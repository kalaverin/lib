from collections.abc import Callable
from functools import lru_cache
from time import sleep, time
from typing import Any, Literal

import redis.exceptions
from redis import Redis
from redis.client import PubSub
from redis.connection import ConnectionPool
from redis_lock import RedisLock

from kain import pin
from kalib import exception


class Pool:

    Recoverable = (
        ConnectionRefusedError,
        TimeoutError,
        redis.exceptions.BusyLoadingError,
        redis.exceptions.ClusterDownError,
        redis.exceptions.ConnectionError,
        redis.exceptions.TimeoutError,
        redis.exceptions.TryAgainError)

    class Config:

        host                     : str = "localhost"
        port                     : int = 6379
        db                       : int = 0
        password                 : str | None = None

        socket_timeout           : float | int = 5
        socket_connect_timeout   : float | int = 5
        socket_keepalive         : bool = True
        socket_keepalive_options : dict | None = None

        max_connections          : int = 50
        retry_on_timeout         : bool = True
        health_check_interval    : int = 30

        encoding                 : str = "utf-8"
        encoding_errors          : str = "strict"
        decode_responses         : int = True

    @pin.cls.here
    def DefaultPool(cls) -> Redis:  # noqa: N802
        return Redis(connection_pool=ConnectionPool(**cls.Config.Defaults))

    def __init__(
        self,
        /,
        client: Redis | None = None,
        poll: float = 1.0,
        robust: bool = True,
        signal: Callable[[], bool] | None = None,
    ) -> None:
        self._client: Redis | None = client
        self._poll: float = poll
        self._robust: bool = robust
        self._signal: Callable[[], bool] | None = signal

    @pin
    def pool(self) -> Callable[[], Redis]:
        return self._client or self.DefaultPool

    @pin
    def condition(self) -> Any | Callable[[], Literal[True]]:
        return self._signal or (lambda: True)

    @property
    def on(self) -> Any:
        return self.condition()


    @property
    def worker(self) -> Redis:
        client: Redis = self.pool
        while self._robust:
            try:
                if client.ping():
                    break

            except self.Recoverable as e:
                self.log.warning(exception(e).reason)

            sleep(self._poll)
        return client

    def __enter__(self) -> Redis:
        return self.worker

    def __exit__(self, *_, **__) -> None: ...


class Event(Pool):

    def __init__(
        self,
        name: str,
        /,
        blocked: bool = True,
        timeout: float = 0.0,
        ttl: float = 0,
        **kw,
    ) -> None:
        super().__init__(**kw)

        self.name: str = name
        self._ttl: int = int(ttl)
        self._timeout: float = float(timeout)
        self._value: int = self.integer if blocked else -1


    def up(self, ttl: int = 0) -> int:
        with self as cli:
            result = cli.incr(self.name)
            if ttl := int(self._ttl or ttl):
                cli.expire(self.name, ttl)
        return result

    def drop(self) -> int:
        with self as cli:
            return cli.delete(self.name)

    @property
    def value(self) -> int:
        with self as cli:
            return cli.get(self.name)

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
        timeout  : float | None = None,
        /,
        poll     : float | None = None,
        infinite : bool = True,
    ) -> bool:
        counter = 0
        start = time()
        wait = float(self._poll or poll)

        if timeout := (timeout or self._timeout):
            deadline = start + timeout

        while self.on:
            value = self.integer

            if not value:
                self._value = value

            elif self._value != value:
                delta = time() - start

                if counter:
                    self.log.debug(
                        f"{self.name}: {self._value} -> {value} "
                        f"({delta:0.2f}s)")
                self._value = value
                return True

            if timeout:
                wait = min(deadline - time(), self._poll)
                if wait < 0:
                    return infinite

            sleep(wait)
            counter += 1

    def non_zero(self) -> bool:
        counter = 0
        start = time()
        wait = self._poll

        while self.on:
            if self.integer:
                delta = time() - start
                if counter:
                    self.log.debug(f"{self.name} ({delta:0.2f}s)")
                return True

            sleep(wait)
            counter += 1

        return False

    __call__ = changed
    __bool__ = non_zero


@lru_cache
def Flag(*args, **kw) -> Event:  # noqa: N802
    return Event(*args, **kw)


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
        deadline = time() + timeout
        condition = self.condition
        while condition():

            message = pubsub.get_message(
                ignore_subscribe_messages=True, timeout=timeout)

            if not message and deadline < time():
                return False

            if (
                message
                and message["type"] == "message"
                and message["data"] == self.unlock_message
            ):
                return True

        return False

    def acquire(self) -> bool:
        timeout = self._blocking_timeout
        if self._try_acquire():
            return True

        condition = self.condition
        with self._client.pubsub() as pubsub:

            self._subscribe_channel(pubsub)
            deadline = time() + timeout

            while condition():
                self._wait_for_message(pubsub, timeout=timeout)

                if deadline < time():
                    return False

                if self._try_acquire():
                    return True

        return False
