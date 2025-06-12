from functools import cached_property
from time import sleep, time

from kalib.dataclass import dataclass
from kalib.descriptors import Property, cache

try:
    from redis import Redis
    from redis.client import PubSub
    from redis.connection import ConnectionPool
    from redis_lock import RedisLock

except ImportError:
    raise ImportError('redis_lock is required, install kalib[redis]')


class Pool(dataclass.config):

    class PoolConfig(dataclass):
        host                     : str = 'localhost'
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
        encoding                 : str = 'utf-8'
        encoding_errors          : str = 'strict'
        decode_responses         : int = True

    @Property.Class.Parent
    def DefaultPool(cls):  # noqa: N802
        return Redis(connection_pool=ConnectionPool(**cls.PoolConfig.Defaults))


class Event(Pool):

    def __init__(
        self,
        name,
        /,
        client  = None,
        poll    = 1.0,
        blocked = True,
        timeout = None,
        signal  = None,
        ttl     = None,
    ):
        self.name = name
        self._ttl     = ttl
        self._client  = client
        self._poll    = poll
        self._signal  = signal
        self._timeout = timeout
        self._value   = self.value if blocked else -1

    @cached_property
    def client(self):
        return self._client or self.DefaultPool

    @cached_property
    def condition(self):
        return self._signal or (lambda: 1)

    #

    def up(self, ttl: int = 0) -> int:
        result = self.client.incr(self.name)
        if ttl := int(self._ttl or ttl):
            self.client.expire(self.name, ttl)
        return result

    def drop(self) -> int:
        return self.client.delete(self.name)

    @property
    def value(self) -> int:
        return int(self.client.get(self.name) or 0)

    @property
    def on(self):
        return self.condition()

    @property
    def updated(self):
        return self._value != self.value

    def down(self):
        self._value = self.value

    #

    def changed(
        self,
        poll     : float | int | None = None,
        timeout  : float | int | None = None, /,
        infinite : bool = True,
    ) -> bool:
        counter = 0
        start = time()
        wait = float(self._poll or poll)

        if timeout := (timeout or self._timeout):
            deadline = start + timeout

        condition = self.on
        while condition:
            value = self.value

            if not value:
                self._value = value

            elif self._value != value:
                delta = time() - start

                if counter:
                    self.log.debug(
                        f'{self.name}: {self._value} -> {value} '
                        f'({delta:0.2f}s)')
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
            if self.value:
                delta = time() - start
                if counter:
                    self.log.info(f'{self.name} ({delta:0.2f}s)')
                return True

            sleep(wait)
            counter += 1

    __call__ = changed
    __bool__ = non_zero


@cache
def Flag(*args, **kw):  # noqa: N802
    return Event(*args, **kw)


class Lock(RedisLock):

    def __init__(
        self,
        connector,
        name, /,
        timeout = None,
        signal  = None,
    ):
        self.name = name
        self.client = connector
        self._signal = signal
        self._timeout = timeout or 86400 * 365 * 10
        super().__init__(connector, name, blocking_timeout=self._timeout)

    @cached_property
    def condition(self):
        return self._signal or (lambda: 1)

    #

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

            elif (
                message
                and message['type'] == 'message'
                and message['data'] == self.unlock_message
            ):
                return True

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

                elif self._try_acquire():
                    return True
