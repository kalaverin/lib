import sys
from datetime import datetime, timedelta, timezone
from itertools import cycle
from math import log2
from pathlib import Path
from random import shuffle
from sys import version_info
from time import monotonic, time

from kain import (
    Is,
    Missing,
    cache,
    class_property,
    proxy_to,  # noqa: F401
    required,
    to_bytes,
)

Nothing = Missing()


@cache
def get_toml_loader():
    if version_info >= (3, 11):
        from tomllib import load  # noqa: PLC0415
    else:
        try:
            from tomli import load  # noqa: PLC0415
        except ImportError as e:
            raise ImportError('install "tomli" or upgrade to Python 3.11+') from e
    return load


def Now(tz=True, /, **kw):  # noqa: N802
    """Return datetime object with or without timezone.

    When tz passed, it's used, when not tz — timezone-naive datetime returned.

    Also keywargs can be passed to timedelta, so you can get datetime in the future.
    """

    if tz:
        result = datetime.now(tz=timezone.utc if tz is True else tz)
    else:
        result = datetime.utcnow()  # noqa: DTZ003

    return (result + timedelta(**kw)) if kw else result


def stamp(**kw):
    """Return timestamp with timedelta keywargs with timezone support."""
    return Now(**kw).replace(tzinfo=None).timestamp()


class Timer:
    """Context manager to measure time spent in block."""

    @class_property
    def now(cls):
        return time()

    @class_property
    def stamp(cls):
        return stamp()

    def __init__(self):
        self._start = None
        self.spent = None

    def __enter__(self):
        self._start = monotonic()

    def __exit__(self, *args):
        self.spent = monotonic() - self._start

    @property
    def delta(self):
        return monotonic() - self._start if self._start else 0.0


def to_tuple(x):
    return tuple(x or ()) if Is.iterable(x) else (x,)


def toml_read(path):
    loader = get_toml_loader()
    with Path(path).open('rb') as fd:
        return loader(fd)


def yaml_read(path):
    loader = required('yaml.safe_load')
    with Path(path).open('rb') as fd:
        return loader(fd.read())


def cycler(array):
    """Return a function that cycles through the given array."""
    iterator = cycle(array)
    return lambda: next(iterator)


def shuffler(iterable):
    """Return a function that shuffles the given array."""

    if len(iterable) < 3:  # noqa: PLR2004
        return cycler(iterable)

    def iterator():
        last = None
        while True:
            array = list(iterable)
            shuffle(array)

            if last and array[0] is last[-1]:
                continue

            yield from array
            last = array

    iterator = iterator()
    return lambda: next(iterator)


def set_title(title=None, short=True):

    opts = 0
    func = required('setproctitle.setproctitle')

    if title:
        name = title
    else:
        script = sys.argv[0]
        if script.endswith('.py'):
            opts = 1
            name = Path(script).stem
        else:
            name = Path(sys.executable).stem

    func(f"{name} {'' if short else ' '.join(sys.argv[opts:])}".strip())


@cache(2 ** 10)
def fasthash(path, algo='xxhash.xxh128'):
    """Generate fast cache by file content according to sector size."""

    hasher = required(algo)()

    path = Path(path)
    size = path.stat().st_size

    unit_power = 12  # cluster power, modern is 12, 4096 bytes
    cluster_size = 2 ** unit_power  # cluster size in bytes

    parts = int(log2(size))  # file parts count
    part_size = int(size / parts)  # every part size
    cluster = 2 ** min(12, int(log2(part_size)))  # read block size

    with path.open('rb') as fd:
        hasher.update(to_bytes(str(size)))
        for no in range(parts):

            # seek to every file part cluster start and read cluster
            fd.seek(int((part_size * no) // cluster_size) * cluster_size)
            hasher.update(to_bytes(fd.read(cluster)))

    return hasher.hexdigest()


def is_python_runtime():
    """Checks if current runtime is Python, not Nuitka or PyInstaller."""
    return Path(sys.executable).is_file()
