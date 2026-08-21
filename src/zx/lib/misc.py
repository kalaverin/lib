"""Misc helpers: iterators, process title, sampling hash, runtime probe."""

from __future__ import annotations

import sys
from itertools import cycle
from math import log2
from pathlib import Path
from random import shuffle
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

from setproctitle import setproctitle

from zx.core import required, to_bytes


class Hasher(Protocol):
    """Structural contract for hashing backends (xxhash, hashlib, ...)."""

    def update(self, data: bytes, /) -> None:
        """Feed more data into the hash state."""
        ...

    def hexdigest(self) -> str:
        """Render the digest as a hex string."""
        ...


def cycler[T](array: Iterable[T], /) -> Callable[[], T]:
    """Endless verbatim repeater over the input sequence."""
    iterator = cycle(array)
    return lambda: next(iterator)


def shuffler[T](iterable: Sequence[T], /) -> Callable[[], T]:
    """Endless shuffled repeater; degenerates to cycler below 3 items."""
    if len(iterable) < 3:  # noqa: PLR2004
        return cycler(iterable)

    def iterator() -> Iterator[T]:
        last: list[T] | None = None
        while True:
            array = list(iterable)
            shuffle(array)

            if last and array[0] == last[-1]:
                continue

            yield from array
            last = array

    stream = iterator()
    return lambda: next(stream)


def set_title(
    title: str | None = None,
    short: bool = True,  # kwarg-flag API
) -> None:
    """Set the process title from an explicit title or argv[0]."""
    opts = 0

    if title:
        name = title
    else:
        script = sys.argv[0]
        name = Path(script).stem

        if script.endswith(".py"):
            opts = 1

    setproctitle(
        f"{name} {'' if short else ' '.join(sys.argv[opts:])}".strip(),
    )


def fasthash(path: str | Path, algo: str = "xxhash.xxh128") -> str:
    """Cluster-sampling hash of a file; stable, size- and content-sensitive."""
    hasher: Hasher = required(algo)()  # type: ignore[any]  # required() is untyped

    path = Path(path)
    size = path.stat().st_size

    unit_power = 12  # cluster power, modern is 12, 4096 bytes
    cluster_size = 2**unit_power  # cluster size in bytes

    if size <= 1:
        # tiny files: part-size math is undefined, hash size and content
        with path.open("rb") as fd:
            hasher.update(to_bytes(str(size)))
            hasher.update(fd.read())
        return hasher.hexdigest()

    parts = int(log2(size))  # file parts count
    part_size = int(size / parts)  # every part size
    cluster = 2 ** min(unit_power, int(log2(part_size)))  # read block size

    with path.open("rb") as fd:
        hasher.update(to_bytes(str(size)))
        for no in range(parts):
            # seek to every file part cluster start and read cluster
            fd.seek(int((part_size * no) // cluster_size) * cluster_size)
            hasher.update(to_bytes(fd.read(cluster)))

    return hasher.hexdigest()


def is_python_runtime() -> bool:
    """True when sys.executable points at an existing file."""
    return Path(sys.executable).is_file()
