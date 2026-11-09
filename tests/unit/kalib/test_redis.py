"""Tests for `zx.lib.redis` — Config/Pool/Flag/Lock over fakeredis.

No real sockets anywhere: every client comes from the `fake_redis`
factory, and `zx.lib.redis.sleep`/`zx.lib.redis.monotonic` are scripted
wherever a blocking path would otherwise touch real time.

Lock context-manager tests stub `release()`: fakeredis has no Lua
(`evalsha`), so the real release path cannot run against it.
"""

import dataclasses
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import fakeredis
import pytest
from faker import Faker
from redis.exceptions import ConnectionError as RedisConnectionError
from redis_lock.exceptions import LockNotOwnedError

from zx.lib.redis import Config, Flag, Lock, Pool, create_pool

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 6379
ALT_PORT = 6380
DEFAULT_DB = 0
DEFAULT_DECODE_RESPONSES = True

POLL_INTERVAL = 0.25
FLAG_TIMEOUT = 1.0
FLAG_POLL = 0.05
MONOTONIC_START = 100.0
DEADLINE_OVERDRAW = 1.0

ZERO = 0
FIRST_INCREMENT = 1
FIRST_ATTEMPT = 1
EXPECTED_PINGS = 2
SINGLE_CALL = 1
TWO_CALLS = 2
KEY_EXISTS = 1
DELETED_ONCE = 1
NO_EXPIRE_TTL = -1

FLAG_TTL_INIT = 30
FLAG_TTL_CALL = 10

POOL_TEST_TIMEOUT = 10
FLAG_TEST_TIMEOUT = 10
LOCK_TIMEOUT = 0.05
LOCK_WAIT_TIMEOUT = 5.0
LOCK_TEST_TIMEOUT = 30
LOCK_TTL = 30
LOCK_POLL_FAST = 0.01
RELEASE_DELAY = 0.1
CLOCK_JUMP = 50.0
UNLOCK_MESSAGE_TEXT = "ok"
SEAM_TIMEOUT = 1.0
CHANGED_POLL = 0.5
FIRST_TICK = 0.4
SECOND_TICK = 0.7
FINAL_TICK = 1.1
SIGNAL_TRUE_CALLS = 2
KEEPALIVE_IDLE = 60

UP_TTL_CASES = (
    # configured ttl (init), explicit ttl (call), expected client ttl
    (0, 0, NO_EXPIRE_TTL),
    (0, FLAG_TTL_CALL, FLAG_TTL_CALL),
    (FLAG_TTL_INIT, 0, FLAG_TTL_INIT),
    (FLAG_TTL_INIT, FLAG_TTL_CALL, FLAG_TTL_INIT),
)
UP_TTL_IDS = ("no-ttl", "call-ttl", "init-ttl", "init-ttl-wins")


@pytest.fixture
def redis_stub(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> Iterator[list[dict[str, Any]]]:
    """Patch `zx.lib.redis.Redis`; record constructor kwargs per call.

    `create_pool` is @cache'd — the cache is cleared around each test
    so memoization is observed within a single test only.
    """
    calls: list[dict[str, Any]] = []

    def _record(**kwargs: Any) -> fakeredis.FakeRedis:  # noqa: ANN401
        calls.append(kwargs)
        return fake_redis()

    monkeypatch.setattr("zx.lib.redis.Redis", _record)
    create_pool.cache_clear()
    yield calls
    create_pool.cache_clear()


# --- config defaults ---


def test_config_defaults_match_redis_convention() -> None:
    """
    Given: a Config built with no arguments.
    When: its fields are inspected.
    Then: the documented localhost/6379/db0 convention holds, with
        decode_responses enabled.
    """
    # --- Arrange ---

    # --- Act ---
    config = Config()

    # --- Assert ---
    assert config.host == DEFAULT_HOST
    assert config.port == DEFAULT_PORT
    assert config.db == DEFAULT_DB
    assert config.decode_responses is DEFAULT_DECODE_RESPONSES


def test_config_reassignment_raises_frozen_instance_error() -> None:
    """
    Given: an existing Config instance.
    When: a field is reassigned.
    Then: a FrozenInstanceError is raised.
    """
    # --- Arrange ---
    config = Config()

    # --- Act / Assert ---
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.port = ALT_PORT  # type: ignore[misc]


def test_config_keepalive_options_dict_stays_hashable_and_cacheable(
    redis_stub: list[dict[str, Any]],
) -> None:
    """
    Given: a Config carrying a socket_keepalive_options dict — unhashable
        by nature, excluded from the field hash.
    When: the config is hashed and create_pool runs twice with equal
        instances.
    Then: hashing works and the cached client is shared — Redis was
        built exactly once.
    """
    # --- Arrange ---
    options = {"TCP_KEEPIDLE": KEEPALIVE_IDLE}

    # --- Act ---
    first = create_pool(Config(socket_keepalive_options=dict(options)))
    second = create_pool(Config(socket_keepalive_options=dict(options)))

    # --- Assert ---
    assert hash(Config(socket_keepalive_options=dict(options)))
    assert second is first
    assert len(redis_stub) == SINGLE_CALL


# --- create_pool memoization ---
# --- create_pool memoization ---


def test_create_pool_same_config_returns_cached_instance(
    redis_stub: list[dict[str, Any]],
) -> None:
    """
    Given: a Config and a patched `zx.lib.redis.Redis` recorder.
    When: create_pool is called twice with the same instance.
    Then: the very same client is returned and Redis was built once
        from the config asdict.
    """
    # --- Arrange ---
    config = Config()

    # --- Act ---
    first = create_pool(config)
    second = create_pool(config)

    # --- Assert ---
    assert first is second
    assert redis_stub == [dataclasses.asdict(config)]


def test_create_pool_equal_config_hits_cache(
    redis_stub: list[dict[str, Any]],
) -> None:
    """
    Given: a frozen, hashable Config — equality implies same cache key.
    When: create_pool is called with an equal but distinct instance.
    Then: the cached client is returned and Redis was built once.
    """
    # --- Arrange ---
    first = create_pool(Config())

    # --- Act ---
    second = create_pool(Config())

    # --- Assert ---
    assert second is first
    assert len(redis_stub) == SINGLE_CALL


def test_create_pool_different_config_returns_new_instance(
    redis_stub: list[dict[str, Any]],
) -> None:
    """
    Given: two Configs differing in a single field.
    When: create_pool is called with each.
    Then: distinct clients are returned and Redis was built per config.
    """
    # --- Arrange ---

    # --- Act ---
    first = create_pool(Config())
    other = create_pool(Config(port=ALT_PORT))

    # --- Assert ---
    assert other is not first
    assert len(redis_stub) == TWO_CALLS


# --- pool worker ---


def test_pool_worker_healthy_ping_returns_client_without_sleep(
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a pool whose client answers ping immediately.
    When: the worker is requested.
    Then: the client is returned without any poll sleep.
    """
    # --- Arrange ---
    client = fake_redis()
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    pool = Pool(client=client, poll=POLL_INTERVAL)

    # --- Act ---
    worker = pool.worker

    # --- Assert ---
    assert worker is client
    assert sleeps == []


@pytest.mark.timeout(POOL_TEST_TIMEOUT)
def test_pool_worker_recoverable_failure_then_success_retries(
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a client whose ping raises a recoverable ConnectionError once
        and succeeds afterwards; a recorded `zx.lib.redis.sleep`.
    When: the worker is requested.
    Then: the client is returned after one poll sleep with the poll
        value, having pinged exactly twice.
    """
    # --- Arrange ---
    client = fake_redis()
    state = {"pings": ZERO}

    def _flaky_ping() -> bool:
        state["pings"] += 1
        if state["pings"] == FIRST_ATTEMPT:
            raise RedisConnectionError("connection refused")
        return True

    monkeypatch.setattr(client, "ping", _flaky_ping)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    pool = Pool(client=client, poll=POLL_INTERVAL)

    # --- Act ---
    worker = pool.worker

    # --- Assert ---
    assert worker is client
    assert state["pings"] == EXPECTED_PINGS
    assert sleeps == [POLL_INTERVAL]


def test_pool_worker_robust_false_skips_ping_and_sleep(
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a non-robust pool and a client with a ping spy.
    When: the worker is requested.
    Then: the client is returned with zero pings and zero sleeps — a
        single attempt, no retry machinery engaged.
    """
    # --- Arrange ---
    client = fake_redis()
    state = {"pings": ZERO}

    def _spy_ping() -> bool:
        state["pings"] += 1
        return True

    monkeypatch.setattr(client, "ping", _spy_ping)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    pool = Pool(client=client, poll=POLL_INTERVAL, robust=False)

    # --- Act ---
    worker = pool.worker

    # --- Assert ---
    assert worker is client
    assert state["pings"] == ZERO
    assert sleeps == []


def test_pool_worker_signal_false_returns_client_without_ping(
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a pool with a falsy signal and a client whose ping must
        never run.
    When: the worker is requested.
    Then: the client is returned immediately — the loop gate short-
        circuits before any ping or sleep.
    """
    # --- Arrange ---
    client = fake_redis()

    def _forbidden_ping() -> bool:
        raise AssertionError("ping must not run")

    monkeypatch.setattr(client, "ping", _forbidden_ping)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    pool = Pool(client=client, poll=POLL_INTERVAL, signal=lambda: False)

    # --- Act ---
    worker = pool.worker

    # --- Assert ---
    assert worker is client
    assert sleeps == []


# --- pool condition ---
# --- pool condition ---


@pytest.mark.parametrize(
    "signal,expected",
    (
        (None, True),
        (lambda: False, False),
    ),
    ids=("default-truthy", "override-false"),
)
def test_pool_condition_signal_returns_expected(
    fake_redis: Callable[..., fakeredis.FakeRedis],
    signal: Callable[[], bool] | None,
    expected: bool,
) -> None:
    """
    Given: a pool with a parametrized signal override.
    When: the condition/on state is read.
    Then: the default is truthy and a signal override flips it.
    """
    # --- Arrange ---
    pool = Pool(client=fake_redis(), signal=signal)

    # --- Act ---

    # --- Assert ---
    assert pool.on is expected
    assert callable(pool.condition)


# --- flag up / drop ---


@pytest.mark.timeout(FLAG_TEST_TIMEOUT)
@pytest.mark.parametrize(
    "init_ttl,call_ttl,expected_ttl",
    UP_TTL_CASES,
    ids=UP_TTL_IDS,
)
def test_flag_up_with_ttl_sets_expected_expire(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    init_ttl: int,
    call_ttl: int,
    expected_ttl: int,
) -> None:
    """
    Given: a flag with a parametrized configured ttl, up called with a
        parametrized explicit ttl.
    When: up is called.
    Then: the counter reads 1 and the fake client reports the expected
        ttl — the configured ttl wins over the call argument.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    flag = Flag(name, client=client, ttl=init_ttl)

    # --- Act ---
    result = flag.up(ttl=call_ttl)

    # --- Assert ---
    assert result == FIRST_INCREMENT
    assert client.ttl(name) == expected_ttl


def test_flag_drop_deletes_key_and_reports_count(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a raised flag.
    When: drop is called twice.
    Then: the first call reports one deleted key, the value reads None,
        and the second call reports nothing left to delete.
    """
    # --- Arrange ---
    client = fake_redis()
    flag = Flag(fake.word(), client=client)
    flag.up()

    # --- Act ---
    first = flag.drop()

    # --- Assert ---
    assert first == DELETED_ONCE
    assert flag.value is None
    assert flag.drop() == ZERO


# --- flag value / integer ---


def test_flag_missing_key_value_none_integer_zero(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a flag whose key was never set.
    When: value and integer are read.
    Then: value is None and integer coerces to zero.
    """
    # --- Arrange ---
    flag = Flag(fake.word(), client=fake_redis())

    # --- Act ---

    # --- Assert ---
    assert flag.value is None
    assert flag.integer == ZERO


# --- flag updated / down ---


def test_flag_down_snapshots_updated_to_false(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a raised flag — its initial snapshot no longer matches.
    When: down is called.
    Then: the snapshot is refreshed and updated reads False.
    """
    # --- Arrange ---
    flag = Flag(fake.word(), client=fake_redis())
    flag.up()
    assert flag.updated is True

    # --- Act ---
    flag.down()

    # --- Assert ---
    assert flag.updated is False


def test_flag_updated_external_incr_returns_true(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a flag snapshotted at zero.
    When: the counter is incremented behind its back.
    Then: updated reads True — the snapshot diverged.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    flag = Flag(name, client=client)

    # --- Act ---
    client.incr(name)

    # --- Assert ---
    assert flag.updated is True


# --- flag changed ---


@pytest.mark.timeout(FLAG_TEST_TIMEOUT)
def test_flag_changed_external_incr_returns_true(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a flag snapshotted at zero with a scripted no-op sleep.
    When: the counter is incremented behind its back and changed runs.
    Then: changed returns True on the very first poll, before any sleep.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    flag = Flag(name, client=client, poll=FLAG_POLL)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    client.incr(name)

    # --- Act ---
    changed = flag.changed(FLAG_TIMEOUT)

    # --- Assert ---
    assert changed is True
    assert sleeps == []


@pytest.mark.timeout(FLAG_TEST_TIMEOUT)
def test_flag_changed_past_deadline_returns_false(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a never-set flag and a scripted monotonic sequence whose
        second reading is past the deadline, with a recorded sleep.
    When: changed runs with a timeout.
    Then: False is returned past the deadline, without any sleeping.
    """
    # --- Arrange ---
    flag = Flag(
        fake.word(),
        client=fake_redis(),
        blocked=False,
        poll=FLAG_POLL,
    )
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    past_deadline = MONOTONIC_START + FLAG_TIMEOUT + DEADLINE_OVERDRAW
    ticks = iter((MONOTONIC_START, past_deadline))
    monkeypatch.setattr("zx.lib.redis.monotonic", lambda: next(ticks))

    # --- Act ---
    changed = flag.changed(FLAG_TIMEOUT)

    # --- Assert ---
    assert changed is False
    assert sleeps == []


@pytest.mark.timeout(FLAG_TEST_TIMEOUT)
def test_flag_changed_constructor_timeout_applies_without_argument(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a flag constructed with timeout=FLAG_TIMEOUT and a scripted
        monotonic whose second reading is past the deadline.
    When: changed runs without a timeout argument.
    Then: the constructor timeout binds — False past the deadline.
    """
    # --- Arrange ---
    flag = Flag(
        fake.word(),
        client=fake_redis(),
        blocked=False,
        poll=FLAG_POLL,
        timeout=FLAG_TIMEOUT,
    )
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    past_deadline = MONOTONIC_START + FLAG_TIMEOUT + DEADLINE_OVERDRAW
    ticks = iter((MONOTONIC_START, past_deadline))
    monkeypatch.setattr("zx.lib.redis.monotonic", lambda: next(ticks))

    # --- Act ---
    changed = flag.changed()

    # --- Assert ---
    assert changed is False
    assert sleeps == []


@pytest.mark.timeout(FLAG_TEST_TIMEOUT)
def test_flag_changed_poll_argument_caps_every_sleep(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an unset flag, a per-call poll argument wider than the
        instance poll, and a scripted monotonic walking past the
        deadline in fixed steps.
    When: changed runs with the poll argument.
    Then: every sleep is the per-call poll, capped by the remaining
        budget — the argument applies to all iterations, not just
        the first.
    """
    # --- Arrange ---
    flag = Flag(fake.word(), client=fake_redis(), blocked=False, poll=FLAG_POLL)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    ticks = iter(
        (
            MONOTONIC_START,
            MONOTONIC_START + FIRST_TICK,
            MONOTONIC_START + SECOND_TICK,
            MONOTONIC_START + FINAL_TICK,
        ),
    )
    monkeypatch.setattr("zx.lib.redis.monotonic", lambda: next(ticks))

    # --- Act ---
    changed = flag.changed(FLAG_TIMEOUT, poll=CHANGED_POLL)

    # --- Assert ---
    assert changed is False
    assert sleeps == pytest.approx([CHANGED_POLL, FLAG_TIMEOUT - SECOND_TICK])


# --- flag non_zero ---
# --- flag non_zero ---


@pytest.mark.timeout(FLAG_TEST_TIMEOUT)
def test_flag_non_zero_blocks_until_set_returns_true(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an unset flag whose scripted sleep raises the counter.
    When: non_zero runs.
    Then: it blocks across polls and returns True once set.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    flag = Flag(name, client=client, poll=FLAG_POLL)

    def _wake(_seconds: float) -> None:
        client.incr(name)

    monkeypatch.setattr("zx.lib.redis.sleep", _wake)

    # --- Act ---
    non_zero = flag.non_zero()

    # --- Assert ---
    assert non_zero is True


@pytest.mark.timeout(FLAG_TEST_TIMEOUT)
def test_flag_non_zero_condition_false_returns_false(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a flag with a falsy signal override and a recorded sleep.
    When: non_zero runs.
    Then: False is returned immediately — the loop body never engages.
    """
    # --- Arrange ---
    flag = Flag(
        fake.word(),
        client=fake_redis(),
        poll=FLAG_POLL,
        signal=lambda: False,
    )
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)

    # --- Act ---
    non_zero = flag.non_zero()

    # --- Assert ---
    assert non_zero is False
    assert sleeps == []


# --- lock acquire ---


def test_lock_acquire_free_lock_sets_key_with_ttl(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a free lock constructed with an explicit ttl.
    When: acquire runs.
    Then: True is returned immediately, the lock key exists, and the
        key carries the configured ttl — a crashed holder can never
        park the lock forever.
    """
    # --- Arrange ---
    client = fake_redis()
    lock = Lock(client, fake.word(), ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)

    # --- Act ---
    acquired = lock.acquire()

    # --- Assert ---
    assert acquired is True
    assert client.exists(lock.name) == KEY_EXISTS
    assert client.ttl(lock.name) == LOCK_TTL


@pytest.mark.timeout(LOCK_TEST_TIMEOUT)
def test_lock_acquire_condition_false_returns_false(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a held lock and a waiter with a falsy signal override.
    When: acquire runs.
    Then: False is returned — the fast acquire fails, the pub/sub wait
        aborts on the condition before any message polling.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    client.set(name, b"other-token")
    lock = Lock(
        client,
        name,
        ttl=LOCK_TTL,
        timeout=LOCK_WAIT_TIMEOUT,
        signal=lambda: False,
    )

    # --- Act ---
    acquired = lock.acquire()

    # --- Assert ---
    assert acquired is False


@pytest.mark.timeout(LOCK_TEST_TIMEOUT)
def test_lock_acquire_deadline_exceeded_returns_false(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a held lock, a small blocking timeout, and a scripted
        monotonic clock that jumps CLOCK_JUMP seconds on every call.
    When: acquire runs.
    Then: False is returned — the outer deadline exhausts on the
        accelerated clock before any message wait completes.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    client.set(name, b"other-token")
    monkeypatch.setattr("zx.lib.redis.monotonic", _AcceleratedClock())
    lock = Lock(client, name, ttl=LOCK_TTL, timeout=LOCK_TIMEOUT)

    # --- Act ---
    acquired = lock.acquire()

    # --- Assert ---
    assert acquired is False


@pytest.mark.timeout(LOCK_TEST_TIMEOUT)
def test_lock_acquire_no_timeout_waits_until_signal_flips(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a held lock and a waiter with timeout=None (wait forever)
        and a signal that flips False after a few condition checks.
    When: acquire runs on the accelerated clock.
    Then: False is returned via the signal gate — the infinite
        deadline never binds, and each message wait is capped at
        the fast poll interval.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    client.set(name, b"other-token")
    monkeypatch.setattr("zx.lib.redis.monotonic", _AcceleratedClock())
    state = {"calls": ZERO}

    def _flip() -> bool:
        state["calls"] += 1
        return state["calls"] <= SIGNAL_TRUE_CALLS

    lock = Lock(
        client,
        name,
        ttl=LOCK_TTL,
        timeout=None,
        poll=LOCK_POLL_FAST,
        signal=_flip,
    )

    # --- Act ---
    acquired = lock.acquire()

    # --- Assert ---
    assert acquired is False
    assert state["calls"] > SIGNAL_TRUE_CALLS


@pytest.mark.timeout(LOCK_TEST_TIMEOUT)
def test_lock_acquire_unlock_message_returns_true(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a holder and a waiter on one shared fake server; the waiter
        subscribes to the lock channel while the holder still owns it.
    When: the holder releases from a side thread — deleting the key and
        publishing the unlock message (fakeredis has no evalsha, so the
        scripted `release()` is replayed manually) — and the waiter keeps
        acquiring.
    Then: the waiter acquires the lock via the pub/sub wait path.
    """
    # --- Arrange ---
    server = fakeredis.FakeServer()
    holder_client = fake_redis(server=server)
    waiter_client = fake_redis(server=server)
    name = fake.word()
    holder = Lock(holder_client, name, ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)
    assert holder.acquire() is True
    waiter = Lock(
        waiter_client,
        name,
        ttl=LOCK_TTL,
        timeout=LOCK_WAIT_TIMEOUT,
        poll=LOCK_POLL_FAST,
    )

    def _release() -> None:
        time.sleep(RELEASE_DELAY)
        holder_client.delete(name)
        holder_client.publish(f"rlock-channel:{name}", UNLOCK_MESSAGE_TEXT)

    releaser = threading.Thread(target=_release, daemon=True)
    releaser.start()

    # --- Act ---
    acquired = waiter.acquire()

    # --- Assert ---
    assert acquired is True
    releaser.join(LOCK_WAIT_TIMEOUT)
    assert releaser.is_alive() is False


# --- lock: _wait_for_message unit seam (single slice) ---


def test_lock_wait_for_message_accepts_str_data_against_bytes_unlock(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a lock whose inherited unlock_message is bytes.
    When: a str unlock message arrives (decode_responses=True payloads).
    Then: the slice resolves True — regression pin for bugs/zx.lib/027.
    """
    # --- Arrange ---
    lock = Lock(fake_redis(), fake.word(), ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)
    pubsub = _StubPubSub([{"type": "message", "data": UNLOCK_MESSAGE_TEXT}])

    # --- Act / Assert ---
    assert lock._wait_for_message(pubsub, timeout=SEAM_TIMEOUT) is True  # noqa: SLF001


def test_lock_wait_for_message_foreign_payload_returns_false(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a scripted pubsub whose next frame carries a foreign payload.
    When: the wait runs.
    Then: False is returned after exactly one frame — the single-slice
        seam never loops over the stream.
    """
    # --- Arrange ---
    lock = Lock(fake_redis(), fake.word(), ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)
    pubsub = _StubPubSub(
        [
            {"type": "message", "data": fake.word()},
            {"type": "message", "data": UNLOCK_MESSAGE_TEXT},
        ],
    )

    # --- Act ---
    result = lock._wait_for_message(pubsub, timeout=SEAM_TIMEOUT)  # noqa: SLF001

    # --- Assert ---
    assert result is False
    assert len(pubsub.calls) == SINGLE_CALL
    assert pubsub._messages, "single slice must leave later frames untouched"  # noqa: SLF001


def test_lock_wait_for_message_silent_pubsub_returns_false(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a scripted pubsub with no frames.
    When: the wait runs.
    Then: False is returned — the caller owns the deadline, the slice
        just reports the empty read.
    """
    # --- Arrange ---
    lock = Lock(fake_redis(), fake.word(), ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)
    pubsub = _StubPubSub([])

    # --- Act / Assert ---
    assert lock._wait_for_message(pubsub, timeout=SEAM_TIMEOUT) is False  # noqa: SLF001


def test_lock_wait_for_message_condition_false_returns_false(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a lock whose abort signal is already False.
    When: the wait starts.
    Then: False is returned immediately, pubsub never consulted.
    """
    # --- Arrange ---
    lock = Lock(
        fake_redis(),
        fake.word(),
        ttl=LOCK_TTL,
        timeout=LOCK_WAIT_TIMEOUT,
        signal=lambda: False,
    )
    pubsub = _StubPubSub([{"type": "message", "data": UNLOCK_MESSAGE_TEXT}])

    # --- Act ---
    result = lock._wait_for_message(pubsub, timeout=SEAM_TIMEOUT)  # noqa: SLF001

    # --- Assert ---
    assert result is False
    assert pubsub.calls == []


def test_lock_wait_for_message_caps_get_message_timeout_at_poll(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a lock with a fast poll interval and a scripted pubsub
        recording get_message kwargs.
    When: the wait runs with a generous slice timeout.
    Then: get_message is capped at the poll interval — the signal is
        re-checked at least every poll.
    """
    # --- Arrange ---
    lock = Lock(
        fake_redis(),
        fake.word(),
        ttl=LOCK_TTL,
        timeout=LOCK_WAIT_TIMEOUT,
        poll=LOCK_POLL_FAST,
    )
    pubsub = _StubPubSub([])

    # --- Act ---
    result = lock._wait_for_message(pubsub, timeout=SEAM_TIMEOUT)  # noqa: SLF001

    # --- Assert ---
    assert result is False
    assert [call["timeout"] for call in pubsub.calls] == [LOCK_POLL_FAST]


# --- helpers ---


class _StubPubSub:
    """A pubsub stub replaying a scripted message sequence."""

    def __init__(self, messages: list[dict | None]) -> None:
        self._messages = list(messages)
        self.calls: list[dict[str, Any]] = []

    def get_message(self, **kw: Any) -> dict | None:
        """Record the call; pop the next scripted message (None if empty)."""
        self.calls.append(kw)
        return self._messages.pop(0) if self._messages else None


class _AcceleratedClock:
    """A `monotonic()` stub jumping CLOCK_JUMP seconds per call.

    Any deadline arithmetic exhausts after a couple of reads, so
    blocking loops terminate deterministically without real waiting.
    """

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        self._now += CLOCK_JUMP
        return self._now


# --- appended contract tests (pool construction & worker edges) ---

NEGATIVE_TTL = -5


def test_pool_no_client_no_config_builds_from_default_config(
    redis_stub: list[dict[str, Any]],
) -> None:
    """
    Given: a patched `zx.lib.redis.Redis` recorder with a cleared
        create_pool cache.
    When: a Pool is constructed with neither client nor config.
    Then: the default Config() arm runs — Redis was built exactly once
        from the default config asdict and stored on `_client`.
    """
    # --- Arrange ---

    # --- Act ---
    pool = Pool()

    # --- Assert ---
    assert redis_stub == [dataclasses.asdict(Config())]
    assert isinstance(pool._client, fakeredis.FakeRedis)  # noqa: SLF001


def test_pool_worker_falsy_ping_retries_after_sleep(
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a client whose ping returns falsy once, then truthy; a
        recorded `zx.lib.redis.sleep`.
    When: the worker is requested.
    Then: the loop retries — one poll sleep happens and the client is
        returned on the second ping (falsy ping is not an exception).
    """
    # --- Arrange ---
    client = fake_redis()
    state = {"pings": ZERO}

    def _falsy_then_ok_ping() -> bool:
        state["pings"] += 1
        return state["pings"] >= EXPECTED_PINGS

    monkeypatch.setattr(client, "ping", _falsy_then_ok_ping)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    pool = Pool(client=client, poll=POLL_INTERVAL)

    # --- Act ---
    worker = pool.worker

    # --- Assert ---
    assert worker is client
    assert state["pings"] == EXPECTED_PINGS
    assert sleeps == [POLL_INTERVAL]


def test_pool_worker_non_recoverable_ping_error_propagates(
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a client whose ping raises TypeError — outside Recoverable.
    When: the worker is requested.
    Then: TypeError propagates out of the worker; no sleep, no retry.
    """
    # --- Arrange ---
    client = fake_redis()

    def _bad_ping() -> bool:
        raise TypeError("bad ping")

    monkeypatch.setattr(client, "ping", _bad_ping)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    pool = Pool(client=client, poll=POLL_INTERVAL)

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="bad ping"):
        _ = pool.worker
    assert sleeps == []


def test_pool_worker_recoverable_failure_logs_reason(
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: a client whose ping raises a recoverable ConnectionError
        once, then succeeds.
    When: the worker is requested under a WARNING-level caplog.
    Then: logger.warning fires once with `exception(e).reason` —
        ConnectionError(...) carrying the JSON-rendered argument.
    """
    # --- Arrange ---
    client = fake_redis()
    state = {"pings": ZERO}

    def _flaky_ping() -> bool:
        state["pings"] += 1
        if state["pings"] == FIRST_ATTEMPT:
            raise RedisConnectionError("connection refused")
        return True

    monkeypatch.setattr(client, "ping", _flaky_ping)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    pool = Pool(client=client, poll=POLL_INTERVAL)

    # --- Act ---
    with caplog.at_level("WARNING", logger="zx.lib.redis"):
        worker = pool.worker

    # --- Assert ---
    expected_reason = (
        r'redis.exceptions.ConnectionError("\"connection refused\"")'
    )
    warnings = [
        record
        for record in caplog.records
        if record.name == "zx.lib.redis" and record.levelname == "WARNING"
    ]
    assert worker is client
    assert [record.getMessage() for record in warnings] == [expected_reason]


# --- appended contract tests (flag edges) ---


def test_flag_non_str_name_converted_via_who_is(
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a Flag constructed with a non-str name (42).
    When: the name attribute is read.
    Then: the Who.Is conversion arm produced the class name "int".
    """
    # --- Arrange ---
    flag = Flag(42, client=fake_redis())

    # --- Act / Assert ---
    assert flag.name == "int"


def test_flag_unblocked_snapshots_minus_one_updated_immediately(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a Flag with blocked=False on an unset counter.
    When: updated is read before any up() call.
    Then: the -1 snapshot diverges from integer 0 — updated is True
        immediately.
    """
    # --- Arrange ---
    flag = Flag(fake.word(), client=fake_redis(), blocked=False)

    # --- Act / Assert ---
    assert flag.updated is True


def test_flag_value_after_up_returns_int_under_decode_responses(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a raised flag on a decode_responses=True client.
    When: value is read after up().
    Then: the raw client payload is converted — an int comes back.
    """
    # --- Arrange ---
    flag = Flag(fake.word(), client=fake_redis())

    # --- Act ---
    flag.up()
    value = flag.value

    # --- Assert ---
    assert value == 1
    assert isinstance(value, int)


@pytest.mark.timeout(FLAG_TEST_TIMEOUT)
def test_flag_changed_counter_drop_to_zero_resets_snapshot(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an unblocked flag whose counter was raised then deleted
        (drop to zero), a recorded sleep, and a scripted monotonic
        whose second reading is past the deadline.
    When: changed runs with a timeout.
    Then: the drop-to-zero arm resets the snapshot, the deadline arm
        returns False without sleeping, and updated reads False after.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    flag = Flag(name, client=client, blocked=False, poll=FLAG_POLL)
    client.incr(name)
    client.delete(name)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    past_deadline = MONOTONIC_START + FLAG_TIMEOUT + DEADLINE_OVERDRAW
    ticks = iter((MONOTONIC_START, past_deadline))
    monkeypatch.setattr("zx.lib.redis.monotonic", lambda: next(ticks))

    # --- Act ---
    changed = flag.changed(FLAG_TIMEOUT)

    # --- Assert ---
    assert changed is False
    assert sleeps == []
    assert flag.updated is False


@pytest.mark.timeout(FLAG_TEST_TIMEOUT)
def test_flag_call_and_bool_alias_changed_and_non_zero(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an externally incremented flag with a recorded sleep.
    When: the instance is called and bool()'ed.
    Then: __call__ resolves as changed and __bool__ as non_zero —
        both True on the already-raised counter, without any sleep.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    flag = Flag(name, client=client, poll=FLAG_POLL)
    sleeps: list[float] = []
    monkeypatch.setattr("zx.lib.redis.sleep", sleeps.append)
    client.incr(name)

    # --- Act / Assert ---
    assert flag(FLAG_TIMEOUT) is True
    assert bool(flag) is True
    assert sleeps == []


def test_flag_up_with_negative_ttl_removes_key(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a flag with no configured ttl, up called with ttl=-5.
    When: up returns.
    Then: incr reports 1 and the negative expire deletes the key —
        exists() reads zero.  # expected: verify (fakeredis arm)
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    flag = Flag(name, client=client)

    # --- Act ---
    result = flag.up(ttl=NEGATIVE_TTL)

    # --- Assert ---
    assert result == FIRST_INCREMENT
    assert client.exists(name) == ZERO


# --- appended contract tests (lock message-wait edges) ---


def test_lock_wait_for_message_bytes_data_against_str_unlock(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a lock whose unlock_message is patched to the str form while
        the pubsub stub delivers a bytes payload (reverse of bug-027).
    When: the wait runs.
    Then: the bytes data decodes against the str expectation — True.
    """
    # --- Arrange ---
    lock = Lock(fake_redis(), fake.word(), ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)
    lock.unlock_message = UNLOCK_MESSAGE_TEXT
    pubsub = _StubPubSub(
        [{"type": "message", "data": UNLOCK_MESSAGE_TEXT.encode()}],
    )

    # --- Act / Assert ---
    assert lock._wait_for_message(pubsub, timeout=SEAM_TIMEOUT) is True  # noqa: SLF001


def test_lock_wait_for_message_non_message_type_returns_false(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
) -> None:
    """
    Given: a scripted pubsub whose next frame is not a "message".
    When: the wait runs.
    Then: False is returned after that single frame — subscribe and
        pmessage frames do not resolve the wait.
    """
    # --- Arrange ---
    lock = Lock(fake_redis(), fake.word(), ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)
    pubsub = _StubPubSub(
        [
            {"type": "pmessage", "data": UNLOCK_MESSAGE_TEXT.encode()},
            {"type": "message", "data": UNLOCK_MESSAGE_TEXT},
        ],
    )

    # --- Act ---
    result = lock._wait_for_message(pubsub, timeout=SEAM_TIMEOUT)  # noqa: SLF001

    # --- Assert ---
    assert result is False
    assert len(pubsub.calls) == SINGLE_CALL


# --- lock context manager ---


def test_lock_context_clean_exit_calls_release(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an acquirable lock whose release is stubbed (fakeredis has
        no evalsha for the real Lua release).
    When: the context exits without an exception.
    Then: release ran exactly once.
    """
    # --- Arrange ---
    lock = Lock(fake_redis(), fake.word(), ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)
    releases: list[bool] = []
    monkeypatch.setattr(lock, "release", lambda: releases.append(True))

    # --- Act ---
    with lock:
        pass

    # --- Assert ---
    assert len(releases) == SINGLE_CALL


def test_lock_context_body_error_still_releases(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an acquirable lock with a stubbed release.
    When: the context body raises.
    Then: the original exception propagates and release still ran.
    """
    # --- Arrange ---
    lock = Lock(fake_redis(), fake.word(), ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)
    releases: list[bool] = []
    monkeypatch.setattr(lock, "release", lambda: releases.append(True))

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="boom"), lock:
        raise ValueError("boom")
    assert len(releases) == SINGLE_CALL


def test_lock_context_body_error_lock_lost_warns_and_propagates(
    fake: Faker,
    fake_redis: Callable[..., fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: an acquirable lock whose release fails with
        LockNotOwnedError — the key expired or was stolen mid-body.
    When: the context body raises.
    Then: the original exception propagates and the lost lock is
        logged as a warning naming the lock.
    """
    # --- Arrange ---
    client = fake_redis()
    name = fake.word()
    lock = Lock(client, name, ttl=LOCK_TTL, timeout=LOCK_WAIT_TIMEOUT)

    def _lost() -> bool:
        raise LockNotOwnedError

    monkeypatch.setattr(lock, "release", _lost)

    # --- Act / Assert ---
    with (
        caplog.at_level("WARNING", logger="zx.lib.redis"),
        pytest.raises(ValueError, match="boom"),
        lock,
    ):
        raise ValueError("boom")

    warnings = [
        record
        for record in caplog.records
        if record.name == "zx.lib.redis" and record.levelname == "WARNING"
    ]
    assert [record.getMessage() for record in warnings] == [
        "lock lost before release",
    ]
    assert [record.lock for record in warnings] == [name]
