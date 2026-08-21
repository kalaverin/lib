"""Tests for `zx.lib.datetime` — epoch alignment, the `dt` wrapper, `Timer`."""

import operator
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

import pytest
import time_machine
from dateutil.parser import ParserError
from faker import Faker

import zx.lib.datetime as zx_lib_datetime
from zx.lib.datetime import (
    Timer,
    TimeSpec,
    align_datetime_to_index,
    dt,
    get_local_timezone,
)

SECOND = timedelta(seconds=1)

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
NANOSECONDS_PER_SECOND = 1_000_000_000
MAX_EXACT_INTEGER_NS = 2**53 - 1
NS_ROUND_TRIP_TOLERANCE = 1_000  # one microsecond, in nanoseconds
ISO_SECONDS_TEMPLATE = "%Y-%m-%dT%H:%M:%S"

OFFSET_EAST = timezone(timedelta(hours=2))
OFFSET_WEST = timezone(timedelta(hours=-5))

KNOWN_UTC = datetime(2031, 5, 4, 3, 2, 1, tzinfo=UTC)
KNOWN_NAIVE = datetime(2031, 5, 4, 3, 2, 1)  # noqa: DTZ001
KNOWN_NAIVE_AS_EAST_UTC = datetime(2031, 5, 4, 1, 2, 1, tzinfo=UTC)
KNOWN_UTC_STR = "2031-05-04T03:02:01Z"
KNOWN_MINUTES_STR = "2031-05-04T03:02Z"
KNOWN_EAST_STR = "2031-05-04T05:02:01+02:00"
KNOWN_WEST_STR = "2031-05-03T22:02:01-05:00"

# Scripted monotonic ticks for Timer tests; the gaps carry the meaning.
TICK_ENTER = 100.0
TICK_LEAVE = 110.0
TICK_REENTER = 200.0
TICK_RELEAVE = 260.0
TICK_RUNNING = 150.0
TICK_RUNNING_END = 210.0
TICK_INNER_ENTER = 120.0
TICK_INNER_LEAVE = 150.0
TICK_OUTER_LEAVE = 400.0

DELTA_FIRST = TICK_LEAVE - TICK_ENTER
DELTA_SECOND = TICK_RELEAVE - TICK_REENTER
DELTA_BOTH = DELTA_FIRST + DELTA_SECOND
DELTA_RUNNING = TICK_RUNNING - TICK_ENTER
DELTA_RUNNING_TOTAL = TICK_RUNNING_END - TICK_ENTER
DELTA_INNER = TICK_INNER_LEAVE - TICK_INNER_ENTER
DELTA_OUTER = TICK_OUTER_LEAVE - TICK_ENTER

ALIGN_PAIRS: tuple[tuple[int, int], ...] = (
    (1, 0),
    (60, 1),
    (60, -1),
    (3600, 24),
    (86400, 3),
    (7, 1000),
)
ALIGN_PAIR_IDS = (
    "1s-at-epoch",
    "60s-one-minute",
    "60s-before-epoch",
    "3600s-one-day",
    "86400s-three-days",
    "7s-exact-multiple",
)

EPOCH_INDEX_CASES: tuple[tuple[datetime, int, int], ...] = (
    (EPOCH, 60, 0),
    (EPOCH + 59 * SECOND, 60, 0),
    (EPOCH + 60 * SECOND, 60, 1),
    (EPOCH + 119 * SECOND, 60, 1),
    (EPOCH - SECOND, 60, -1),
)
EPOCH_INDEX_IDS = (
    "at-epoch",
    "last-second-of-period",
    "first-second-of-next",
    "second-of-next",
    "before-epoch",
)

ALIGN_TO_PERIOD_CASES: tuple[tuple[int, int, int, int], ...] = (
    # offset_s, period, shift, expected_offset_s
    (91, 60, 0, 60),
    (91, 60, 1, 120),
    (91, 60, -1, 0),
    (0, 3600, 2, 7200),
)
ALIGN_TO_PERIOD_IDS = (
    "floors-to-boundary",
    "shift-forward",
    "shift-backward",
    "epoch-with-shift",
)

TIMESTAMP_CASES: tuple[float, ...] = (0.0, 1_000_000_000.0, -1.0)
TIMESTAMP_IDS = ("epoch", "billions", "before-epoch")

NANOSECOND_CASES: tuple[int, ...] = (0, 1_000_000_000, 123_456_789_123_456)
NANOSECOND_IDS = ("epoch", "one-second", "sub-second")

COMPARISON_MATRIX: tuple[tuple[str, str, bool], ...] = (
    # op, relation of the other operand to the base, expected
    ("eq", "same", True),
    ("eq", "later", False),
    ("ne", "later", True),
    ("ne", "same", False),
    ("lt", "later", True),
    ("lt", "same", False),
    ("le", "same", True),
    ("le", "earlier", False),
    ("gt", "earlier", True),
    ("gt", "same", False),
    ("ge", "same", True),
    ("ge", "later", False),
)
COMPARISON_IDS = (
    "eq-same",
    "eq-later",
    "ne-later",
    "ne-same",
    "lt-later",
    "lt-same",
    "le-same",
    "le-earlier",
    "gt-earlier",
    "gt-same",
    "ge-same",
    "ge-later",
)

ORDERING_OPS = ("lt", "le", "gt", "ge")
FOREIGN_VALUES: tuple[object, ...] = (None, 42, "text", (1, 2))
FOREIGN_IDS = ("none", "int", "str", "tuple")

align_index_pairs = pytest.mark.parametrize(
    "period,idx",
    ALIGN_PAIRS,
    ids=ALIGN_PAIR_IDS,
)


# --- module functions ---


@align_index_pairs
def test_align_datetime_to_index_returns_utc_exact_multiple(
    period: int,
    idx: int,
) -> None:
    """
    Given: a parametrized period and epoch-index pair.
    When: they are aligned to a datetime.
    Then: the result is UTC-aware at the exact multiple idx * period.
    """
    # --- Arrange ---

    # --- Act ---
    result = align_datetime_to_index(period, idx)

    # --- Assert ---
    assert result.tzinfo is UTC
    assert result.timestamp() == period * idx


def test_get_local_timezone_returns_usable_tzinfo() -> None:
    """
    Given: the host platform reports a local timezone.
    When: get_local_timezone is called.
    Then: a tzinfo with a resolvable utcoffset is returned.
    """
    # --- Arrange ---

    # --- Act ---
    result = get_local_timezone()

    # --- Assert ---
    assert isinstance(result, tzinfo)
    assert datetime.now(result).utcoffset() is not None


# --- dt: now-based constructors ---


def test_dt_utc_returns_frozen_destination_in_utc(
    frozen_time: time_machine.travel,
) -> None:
    """
    Given: the wall clock frozen at a faker-seeded UTC destination.
    When: the dt.utc classmethod is called.
    Then: the frozen instant is returned with UTC tzinfo.
    """
    # --- Arrange ---
    expected_ns = frozen_time.time_ns()

    # --- Act ---
    result = dt.utc()

    # --- Assert ---
    assert result.tzinfo is UTC
    assert result.timestamp() == pytest.approx(
        expected_ns / NANOSECONDS_PER_SECOND,
        abs=0.001,
    )


def test_dt_default_init_freezes_now(
    frozen_time: time_machine.travel,
) -> None:
    """
    Given: the wall clock frozen at a faker-seeded UTC destination.
    When: a dt is constructed without arguments.
    Then: it wraps the frozen instant as UTC.
    """
    # --- Arrange ---
    expected_ns = frozen_time.time_ns()

    # --- Act ---
    result = dt()

    # --- Assert ---
    assert result.dt.tzinfo is UTC
    assert result.to_ts() == pytest.approx(
        expected_ns / NANOSECONDS_PER_SECOND,
        abs=0.001,
    )


def test_dt_timestamp_reads_frozen_clock(
    frozen_time: time_machine.travel,
) -> None:
    """
    Given: the wall clock frozen at a faker-seeded UTC destination.
    When: the dt.timestamp classmethod is called.
    Then: the frozen instant in seconds is returned.
    """
    # --- Arrange ---
    expected_ns = frozen_time.time_ns()

    # --- Act ---
    result = dt.timestamp()

    # --- Assert ---
    assert result == pytest.approx(
        expected_ns / NANOSECONDS_PER_SECOND,
        abs=0.001,
    )


def test_dt_iso_at_frozen_destination_uses_z_suffix(
    frozen_time: time_machine.travel,
) -> None:
    """
    Given: the wall clock frozen at a faker-seeded UTC destination.
    When: the dt.iso classmethod is called.
    Then: a Z-suffixed ISO string at whole-second precision is returned.
    """
    # --- Arrange ---
    seconds = frozen_time.time_ns() // NANOSECONDS_PER_SECOND
    expected = (
        datetime.fromtimestamp(seconds, tz=UTC).strftime(ISO_SECONDS_TEMPLATE)
        + "Z"
    )

    # --- Act ---
    result = dt.iso()

    # --- Assert ---
    assert result == expected


# --- dt: construction from external values ---


def test_dt_from_datetime_aware_defaults_to_utc() -> None:
    """
    Given: a timezone-aware datetime.
    When: a dt is built from it without an explicit tz.
    Then: the same instant is stored in UTC.
    """
    # --- Arrange ---

    # --- Act ---
    result = dt.from_datetime(KNOWN_UTC)

    # --- Assert ---
    assert result.dt.tzinfo is UTC
    assert result.dt == KNOWN_UTC


def test_dt_from_datetime_naive_with_tz_converts() -> None:
    """
    Given: a naive datetime and an explicit eastward tz.
    When: a dt is built from the pair.
    Then: the instant is shifted from the given tz into UTC.
    """
    # --- Arrange ---

    # --- Act ---
    result = dt.from_datetime(KNOWN_NAIVE, tz=OFFSET_EAST)

    # --- Assert ---
    assert result.dt.tzinfo is UTC
    assert result == KNOWN_NAIVE_AS_EAST_UTC


def test_dt_from_datetime_naive_without_tz_raises_value_error() -> None:
    """
    Given: a naive datetime and no explicit tz.
    When: a dt is built from it.
    Then: a ValueError explaining the missing timezone is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="has no timezone"):
        dt.from_datetime(KNOWN_NAIVE)


def test_dt_from_datetime_aware_with_tz_raises_value_error() -> None:
    """
    Given: an already aware datetime plus an explicit tz.
    When: a dt is built from the pair.
    Then: a ValueError explaining the duplicate timezone is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="already has a timezone"):
        dt.from_datetime(KNOWN_UTC, tz=OFFSET_EAST)


def test_dt_ensure_tz_naive_with_tz_converts() -> None:
    """
    Given: a naive datetime and an explicit eastward tz.
    When: it is passed through dt.ensure_tz.
    Then: the instant is shifted from the given tz into UTC.
    """
    # --- Arrange ---

    # --- Act ---
    result = dt.ensure_tz(KNOWN_NAIVE, tz=OFFSET_EAST)

    # --- Assert ---
    assert result.tzinfo is UTC
    assert result == KNOWN_NAIVE_AS_EAST_UTC


def test_dt_ensure_tz_naive_without_tz_raises_value_error() -> None:
    """
    Given: a naive datetime and no explicit tz.
    When: it is passed through dt.ensure_tz.
    Then: a ValueError explaining the missing timezone is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="has no timezone"):
        dt.ensure_tz(KNOWN_NAIVE)


def test_dt_ensure_tz_aware_with_tz_raises_value_error() -> None:
    """
    Given: an already aware datetime plus an explicit tz.
    When: it is passed through dt.ensure_tz.
    Then: a ValueError explaining the duplicate timezone is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="already has a timezone"):
        dt.ensure_tz(KNOWN_UTC, tz=OFFSET_EAST)


def test_dt_ensure_tz_aware_without_tz_converts_to_utc() -> None:
    """
    Given: an aware non-UTC datetime and no explicit tz.
    When: it is passed through dt.ensure_tz.
    Then: the same instant is returned with UTC tzinfo.
    """
    # --- Arrange ---
    east = KNOWN_UTC.astimezone(OFFSET_EAST)

    # --- Act ---
    result = dt.ensure_tz(east)

    # --- Assert ---
    assert result.tzinfo is UTC
    assert result == KNOWN_UTC


def test_dt_from_str_aware_iso_round_trips(fake: Faker) -> None:
    """
    Given: a faker-driven aware datetime serialized to ISO.
    When: a dt is parsed from that string without an explicit tz.
    Then: the same instant is stored in UTC.
    """
    # --- Arrange ---
    instant = fake.date_time(tzinfo=UTC)

    # --- Act ---
    result = dt.from_str(instant.isoformat())

    # --- Assert ---
    assert result == instant
    assert result.dt.tzinfo is UTC


def test_dt_from_str_naive_with_tz_converts() -> None:
    """
    Given: a naive ISO string and an explicit eastward tz.
    When: a dt is parsed from the pair.
    Then: the instant is shifted from the given tz into UTC.
    """
    # --- Arrange ---

    # --- Act ---
    result = dt.from_str(KNOWN_NAIVE.isoformat(), tz=OFFSET_EAST)

    # --- Assert ---
    assert result == KNOWN_NAIVE_AS_EAST_UTC


def test_dt_from_str_naive_without_tz_raises_value_error() -> None:
    """
    Given: a naive ISO string and no explicit tz.
    When: a dt is parsed from it.
    Then: a ValueError explaining the missing timezone is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="has no timezone"):
        dt.from_str(KNOWN_NAIVE.isoformat())


@pytest.mark.parametrize("value", TIMESTAMP_CASES, ids=TIMESTAMP_IDS)
def test_dt_from_ts_to_ts_round_trip(value: float) -> None:
    """
    Given: a parametrized POSIX timestamp.
    When: a dt is built from it and converted back.
    Then: the exact timestamp is returned.
    """
    # --- Arrange ---

    # --- Act ---
    result = dt.from_ts(value)

    # --- Assert ---
    assert result.dt.tzinfo is UTC
    assert result.to_ts() == value


def test_dt_from_ts_to_ts_round_trip_faker(fake: Faker) -> None:
    """
    Given: a faker-driven POSIX timestamp.
    When: a dt is built from it and converted back.
    Then: the exact timestamp is returned.
    """
    # --- Arrange ---
    ts = float(fake.unix_time())

    # --- Act ---
    result = dt.from_ts(ts)

    # --- Assert ---
    # sub-microsecond digits are rounded away by datetime's µs grid
    assert result.to_ts() == pytest.approx(ts, abs=1e-6)


def test_dt_from_ts_with_tz_preserves_instant() -> None:
    """
    Given: a POSIX timestamp and an explicit eastward tz.
    When: a dt is built from the pair.
    Then: the same instant is stored in UTC.
    """
    # --- Arrange ---
    ts = KNOWN_UTC.timestamp()

    # --- Act ---
    result = dt.from_ts(ts, tz=OFFSET_EAST)

    # --- Assert ---
    assert result == KNOWN_UTC


@pytest.mark.parametrize("value", NANOSECOND_CASES, ids=NANOSECOND_IDS)
def test_dt_from_ns_to_ns_round_trip(value: int) -> None:
    """
    Given: a parametrized POSIX timestamp in nanoseconds.
    When: a dt is built from it and converted back.
    Then: the value is preserved within float-microsecond precision.
    """
    # --- Arrange ---

    # --- Act ---
    result = dt.from_ns(value)

    # --- Assert ---
    assert result.to_ns() == pytest.approx(value, abs=NS_ROUND_TRIP_TOLERANCE)


def test_dt_from_ns_to_ns_round_trip_faker(fake: Faker) -> None:
    """
    Given: a faker-driven POSIX timestamp in nanoseconds.
    When: a dt is built from it and converted back.
    Then: the value is preserved within float-microsecond precision.
    """
    # --- Arrange ---
    value = fake.pyint(min_value=0, max_value=MAX_EXACT_INTEGER_NS)

    # --- Act ---
    result = dt.from_ns(value)

    # --- Assert ---
    assert result.to_ns() == pytest.approx(value, abs=NS_ROUND_TRIP_TOLERANCE)


# --- dt: parse dispatch ---


def test_dt_parse_dt_instance_returns_identity() -> None:
    """
    Given: an existing dt instance.
    When: it is passed to dt.parse.
    Then: the very same object is returned.
    """
    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    result = dt.parse(instance)

    # --- Assert ---
    assert result is instance


def test_dt_parse_datetime_returns_equivalent() -> None:
    """
    Given: a timezone-aware datetime.
    When: it is passed to dt.parse.
    Then: an equivalent dt in UTC is returned.
    """
    # --- Arrange ---

    # --- Act ---
    result = dt.parse(KNOWN_UTC)

    # --- Assert ---
    assert result == KNOWN_UTC
    assert result.dt.tzinfo is UTC


def test_dt_parse_str_dispatches_to_from_str() -> None:
    """
    Given: an ISO string carrying a Z suffix.
    When: it is passed to dt.parse.
    Then: an equivalent dt in UTC is returned.
    """
    # --- Arrange ---

    # --- Act ---
    result = dt.parse(KNOWN_UTC_STR)

    # --- Assert ---
    assert result == KNOWN_UTC


@pytest.mark.parametrize("kind", ("float", "int"), ids=("float", "int"))
def test_dt_parse_number_dispatches_to_from_ts(
    fake: Faker,
    kind: str,
) -> None:
    """
    Given: a faker-driven POSIX timestamp as a parametrized numeric kind.
    When: it is passed to dt.parse.
    Then: the same instant is stored.
    """
    # --- Arrange ---
    ts = fake.unix_time()
    value: float | int = float(ts) if kind == "float" else int(ts)

    # --- Act ---
    result = dt.parse(value)

    # --- Assert ---
    if kind == "float":
        # sub-microsecond digits are rounded away by datetime's µs grid
        assert result.to_ts() == pytest.approx(float(value), abs=1e-6)
    else:
        assert result.to_ts() == float(value)


@pytest.mark.parametrize(
    "value",
    (None, [1, 2], {"a": 1}),
    ids=("none", "list", "dict"),
)
def test_dt_parse_unsupported_type_raises_type_error(value: object) -> None:
    """
    Given: a parametrized value of an unsupported type.
    When: it is passed to dt.parse.
    Then: a TypeError naming the supported types is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(TypeError, match=r"expected datetime \| float \| str"):
        dt.parse(value)


# --- dt: serialization ---


def test_dt_to_str_utc_uses_z_suffix() -> None:
    """
    Given: a dt at a fixed UTC instant.
    When: it is serialized without an explicit tz.
    Then: a Z-suffixed ISO string is returned.
    """
    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    result = instance.to_str()

    # --- Assert ---
    assert result == KNOWN_UTC_STR


def test_dt_to_str_non_utc_uses_offset_form() -> None:
    """
    Given: a dt at a fixed UTC instant.
    When: it is serialized with an explicit non-UTC tz.
    Then: the offset form without a Z suffix is returned.
    """
    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    result_east = instance.to_str(tz=OFFSET_EAST)
    result_west = instance.to_str(tz=OFFSET_WEST)

    # --- Assert ---
    assert result_east == KNOWN_EAST_STR
    assert result_west == KNOWN_WEST_STR


def test_dt_to_str_timespec_minutes_truncates() -> None:
    """
    Given: a dt at a fixed UTC instant.
    When: it is serialized with minute precision.
    Then: the seconds field is dropped from the output.
    """
    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    result = instance.to_str(timespec="minutes")

    # --- Assert ---
    assert result == KNOWN_MINUTES_STR


def test_dt_str_matches_to_str() -> None:
    """
    Given: a dt at a fixed UTC instant.
    When: it is rendered via str().
    Then: the output equals the default to_str form.
    """
    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    result = str(instance)

    # --- Assert ---
    assert result == instance.to_str()


def test_dt_to_datetime_with_tz_converts() -> None:
    """
    Given: a dt at a fixed UTC instant.
    When: it is exported with an explicit tz.
    Then: the converted aware datetime is returned.
    """
    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    result = instance.to_datetime(tz=OFFSET_EAST)

    # --- Assert ---
    assert result == KNOWN_UTC
    assert result.utcoffset() == timedelta(hours=2)


def test_dt_to_ts_with_tz_preserves_instant() -> None:
    """
    Given: a dt at a fixed UTC instant.
    When: it is exported as a timestamp with an explicit tz.
    Then: the same POSIX seconds are returned.
    """
    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    result = instance.to_ts(tz=OFFSET_EAST)

    # --- Assert ---
    assert result == pytest.approx(instance.to_ts(), abs=0.001)


# --- dt: comparisons ---


@pytest.mark.parametrize(
    "other_kind",
    ("dt", "datetime"),
    ids=("other-dt", "other-datetime"),
)
@pytest.mark.parametrize(
    "op,relation,expected",
    COMPARISON_MATRIX,
    ids=COMPARISON_IDS,
)
def test_dt_comparison_matrix_matches_instant_order(
    op: str,
    relation: str,
    expected: bool,
    other_kind: str,
) -> None:
    """
    Given: a dt at a fixed instant and a parametrized comparison operand.
    When: a parametrized comparison operator is applied.
    Then: the result follows the underlying instant ordering.
    """
    # --- Arrange ---
    base = dt.from_datetime(KNOWN_UTC)
    instant_by_relation = {
        "same": KNOWN_UTC,
        "later": KNOWN_UTC + SECOND,
        "earlier": KNOWN_UTC - SECOND,
    }
    other: dt | datetime = (
        dt.from_datetime(instant_by_relation[relation])
        if other_kind == "dt"
        else instant_by_relation[relation]
    )

    # --- Act ---
    result = getattr(operator, op)(base, other)

    # --- Assert ---
    assert result is expected


@pytest.mark.parametrize("value", FOREIGN_VALUES, ids=FOREIGN_IDS)
def test_dt_equality_with_foreign_type_returns_false(value: object) -> None:
    """
    Given: a dt instance and a parametrized foreign value.
    When: equality is compared.
    Then: the comparison is False rather than an error.
    """
    # --- Arrange ---
    base = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    result = base == value

    # --- Assert ---
    assert result is False


@pytest.mark.parametrize("op", ORDERING_OPS, ids=ORDERING_OPS)
@pytest.mark.parametrize("value", FOREIGN_VALUES, ids=FOREIGN_IDS)
def test_dt_ordering_with_foreign_type_raises_type_error(
    op: str,
    value: object,
) -> None:
    """
    Given: a dt instance and a parametrized foreign value.
    When: a parametrized ordering operator is applied.
    Then: a TypeError is raised.
    """
    # --- Arrange ---
    base = dt.from_datetime(KNOWN_UTC)

    # --- Act / Assert ---
    with pytest.raises(TypeError):
        getattr(operator, op)(base, value)


def test_dt_hash_matches_underlying_datetime() -> None:
    """
    Given: two dt instances at the same instant and the raw datetime.
    When: they are hashed and collected into a set.
    Then: equal hashes and deduplication follow datetime semantics.
    """
    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)
    equivalent = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    collected = {instance, equivalent}

    # --- Assert ---
    assert hash(instance) == hash(KNOWN_UTC)
    assert len(collected) == 1


# --- dt: epoch index and alignment ---


@pytest.mark.parametrize(
    "instant,period,expected",
    EPOCH_INDEX_CASES,
    ids=EPOCH_INDEX_IDS,
)
def test_dt_get_epoch_index_counts_whole_periods(
    instant: datetime,
    period: int,
    expected: int,
) -> None:
    """
    Given: a parametrized instant and period.
    When: the epoch index of the instant is computed.
    Then: floor-divided whole periods since the epoch are returned.
    """
    # --- Arrange ---
    instance = dt.from_datetime(instant)

    # --- Act ---
    result = instance.get_epoch_index(period)

    # --- Assert ---
    assert result == expected


@pytest.mark.parametrize(
    "offset_s,period,shift,expected_offset_s",
    ALIGN_TO_PERIOD_CASES,
    ids=ALIGN_TO_PERIOD_IDS,
)
def test_dt_align_to_period_floors_to_period_boundary(
    offset_s: int,
    period: int,
    shift: int,
    expected_offset_s: int,
) -> None:
    """
    Given: a parametrized instant, period, and optional shift.
    When: the dt is aligned to the period.
    Then: the result sits at the expected period boundary in UTC.
    """
    # --- Arrange ---
    instance = dt.from_datetime(EPOCH + timedelta(seconds=offset_s))

    # --- Act ---
    result = instance.align_to_period(period, shift=shift)

    # --- Assert ---
    assert result.dt.tzinfo is UTC
    assert result.dt == EPOCH + timedelta(seconds=expected_offset_s)


def test_dt_align_to_period_round_trips_with_faker(fake: Faker) -> None:
    """
    Given: a faker-driven instant aligned to a whole-day period.
    When: the aligned index is compared with the original index.
    Then: both indexes match and the aligned instant is a boundary.
    """
    # --- Arrange ---
    instant = dt.from_ts(float(fake.unix_time()))
    period = 86_400

    # --- Act ---
    aligned = instant.align_to_period(period)

    # --- Assert ---
    assert aligned.get_epoch_index(period) == instant.get_epoch_index(period)
    assert aligned.dt.timestamp() % period == 0


# --- timer ---


def _scripted_clock(*ticks: float) -> Callable[[], float]:
    """A stand-in for time.monotonic yielding preset ticks in order."""
    remaining = iter(ticks)

    def _next_tick() -> float:
        return next(remaining)

    return _next_tick


def test_timer_delta_before_start_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a Timer that never entered a context, on a clock with no ticks.
    When: delta is read.
    Then: zero is returned and the clock is never consulted.
    """
    # --- Arrange ---
    monkeypatch.setattr(zx_lib_datetime, "monotonic", _scripted_clock())

    # --- Act ---
    result = Timer().delta

    # --- Assert ---
    assert result == 0.0


def test_timer_single_context_accumulates_scripted_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a scripted monotonic clock advancing between enter and exit.
    When: a single context is timed.
    Then: delta equals the scripted elapsed time.
    """
    # --- Arrange ---
    clock = _scripted_clock(TICK_ENTER, TICK_LEAVE)
    monkeypatch.setattr(zx_lib_datetime, "monotonic", clock)

    # --- Act ---
    timer = Timer()
    with timer:
        pass

    # --- Assert ---
    assert timer.delta == DELTA_FIRST


def test_timer_reentered_context_accumulates_spent_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a scripted monotonic clock advancing across two sessions.
    When: the same Timer is entered, exited, and re-entered.
    Then: delta accumulates both scripted spans.
    """
    # --- Arrange ---
    clock = _scripted_clock(TICK_ENTER, TICK_LEAVE, TICK_REENTER, TICK_RELEAVE)
    monkeypatch.setattr(zx_lib_datetime, "monotonic", clock)

    # --- Act ---
    timer = Timer()
    with timer:
        pass
    with timer:
        pass

    # --- Assert ---
    assert timer.delta == DELTA_BOTH


def test_timer_delta_tracks_clock_while_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a scripted monotonic clock advancing inside a running context.
    When: delta is read while running and again after exit.
    Then: both reads reflect the scripted elapsed time.
    """
    # --- Arrange ---
    clock = _scripted_clock(TICK_ENTER, TICK_RUNNING, TICK_RUNNING_END)
    monkeypatch.setattr(zx_lib_datetime, "monotonic", clock)

    # --- Act ---
    timer = Timer()
    with timer:
        running_delta = timer.delta
    stopped_delta = timer.delta

    # --- Assert ---
    assert running_delta == DELTA_RUNNING
    assert stopped_delta == DELTA_RUNNING_TOTAL


def test_timer_nested_contexts_accumulate_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: two Timers interleaved on one scripted monotonic clock.
    When: both contexts close.
    Then: each delta covers only its own scripted span.
    """
    # --- Arrange ---
    clock = _scripted_clock(
        TICK_ENTER,
        TICK_INNER_ENTER,
        TICK_INNER_LEAVE,
        TICK_OUTER_LEAVE,
    )
    monkeypatch.setattr(zx_lib_datetime, "monotonic", clock)

    # --- Act ---
    outer = Timer()
    inner = Timer()
    with outer, inner:
        pass

    # --- Assert ---
    assert inner.delta == DELTA_INNER
    assert outer.delta == DELTA_OUTER


# --- edge cases: bool parsing, timespec pins, DST gap, degenerate periods ---

BERLIN = ZoneInfo("Europe/Berlin")
# 2024-03-31 02:30 does not exist in Europe/Berlin (spring-forward gap).
DST_GAP_LOCAL = datetime(2024, 3, 31, 2, 30)  # noqa: DTZ001
DST_GAP_AS_UTC = datetime(2024, 3, 31, 1, 30, tzinfo=UTC)

TO_STR_TIMESPEC_CASES: tuple[tuple[TimeSpec, str], ...] = (
    ("hours", "2031-05-04T03Z"),
    ("auto", KNOWN_UTC_STR),
    ("microseconds", "2031-05-04T03:02:01.000000Z"),
)
TO_STR_TIMESPEC_IDS = ("hours", "auto", "microseconds")

# offset_s, period, shift, expected_offset_s — negative shifts cross the
# epoch, so the aligned instant lands before 1970-01-01.
EPOCH_CROSSING_CASES: tuple[tuple[int, int, int, int], ...] = (
    (91, 60, -2, -60),
    (30, 60, -1, -60),
    (0, 3600, -1, -3600),
)
EPOCH_CROSSING_IDS = (
    "floors-before-epoch",
    "mid-period-before-epoch",
    "epoch-crosses-back",
)


def test_dt_parse_bool_raises_type_error() -> None:
    """
    Given: a boolean value.
    When: it is passed to dt.parse.
    Then: TypeError is raised — bool is not accepted as an int timestamp.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="expected datetime"):
        dt.parse(True)  # type: ignore[arg-type]


def test_dt_from_str_garbage_raises_parser_error() -> None:
    """
    Given: a string that is not a date at all.
    When: a dt is parsed from it.
    Then: dateutil's ParserError (a ValueError subclass) is raised.
    """

    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ParserError):
        dt.from_str("not a date")


def test_dt_parse_str_with_tz_converts() -> None:
    """
    Given: a naive ISO string and an explicit eastward tz.
    When: it is passed to dt.parse.
    Then: the instant is shifted from the given tz into UTC.
    """

    # --- Arrange ---

    # --- Act ---
    result = dt.parse(KNOWN_NAIVE.isoformat(), tz=OFFSET_EAST)

    # --- Assert ---
    assert result == KNOWN_NAIVE_AS_EAST_UTC


def test_dt_timespec_milliseconds_default_to_str_keeps_fraction() -> None:
    """
    Given: a dt constructed with millisecond precision.
    When: it is serialized with defaults.
    Then: the default timespec comes from the instance and .000 is kept.
    """

    # --- Arrange ---
    instance = dt(KNOWN_UTC, timespec="milliseconds")

    # --- Act ---
    result = instance.to_str()

    # --- Assert ---
    assert result == "2031-05-04T03:02:01.000Z"


def test_dt_iso_with_tz_and_timespec_kwargs(
    frozen_time: time_machine.travel,
) -> None:
    """
    Given: the wall clock frozen at a faker-seeded UTC destination.
    When: dt.iso is called with both tz and timespec.
    Then: the offset form at the requested precision is returned.
    """

    # --- Arrange ---
    expected = datetime.fromtimestamp(
        frozen_time.time_ns() / NANOSECONDS_PER_SECOND,
        tz=OFFSET_EAST,
    ).isoformat(timespec="minutes")

    # --- Act ---
    result = dt.iso(tz=OFFSET_EAST, timespec="minutes")

    # --- Assert ---
    assert result == expected


@pytest.mark.parametrize(
    "timespec,expected",
    TO_STR_TIMESPEC_CASES,
    ids=TO_STR_TIMESPEC_IDS,
)
def test_dt_to_str_timespec_variants(
    timespec: TimeSpec, expected: str,
) -> None:
    """
    Given: a dt at a fixed UTC instant.
    When: it is serialized with a parametrized timespec.
    Then: the exact wire form is pinned for each variant.
    """
    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)

    # --- Act ---
    result = instance.to_str(timespec=timespec)

    # --- Assert ---
    assert result == expected


def test_dt_ensure_tz_dst_gap_local_time_converts() -> None:
    """
    Given: a local wall time inside the Europe/Berlin spring-forward gap.
    When: it is passed through dt.ensure_tz with that tz.
    Then: the pre-transition offset (+01:00) applies and the instant is
        shifted to 01:30 UTC.
    """

    # --- Arrange ---

    # --- Act ---
    result = dt.ensure_tz(DST_GAP_LOCAL, tz=BERLIN)

    # --- Assert ---
    assert result.tzinfo is UTC
    assert result == DST_GAP_AS_UTC


def test_dt_from_ns_negative_one_round_trips() -> None:
    """
    Given: a POSIX timestamp of minus one nanosecond.
    When: a dt is built from it and converted back.
    Then: the value is preserved within float-microsecond precision.
    """

    # --- Arrange ---

    # --- Act ---
    result = dt.from_ns(-1)

    # --- Assert ---
    assert result.to_ns() == pytest.approx(-1, abs=NS_ROUND_TRIP_TOLERANCE)


def test_timer_exception_inside_body_propagates_and_accumulates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a scripted monotonic clock and a Timer whose body raises.
    When: the context exits with the exception.
    Then: the exception propagates and the spent span is accumulated.
    """

    # --- Arrange ---
    clock = _scripted_clock(TICK_ENTER, TICK_LEAVE)
    monkeypatch.setattr(zx_lib_datetime, "monotonic", clock)

    # --- Act / Assert ---
    timer = Timer()
    with pytest.raises(RuntimeError, match="boom"), timer:
        raise RuntimeError("boom")

    # --- Assert ---
    assert timer.delta == DELTA_FIRST


def test_timer_delta_between_exit_and_reenter_returns_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a Timer already exited once, on a scripted monotonic clock.
    When: delta is read between sessions and again inside a re-entry.
    Then: the between read returns only the first span; the running read
        accumulates the new span on top of it.
    """

    # --- Arrange ---
    clock = _scripted_clock(
        TICK_ENTER,
        TICK_LEAVE,
        TICK_REENTER,
        TICK_RUNNING,
        TICK_RUNNING_END,
    )
    monkeypatch.setattr(zx_lib_datetime, "monotonic", clock)

    # --- Act ---
    timer = Timer()
    with timer:
        pass
    between = timer.delta
    with timer:
        running = timer.delta

    # --- Assert ---
    assert between == DELTA_FIRST
    assert running == DELTA_FIRST + (TICK_RUNNING - TICK_REENTER)


@pytest.mark.parametrize(
    "offset_s,period,shift,expected_offset_s",
    EPOCH_CROSSING_CASES,
    ids=EPOCH_CROSSING_IDS,
)
def test_dt_align_to_period_negative_shift_crosses_epoch(
    offset_s: int,
    period: int,
    shift: int,
    expected_offset_s: int,
) -> None:
    """
    Given: a parametrized instant, period, and negative shift.
    When: the dt is aligned to the period.
    Then: the result sits before the epoch at the expected boundary.
    """
    # --- Arrange ---
    instance = dt.from_datetime(EPOCH + timedelta(seconds=offset_s))

    # --- Act ---
    result = instance.align_to_period(period, shift=shift)

    # --- Assert ---
    assert result.dt.tzinfo is UTC
    assert result.dt == EPOCH + timedelta(seconds=expected_offset_s)


def test_dt_get_epoch_index_zero_period_raises_zero_division_error() -> None:
    """
    Given: a dt instance and a zero period.
    When: the epoch index is computed.
    Then: a ZeroDivisionError escapes the floor division.

    pin: current behavior, flagged — period=0 crashes instead of raising
    a domain-specific error.
    """

    # --- Arrange ---
    instance = dt.from_datetime(KNOWN_UTC)

    # --- Act / Assert ---
    with pytest.raises(ZeroDivisionError):
        instance.get_epoch_index(0)
