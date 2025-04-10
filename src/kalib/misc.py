import sys
from datetime import datetime, timedelta, timezone
from functools import partial
from itertools import cycle
from math import log2
from operator import attrgetter, methodcaller
from pathlib import Path
from random import shuffle
from sys import stderr, stdin, stdout, version_info
from time import monotonic, time

from kalib.classes import Missing
from kalib.descriptors import Property, cache
from kalib.functions import to_bytes
from kalib.internals import (
    Who,
    class_of,
    get_attr,
    is_class,
    is_iterable,
)
from kalib.internals import sourcefile as generic_sourcefile

Nothing = Missing()


@cache
def get_importer():
    # avoid circular imports
    from kalib.importer import required
    return required


@cache
def get_toml_loader():
    if version_info >= (3, 11):
        from tomllib import load
    else:
        try:
            from tomli import load
        except ImportError as e:
            raise ImportError('install "tomli" or upgrade to Python 3.11+') from e
    return load


@cache
def get_yaml_loader():
    return get_importer()('yaml.safe_load')


def is_tty():
    """Return True if all standard streams are tty."""

    if not getattr(sys, 'frozen', False): # nuitka compiler checks this
        return all(map(methodcaller('isatty'), (stderr, stdin, stdout)))


tty = is_tty()


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

    @Property.Class
    def now(cls):
        return time()

    @Property.Class
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


def lazy_proxy_to(  # noqa: PLR0915
    *mapping,
    getter  = attrgetter,
    default = Nothing,
    pre     = None,
    safe    = True,
):
    if isinstance(mapping[-1], str):
        bind = Property.Cached

    elif mapping[-1] is None:
        bind, mapping = None, mapping[:-1]

    else:
        bind, mapping = mapping[-1], mapping[:-1]


    def binder(cls):  # noqa: PLR0915

        try:
            fields = cls.__proxy_fields__
        except AttributeError:
            fields = []
            cls.__proxy_fields__ = fields

        pivot, mapping_list = mapping[0], mapping[1:]

        if not is_class(cls):
            msg = f"{Who.Is(cls)} isn't a class"
            raise TypeError(msg)

        if (
            not mapping_list or
            (len(mapping_list) == 1 and not isinstance(mapping_list[0], str))
        ):
            raise ValueError(f'empty {mapping_list=} for {pivot=}')

        for method in mapping_list:

            if safe and not method.startswith('_') and get_attr(cls, method):
                msg = (
                    f'{Who(cls)} already exists {method!a}: '
                    f'{get_attr(cls, method)}')
                raise TypeError(msg)

            def lazy_call(method, node):
                if not isinstance(pivot, str):
                    try:
                        return getattr(pivot, method)
                    except AttributeError as e:
                        msg = (
                            f'{Who(node)}.{method} {Who.Name(getter)[:4]}-proxied -> '
                            f"{Who(pivot)}.{method}, but last isn't exists")
                        raise TypeError(msg) from e

                try:
                    entity = getattr(node, pivot)
                except AttributeError as e:
                    msg = (
                        f'{Who(node)}.{method} {Who.Name(getter)[:4]}-proxied -> '
                        f'{Who(node)}.{pivot}.{method}, but '
                        f"{Who(node)}.{pivot} isn't exists")
                    raise TypeError(msg) from e

                if entity is None:
                    msg = (
                        f'{Who(node)}.{method} {Who.Name(getter)[:4]}-proxied -> '
                        f'{Who(node)}.{pivot}.{method}, but current '
                        f'{Who(node)}.{pivot} is None')

                    if default is Nothing:
                        raise TypeError(msg)

                    msg = f'{msg}; return {Who.Is(default)}'
                    cls.log.verbose(msg)
                    attribute = default

                else:
                    try:
                        attribute = getter(method)(entity)

                    except (AttributeError, KeyError) as e:
                        msg = (
                            f'{Who(node)}.{method} {Who.Name(getter)[:4]}-proxied -> '
                            f"{Who(node)}.{pivot}.{method}, but isn't exists "
                            f"('{method}' not in {Who(node)}.{pivot}): {Who.Is(entity)}")

                        if default is Nothing:
                            raise class_of(e)(msg) from e

                        msg = f'{msg}; return {Who.Is(default)}'
                        cls.log.verbose(msg)
                        attribute = default

                return partial(pre, attribute) if pre else attribute

            lazy_call.__name__ = method
            lazy_call.__qualname__ = f'{pivot}.{method}'

            if bind is None:
                node = cls.__dict__[pivot]
                try:
                    value = node.__dict__[method]
                except KeyError:
                    value = getattr(node, method)
            else:
                wrap = partial(lazy_call, method)
                wrap.__name__ = method
                wrap.__qualname__ = f'{pivot}.{method}'
                value = bind(wrap)

            fields.append(method)
            setattr(cls, method, value)
            cls.__proxy_fields__.sort()

        return cls
    return binder


def sourcefile(something, template=None):
    """Return sourcefile for object if it's reachable with format template"""
    source = generic_sourcefile(something)
    if not source:
        return ''
    elif not template:
        return str(source)
    return ' ' + (template % source)


def to_tuple(x):
    return tuple(x or ()) if is_iterable(x) else (x,)


def toml_read(path):
    loader = get_toml_loader()
    with Path(path).open('rb') as fd:
        return loader(fd)


def yaml_read(path):
    loader = get_yaml_loader()
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
    func = get_importer()('setproctitle.setproctitle')

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

    hasher = get_importer()(algo)()

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
