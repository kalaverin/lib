from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import cache
from logging import getLogger
from time import monotonic, sleep
from typing import Any, Literal, override

import redis.exceptions
from redis import Redis
from redis.client import PubSub
from redis_lock import RedisLock

from zx.core import Who
from zx.lib import exception
from zx.prop import pin

logger = getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Config:
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None

    socket_timeout: float = 5
    socket_connect_timeout: float = 5
    socket_keepalive: bool = True
    socket_keepalive_options: dict | None = None

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
        while self._robust:
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
        timeout: float = 0.0,
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
        self._timeout: float = float(timeout)

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
        infinite: bool = True,
    ) -> bool:
        counter = 0
        start = monotonic()
        wait = float(poll or self._poll or 0.1)

        if timeout := (timeout or self._timeout):
            deadline = start + timeout

        while self.on:
            value = self.integer

            if not value:
                self._value = value

            elif self._value != value:
                delta = monotonic() - start
                if counter:
                    logger.debug(
                        "value changed",
                        extra={
                            "title": self.title,
                            "before": self._value,
                            "after": value,
                            "delta": delta,
                        },
                    )
                self._value = value
                return True

            if timeout:
                wait = min(deadline - monotonic(), self._poll)
                if wait < 0:
                    return infinite

            sleep(wait)
            counter += 1
        return False

    def non_zero(self) -> bool:
        counter = 0
        start = monotonic()
        wait = self._poll

        while self.on:
            if self.integer:
                delta = monotonic() - start
                if counter:
                    logger.debug(
                        "non zero",
                        extra={
                            "title": self.title,
                            "delta": delta,
                        },
                    )
                return True
            sleep(wait)
            counter += 1
        return False

    __call__ = changed
    __bool__ = non_zero


class Lock(RedisLock):
    def __init__(
        self,
        connector,
        name: str,
        /,
        timeout: int = 0,
        signal: Callable[[], bool] | None = None,
    ) -> None:
        self.name: str = name
        self.client: Redis = connector
        self._signal: Callable[[], bool] | None = signal
        self._timeout: int = timeout or 86400 * 365 * 10

        super().__init__(connector, name, blocking_timeout=self._timeout)

    @pin
    def condition(self) -> Any | Callable[[], Literal[True]]:
        return self._signal or (lambda: True)

    def _try_acquire(self) -> bool:
        return self._client.set(self.name, self.token, nx=True, ex=self._ex)

    def _wait_for_message(self, pubsub: PubSub, timeout: int) -> bool:
        deadline = monotonic() + timeout
        condition = self.condition
        while condition():
            if deadline < monotonic():
                return False

            message = pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=timeout,
            )

            if message and message["type"] == "message":
                data = message["data"]
                expected = self.unlock_message
                if isinstance(data, bytes):
                    data = data.decode()
                if isinstance(expected, bytes):
                    expected = expected.decode()
                if data == expected:
                    return True

        return False

    @override
    def acquire(self) -> bool:
        timeout = self._blocking_timeout
        if self._try_acquire():
            return True

        condition = self.condition
        with self._client.pubsub() as pubsub:
            self._subscribe_channel(pubsub)
            deadline = monotonic() + timeout

            while condition():
                self._wait_for_message(pubsub, timeout=timeout)

                if deadline < monotonic():
                    return False

                if self._try_acquire():
                    return True

        return False
