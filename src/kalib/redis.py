from functools import cached_property
from time import sleep, time

from kalib.loggers import Logging

try:
    from redis_lock import RedisLock
    from redis.client import PubSub

except ImportError:
    raise ImportError('redis_lock is required, install kalib[redis]')


class Flag(Logging.Mixin):

    def __init__(
        self,
        connector,
        name, /,
        wait    = 1.0,
        locked  = False,
        timeout = None,
        signal  = None,
    ):
        self.name = name
        self.client = connector

        self._wait    = wait
        self._signal  = signal
        self._value   = self.value if locked else -1
        self._timeout = timeout

    @cached_property
    def condition(self):
        return self._signal or (lambda: 1)

    #

    def up(self):
        return self.client.incr(self.name)

    @property
    def value(self):
        return int(self.client.get(self.name) or 0)

    def wait(self, timeout=None):
        counter = 0
        start = time()

        if timeout := timeout or self.timeout:
            deadline = start + timeout

        condition = self.condition
        while condition():
            value = self.value

            if value != self._value:
                delta = time() - start
                if counter:
                    self.log.info(
                        f'{self.name}: {self._value} -> {value} '
                        f'({delta:0.2f}s)')
                self._value = value
                return True

            if timeout:
                wait = min(deadline - time(), self._wait)
                if wait < 0:
                    return True

            sleep(wait)
            counter += 1


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
