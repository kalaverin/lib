from datetime import UTC, datetime, timedelta
from time import monotonic

from kain import class_property


def now(**kw: float) -> datetime:
    result = datetime.now(UTC)
    return (result + timedelta(**kw)) if kw else result


def stamp(**kw: float) -> float:
    return now(**kw).timestamp()


def isotime(**kw: float) -> str:
    return format_datetime(now(**kw))


def format_datetime(dt: datetime) -> str:
    """Format datetime to ISO 8601 string with seconds precision.

    The datetime is converted to UTC and formatted with 'Z' suffix
    instead of '+00:00' for cleaner representation.

    Args:
        dt: The datetime with timezone to format.

    Returns:
        The formatted datetime string: 2026-03-26T12:14:56Z

    Raises:
        ValueError: If the datetime is not timezone-aware.

    Example:
        >>> from datetime import datetime, UTC
        >>> dt = datetime(2026, 3, 26, 12, 14, 56, tzinfo=UTC)
        >>> format_datetime(dt)
        '2026-03-26T12:14:56Z'
    """

    # timezone-aware datetimes are required for unambiguous formatting
    if not dt.tzinfo:
        raise ValueError("Datetime must be timezone-aware")

    # always convert taken datetime to UTC
    result = dt.astimezone(UTC).isoformat(timespec="seconds")

    if not result.endswith("+00:00"):
        msg = f"Unexpected datetime format: {result}"
        raise ValueError(msg)

    return f"{result[:-6]}Z"  # replace '+00:00' with 'Z'


class Timer:

    @class_property
    def ISO(cls) -> str:
        return isotime()

    @class_property
    def now(cls) -> datetime:
        return now()

    @class_property
    def stamp(cls) -> float:
        return stamp()

    def __init__(self) -> None:
        self._spent: float = 0.0
        self._start: float = monotonic()

    def __enter__(self):
        self._start = monotonic()

    def __exit__(self, *_) -> None:
        self._spent = monotonic() - self._start

    @property
    def delta(self) -> float:
        return monotonic() - self._start if self._start else 0.0


def get_from_epoch_start_offset(
    period: int,
    dt: datetime,
    /,
) -> int:
    """Calculate the period index from epoch start for a given datetime.

    Args:
        period: The period duration in seconds.
        dt: The datetime to convert to period index.

    Returns:
        The period index (number of periods since epoch).

    Example:
        >>> from datetime import datetime, UTC
        >>> dt = datetime(2026, 3, 26, 12, 0, 0, tzinfo=UTC)
        >>> get_from_epoch_start_offset(300, dt)  # 5-minute periods
        10523520
    """
    return int(dt.timestamp() // period)


def make_aligned_datetime_from_offset(
    period: int,
    idx: int,
    /,
) -> datetime:
    """Create a datetime from a period index.

    Args:
        period: The period duration in seconds.
        idx: The period index (number of periods since epoch).

    Returns:
        The datetime corresponding to the period index.

    Example:
        >>> dt = make_aligned_datetime_from_offset(300, 10523520)
        >>> print(dt.isoformat())
        '2026-03-26T12:00:00+00:00'
    """
    return datetime.fromtimestamp(idx * period, tz=UTC)


def align_datetime(
    period: int,
    dt: datetime,
    /,
    shift: int = 0,
) -> datetime:
    """Align a datetime to period boundaries.

    Rounds the datetime down to the nearest period boundary,
    optionally with a shift in period index.

    Args:
        period: The period duration in seconds (e.g., 300 for 5 minutes).
        dt: The datetime to align.
        shift: Optional shift in period indices (default: 0).

    Returns:
        The aligned datetime at the period boundary.

    Example:
        >>> from datetime import datetime, UTC
        >>> dt = datetime(2026, 3, 26, 12, 14, 37, tzinfo=UTC)
        >>> aligned = align_datetime(300, dt)  # Align to 5-minute boundary
        >>> print(aligned.isoformat())
        '2026-03-26T12:10:00+00:00'
        >>> # With shift of -1, get previous period
        >>> previous = align_datetime(300, dt, shift=-1)
        >>> print(previous.isoformat())
        '2026-03-26T12:05:00+00:00'
    """
    idx = shift + get_from_epoch_start_offset(period, dt)
    return make_aligned_datetime_from_offset(period, idx)
