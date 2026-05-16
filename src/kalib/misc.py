import sys
from datetime import UTC, datetime, timedelta
from itertools import cycle
from math import log2
from pathlib import Path
from random import shuffle
from time import monotonic, time

from setproctitle import setproctitle

from kain import (
    Missing,
    class_property,
    required,
    to_bytes,
)

Nothing = Missing()


def Now(tz=True, /, **kw):  # noqa: N802
    if tz:
        result = datetime.now(tz=UTC if tz is True else tz)
    else:
        result = datetime.utcnow()  # noqa: DTZ003

    return (result + timedelta(**kw)) if kw else result


def stamp(**kw):
    return Now(**kw).replace(tzinfo=None).timestamp()


class Timer:

    @class_property
    def now(cls):
        return time()

    @class_property
    def stamp(cls):
        return stamp()

    def __init__(self):
        self.spent = None
        self._start = monotonic()

    def __enter__(self):
        self._start = monotonic()

    def __exit__(self, *args):
        self.spent = monotonic() - self._start

    @property
    def delta(self):
        return monotonic() - self._start if self._start else 0.0


def cycler(array):
    iterator = cycle(array)
    return lambda: next(iterator)


def shuffler(iterable):
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

    if title:
        name = title
    else:
        script = sys.argv[0]
        if script.endswith(".py"):
            opts = 1
            name = Path(script).stem
        else:
            name = Path(sys.executable).stem

    setproctitle(f"{name} {'' if short else ' '.join(sys.argv[opts:])}".strip())


def fasthash(path, algo="xxhash.xxh128"):
    hasher = required(algo)()

    path = Path(path)
    size = path.stat().st_size

    unit_power = 12  # cluster power, modern is 12, 4096 bytes
    cluster_size = 2 ** unit_power  # cluster size in bytes

    parts = int(log2(size))  # file parts count
    part_size = int(size / parts)  # every part size
    cluster = 2 ** min(12, int(log2(part_size)))  # read block size

    with path.open("rb") as fd:
        hasher.update(to_bytes(str(size)))
        for no in range(parts):

            # seek to every file part cluster start and read cluster
            fd.seek(int((part_size * no) // cluster_size) * cluster_size)
            hasher.update(to_bytes(fd.read(cluster)))

    return hasher.hexdigest()


def is_python_runtime():
    return Path(sys.executable).is_file()
