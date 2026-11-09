import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from functools import cache
from logging import getLogger
from time import monotonic, sleep
from types import TracebackType
from typing import Any, Literal, override

import redis.exceptions
from redis import Redis
from redis.client import PubSub
from redis_lock import RedisLock
from redis_lock.exceptions import LockNotOwnedError

from zx.core import Who, to_bytes
from zx.lib import exception
from zx.prop import pin

logger = getLogger(__name__)

MIN_POLL_INTERVAL = 0.1


@dataclass(frozen=True, slots=True)
class Config:
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None

    socket_timeout: float = 5
    socket_connect_timeout: float = 5
    socket_keepalive: bool = True
    socket_keepalive_options: dict | None = field(default=None, hash=False)

    max_connections: int = 50
    retry_on_timeout: bool = True

    health_check_interval: int = 30
    encoding: str = "utf-8"
    encoding_errors: str = "strict"
    decode_responses: bool = True


@cache
def create_pool(config: Config) -> Redis:
    return Redis(**asdict(config))


class Pool:
    Recoverable = (
        ConnectionRefusedError,
        TimeoutError,
        redis.exceptions.BusyLoadingError,
        redis.exceptions.ClusterDownError,
        redis.exceptions.ConnectionError,
        redis.exceptions.TimeoutError,
        redis.exceptions.TryAgainError,
    )

    def __init__(
        self,
        /,
        client: Redis | None = None,
        config: Config | None = None,
        poll: float = 1.0,
        robust: bool = True,
        signal: Callable[[], bool] | None = None,
    ) -> None:
        self._poll: float = poll
        self._robust: bool = robust
        self._signal: Callable[[], bool] | None = signal

        if client is not None:
            self._client = client
        elif config is not None:
            self._client = create_pool(config)
        else:
            self._client = create_pool(Config())

    @pin
    def condition(self) -> Any | Callable[[], Literal[True]]:
        return self._signal or (lambda: True)

    @property
    def on(self) -> Any:
        return self.condition()

    @property
    def worker(self) -> Redis:
        client: Redis = self._client
        while self._robust and self.on:
            try:
                if client.ping():
                    break

            except self.Recoverable as e:
                logger.warning(exception(e).reason)

            sleep(self._poll)
        return client

    def __enter__(self) -> Redis:
        return self.worker

    def __exit__(self, *_, **__) -> None: ...


class Flag(Pool):
    def __init__(  # noqa: PLR0913, PLR0917
        self,
        name: object,
        /,
        client: Redis | None = None,
        config: Config | None = None,
        poll: float = 1.0,
        robust: bool = True,
        signal: Callable[[], bool] | None = None,
        # behavior
        blocked: bool = True,
        timeout: float | None = None,
        ttl: float = 0,
    ) -> None:
        super().__init__(
            client=client,
            poll=poll,
            robust=robust,
            signal=signal,
            config=config,
        )
        self.name = name if isinstance(name, str) else Who.Is(name)
        self._value: int = self.integer if blocked else -1
        self._ttl: int = int(ttl)
        self._timeout: float | None = timeout

    @pin
    def title(self) -> str:
        return f"{Who.Is(self)}({self.name})"

    def up(self, ttl: int = 0) -> int:
        with self as redis:
            result = redis.incr(self.name)
            if ttl := int(self._ttl or ttl):
                redis.expire(self.name, ttl)
        return result

    def drop(self) -> int:
        with self as redis:
            return redis.delete(self.name)

    @property
    def value(self) -> int | None:
        with self as redis:
            raw = redis.get(self.name)
            return int(raw) if raw is not None else None

    @property
    def integer(self) -> int:
        return int(self.value or 0)

    @property
    def updated(self) -> bool:
        return self._value != self.integer

    def down(self) -> None:
        self._value = self.integer

    def changed(
        self,
        timeout: float | None = None,
        /,
        poll: float | None = None,
        default: bool = True,
    ) -> bool:
        counter = 0
        start = monotonic()

        wait = float(poll or self._poll or MIN_POLL_INTERVAL)
        deadline = start + (timeout or self._timeout or math.inf)

        while self.on:
            value = self.integer

            if not value:
                self._value = value

            elif self._value != value:
                if counter:
                    logger.debug(
                        "value changed",
                        extra={
                            "title": self.title,
                            "before": self._value,
                            "after": value,
                            "delta": monotonic() - start,
                            "tries": counter,
                        },
                    )
                self._value = value
                return True

            remaining = deadline - monotonic()
            if remaining <= 0:
                return default

            sleep(min(remaining, wait))
            counter += 1
        return False

    def non_zero(
        self,
        timeout: float | None = None,
        /,
        poll: float | None = None,
        default: bool = True,
    ) -> bool:

        counter = 0
        start = monotonic()

        wait = float(poll or self._poll or MIN_POLL_INTERVAL)
        deadline = start + (timeout or self._timeout or math.inf)

        while self.on:
            if self.integer:
                logger.debug(
                    "non zero",
                    extra={
                        "title": self.title,
                        "delta": monotonic() - start,
                        "tries": counter,
                    },
                )
                return True

            remaining = deadline - monotonic()
            if remaining <= 0:
                return default

            sleep(min(remaining, wait))
            counter += 1
        return False

    __call__ = changed
    __bool__ = non_zero


class Lock(RedisLock):
    def __init__(
        self,
        connector: Redis,
        name: str,
        /,
        *,
        ttl: int,
        timeout: float | None = None,
        poll: float = 1.0,
        signal: Callable[[], bool] | None = None,
    ) -> None:
        self._signal: Callable[[], bool] | None = signal
        self._poll: float = poll
        super().__init__(
            connector,
            name,
            blocking_timeout=math.inf if timeout is None else timeout,
            expire_timeout=ttl,
        )

    @pin
    def condition(self) -> Any | Callable[[], Literal[True]]:
        return self._signal or (lambda: True)

    def _wait_for_message(self, pubsub: PubSub, timeout: float) -> bool:
        if not self.condition():
            return False

        message = pubsub.get_message(
            ignore_subscribe_messages=True,
            timeout=min(self._poll, timeout),
        )

        if message is None or message["type"] != "message":
            return False

        return to_bytes(message["data"]) == to_bytes(self.unlock_message)

    @override
    def acquire(self) -> bool:
        if self._try_acquire():
            return True

        condition = self.condition
        with self._client.pubsub() as pubsub:
            self._subscribe_channel(pubsub)

            deadline = monotonic() + self._blocking_timeout
            while condition():
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return False

                self._wait_for_message(pubsub, timeout=remaining)
                if self._try_acquire():
                    return True
        return False

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self.release()
        except LockNotOwnedError:
            if exc_type is None:
                raise
            logger.warning("lock lost before release", extra={"lock": self.name})
