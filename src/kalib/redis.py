from time import sleep, time

from kalib import exception
from kalib.dataclass import dataclass
from kalib.descriptors import cache, pin

try:
    import redis.exceptions
    from redis import Redis
    from redis.client import PubSub
    from redis.connection import ConnectionPool
    from redis_lock import RedisLock

except ImportError:
    raise ImportError('redis & redis_lock is required, install kalib[redis]')


class Pool(dataclass.config):

    Recoverable = (
        ConnectionRefusedError,
        TimeoutError,
        redis.exceptions.BusyLoadingError,
        redis.exceptions.ClusterDownError,
        redis.exceptions.ConnectionError,
        redis.exceptions.TimeoutError,
        redis.exceptions.TryAgainError)

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

    @pin.cls.here
    def DefaultPool(cls):  # noqa: N802
        return Redis(connection_pool=ConnectionPool(**cls.PoolConfig.Defaults))

    def __init__(
        self,
        /,
        client  = None,
        poll    = 1.0,
        robust  = True,
        signal  = None,
    ):
        self._client  = client
        self._poll    = poll
        self._signal  = signal
        self._robust  = robust

    @pin
    def pool(self):
        return self._client or self.DefaultPool

    @pin
    def condition(self):
        return self._signal or (lambda: True)

    @property
    def on(self):
        return self.condition()

    #

    @property
    def worker(self):
        client = self.pool
        while self._robust:
            try:
                if client.ping():
                    break

            except self.Recoverable as e:
                self.log.warning(f'{exception(e).reason}')

            sleep(self._poll)
            continue
        return client


    def __enter__(self):
        return self.worker

    def __exit__(self, *_, **__): ...


class Event(Pool):

    def __init__(
        self,
        name,
        /,
        blocked = True,
        timeout = None,
        ttl     = None,
        **kw,
    ):
        super().__init__(**kw)
        self.name = name
        self._ttl     = ttl
        self._timeout = timeout
        self._value   = self.integer if blocked else -1

    #

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

    #

    @property
    def updated(self):
        return self._value != self.integer

    def down(self):
        self._value = self.integer

    #

    def changed(
        self,
        timeout  : float | int | None = None, /,
        poll     : float | int | None = None,
        infinite : bool = True,
    ) -> bool:
        counter = 0
        start = time()
        wait = float(self._poll or poll)

        if timeout := (timeout or self._timeout):
            deadline = start + timeout

        condition = self.on
        while condition:
            value = self.integer

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
            if self.integer:
                delta = time() - start
                if counter:
                    self.log.debug(f'{self.name} ({delta:0.2f}s)')
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

    @pin
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
