from datetime import UTC, datetime, tzinfo
from time import monotonic
from typing import Literal, Self, cast

from dateutil import parser

from zx.core import Who

__all__ = (
    "ISOZString",
    "Timer",
    "dt",
)

type ISOZString = str
type TimeSpec = Literal[
    "auto",
    "hours",
    "minutes",
    "seconds",
    "milliseconds",
    "microseconds",
]

DEFAULT_TZ: tzinfo = UTC
DEFAULT_PRECISION: TimeSpec = "seconds"


def align_datetime_to_index(
    period: int,
    idx: int,
    /,
) -> datetime:
    return datetime.fromtimestamp(idx * period, tz=DEFAULT_TZ)


def get_local_timezone() -> tzinfo:
    result = datetime.now().astimezone().tzinfo
    if result is None:
        raise RuntimeError("failed to get local timezone")
    return result


class dt:  # noqa: N801
    TZ = get_local_timezone()

    @classmethod
    def utc(cls) -> datetime:
        return datetime.now(DEFAULT_TZ)

    @classmethod
    def now(cls) -> datetime:
        return cls.utc().replace(tzinfo=None)

    @classmethod
    def ensure_tz(cls, dt: datetime, tz: tzinfo | None = None) -> datetime:
        if dt.tzinfo is None:
            if tz is not None:
                return dt.replace(tzinfo=tz).astimezone(DEFAULT_TZ)
            msg = f"has no timezone, try to pass tz={cls.TZ}"
            raise ValueError(msg)

        if tz is not None:
            raise ValueError("already has a timezone")
        return dt.astimezone(DEFAULT_TZ)

    # external constructors for datetime, timestamp, and ISO string

    @classmethod
    def from_datetime(cls, dt: datetime, tz: tzinfo | None = None) -> Self:
        return cls(dt=dt, tz=tz)

    @classmethod
    def from_str(cls, value: str, tz: tzinfo | None = None) -> Self:
        dt = cast("datetime", parser.parse(value))
        return cls.from_datetime(dt, tz=tz)

    @classmethod
    def from_ts(cls, value: float, tz: tzinfo | None = None) -> Self:
        dt = datetime.fromtimestamp(value, tz=tz or DEFAULT_TZ)
        return cls.from_datetime(dt)

    @classmethod
    def from_ns(cls, value: float, tz: tzinfo | None = None) -> Self:
        return cls.from_ts(value / 1e9, tz)

    @classmethod
    def parse(
        cls,
        value: datetime | float | str | Self,
        tz: tzinfo | None = None,
    ) -> Self:
        if isinstance(value, cls):
            return value
        if isinstance(value, datetime):
            return cls(value, tz=tz)
        if isinstance(value, str):
            return cls.from_str(value, tz=tz)
        if isinstance(value, bool):
            msg = f"expected datetime | float | str, got {Who.Is(value)}"
            raise TypeError(msg)
        if isinstance(value, float | int):
            return cls.from_ts(value, tz=tz)
        msg = f"expected datetime | float | str, got {Who.Is(value)}"
        raise TypeError(msg)

    def to_datetime(self, tz: tzinfo | None = None) -> datetime:
        return self.dt.astimezone(tz) if tz else self.dt

    def to_str(
        self,
        tz: tzinfo | None = None,
        timespec: TimeSpec | None = None,
    ) -> ISOZString:
        ts = timespec or self.ts
        if tz is None or tz is UTC:
            return f"{self.dt.isoformat(timespec=ts)[:-6]}Z"
        return self.dt.astimezone(tz).isoformat(timespec=ts)

    def to_ts(self, tz: tzinfo | None = None) -> float:
        return self.to_datetime(tz).timestamp()

    def to_ns(self, tz: tzinfo | None = None) -> float:
        return self.to_ts(tz) * 1e9

    # special constructors for current time, timestamp, and ISO string

    @classmethod
    def timestamp(cls) -> float:
        return cls().to_ts()

    @classmethod
    def iso(
        cls,
        tz: tzinfo | None = None,
        timespec: TimeSpec | None = None,
    ) -> str:
        return cls().to_str(tz=tz, timespec=timespec)

    # internal methods and properties

    def __init__(
        self,
        dt: datetime | None = None,
        tz: tzinfo | None = None,
        timespec: TimeSpec = DEFAULT_PRECISION,
    ) -> None:
        self.ts = timespec
        self.dt = self.utc() if dt is None else self.ensure_tz(dt, tz)

    def __str__(self) -> str:
        return self.to_str()

    def __hash__(self) -> int:
        return hash(self.dt)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, dt | datetime):
            return NotImplemented
        return self.dt == (other.dt if isinstance(other, dt) else other)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, dt | datetime):
            return NotImplemented
        return self.dt < (other.dt if isinstance(other, dt) else other)

    def __le__(self, other: object) -> bool:
        if not isinstance(other, dt | datetime):
            return NotImplemented
        return self.dt <= (other.dt if isinstance(other, dt) else other)

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, dt | datetime):
            return NotImplemented
        return self.dt > (other.dt if isinstance(other, dt) else other)

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, dt | datetime):
            return NotImplemented
        return self.dt >= (other.dt if isinstance(other, dt) else other)

    def get_epoch_index(self, period: int) -> int:
        return int(self.dt.timestamp() // period)

    def align_to_period(self, period: int, /, shift: int = 0) -> Self:
        idx = shift + self.get_epoch_index(period)
        return self.__class__(align_datetime_to_index(period, idx))


class Timer:
    def __init__(self) -> None:
        self._spent: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> Self:
        self._start = monotonic()
        return self

    def __exit__(self, *_) -> None:
        self._spent += monotonic() - self._start
        self._start: float = 0.0

    @property
    def delta(self) -> float:
        if not self._start:
            return self._spent
        return self._spent + (monotonic() - self._start)
