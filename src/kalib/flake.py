from datetime import UTC, datetime
from hashlib import sha256
from secrets import randbits
from typing import ClassVar, override

from base58 import b58encode_int

from kain import Who, pin
from kalib.datetime import stamp
from kalib.settings import KubernetesPod

EPOCH: datetime = datetime(year=2026, month=5, day=3, tzinfo=UTC)
POD_ID: bytes = sha256(KubernetesPod().pod.encode()).digest()


class Flake:
    """Generates unique 62-bit IDs based on time, pod ID, and randomness.

    Usage:
        flake_id = Flake()

        id_int = int(flake_id)      # get ID as integer
        id_bytes = bytes(flake_id)  # get ID as raw bytes
        id_str = str(flake_id)      # get ID as string (base58-encoded)
    """

    # runtime constants

    PodId: ClassVar[int] = POD_ID[0] & 0xFF
    Epoch: ClassVar[int] = int(EPOCH.timestamp() * 1e3)

    # bit allocations, ID contains 62 bits total:

    BitsStamp: ClassVar[int] = 41
    BitsPod: ClassVar[int] = 8
    BitsRandom: ClassVar[int] = 13

    # derived constant limits

    MaxStamp: ClassVar[int] = (1 << BitsStamp) - 1
    MaxId: ClassVar[int] = (1 << BitsStamp + BitsPod + BitsRandom) - 1

    # some classmethods

    @staticmethod
    def to_base58(i: int) -> str:
        if i < 0:
            raise ValueError("negative numbers cannot be base58 encoded")
        return b58encode_int(i).decode()

    # instance one-time properties, stamp and stamp-dependent value

    @pin[int]
    def _stamp(self) -> int:
        result: int = int(stamp() * 1e3) - self.Epoch
        if result < self.MaxStamp:
            return result
        raise OverflowError

    @pin[int]
    def _value(self) -> int:
        result: int = (
            (self._stamp << (self.BitsPod + self.BitsRandom))
            | (self.PodId << self.BitsRandom)
            | randbits(self.BitsRandom)
        )

        if result >= self.MaxId:
            raise OverflowError
        return result

    # magic methods

    def __int__(self) -> int:
        return self._value

    @override
    def __str__(self) -> str:
        return self.to_base58(self._value)

    def __bytes__(self) -> bytes:
        return int(self).to_bytes(length=8)  # because we use 62 bits

    @override
    def __repr__(self) -> str:
        # but for representation we show hex representation of bytes
        return f"<{Who.Is(self)}: 0x{bytes(self).hex()} -> {self}>"
