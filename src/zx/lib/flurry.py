from __future__ import annotations

import os
import socket
from datetime import UTC, datetime
from functools import cached_property
from hashlib import sha256
from secrets import randbits
from typing import ClassVar, Self, override

from base58 import b58decode_int, b58encode_int

from zx.core import Who
from zx.lib.datetime import dt

EPOCH: datetime = datetime(year=2025, month=1, day=1, tzinfo=UTC)


def flurry_seed() -> bytes:
    raw = os.environ.get("FLURRY_SEED") or socket.gethostname()
    return sha256(raw.encode()).digest()


MACHINE_ID: bytes = flurry_seed()


class Flurry:
    # runtime constants

    Id: ClassVar[int] = MACHINE_ID[0] & 0xFF
    Epoch: ClassVar[int] = int(EPOCH.timestamp() * 1e3)

    # bit allocations, ID contains 62 bits total:

    BitsStamp: ClassVar[int] = 41
    BitsPod: ClassVar[int] = 8
    BitsRandom: ClassVar[int] = 13

    # derived constant limits

    MaxStamp: ClassVar[int] = (1 << BitsStamp) - 1
    MaxId: ClassVar[int] = (1 << BitsStamp + BitsPod + BitsRandom) - 1
    BytesLength: ClassVar[int] = 8

    # some classmethods

    def to_bytes(self) -> bytes:
        return bytes(self)

    def to_int(self) -> int:
        return int(self)

    def to_str(self) -> str:
        return str(self)

    @classmethod
    def from_bytes(cls, value: bytes) -> Self:
        if len(value) != cls.BytesLength:
            msg = f"expected {cls.BytesLength} bytes, got {len(value)}"
            raise ValueError(msg)
        return cls(int.from_bytes(value, byteorder="big"))

    @classmethod
    def from_int(cls, value: int) -> Self:
        return cls(value)

    @classmethod
    def from_str(cls, text: str) -> Self:
        trimmed = text.strip()
        if not trimmed:
            raise ValueError("empty Flurry id")
        try:
            parsed = b58decode_int(trimmed.encode())
        except ValueError as e:
            msg = f"invalid Flurry id: {trimmed!r}"
            raise ValueError(msg) from e
        return cls(parsed)

    @classmethod
    def parse(cls, value: str | int | bytes | Self) -> Self:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls.from_str(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return cls.from_int(value)
        if isinstance(value, bytes):
            return cls.from_bytes(value)
        msg = f"expected str, int, or bytes, got {Who.Is(value)}"
        raise TypeError(msg)

    def __init__(self, value: int | None = None) -> None:
        if value is not None:
            if value < 0 or value > self.MaxId:
                msg = f"Flurry value out of range: {value}"
                raise ValueError(msg)
            # bypass cached_property generation
            object.__setattr__(self, "_value", value)

    # instance one-time properties, stamp and stamp-dependent value

    @cached_property[int]
    def _stamp(self) -> int:
        result: int = int(dt.timestamp() * 1e3) - self.Epoch
        if result < self.MaxStamp:
            return result
        raise OverflowError

    @cached_property[int]
    def _value(self) -> int:
        result: int = (
            (self._stamp << (self.BitsPod + self.BitsRandom))
            | (self.Id << self.BitsRandom)
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
        value = int(self)
        if value < 0:
            raise ValueError("negative numbers cannot be base58 encoded")
        return b58encode_int(i=value).decode()

    def __bytes__(self) -> bytes:
        return int(self).to_bytes(length=8)  # because we use 62 bits

    @override
    def __repr__(self) -> str:
        # but for representation we show hex representation of bytes
        return f"<{Who.Addr(self)} -> {self}>"
