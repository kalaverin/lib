import sys
from contextlib import suppress
from functools import cache
from importlib import import_module
from inspect import ismodule
from os import sep
from pathlib import Path

from kalib.functions import to_ascii
from kalib.internals import Who, iter_stack, unique
from kalib.loggers import Logging

__all__ = 'add_path', 'optional', 'required'

logger = Logging.get(__name__)


IGNORED_OBJECT_FIELDS = {
    '__builtins__', '__cached__', '__doc__', '__file__', '__loader__',
    '__name__', '__package__', '__path__', '__spec__'}
PACKAGES_MAP = {'magic': 'python-magic', 'git': 'gitpython'}


@cache
def get_module(path):

    chunks = path.split('.')
    count = len(chunks) + 1

    if count == 2:  # noqa: PLR2004
        with suppress(ModuleNotFoundError):
            return import_module(path), ()

    for i in range(1, count):
        chunk = '.'.join(chunks[:count - i])
        with suppress(ModuleNotFoundError):
            return import_module(chunk), tuple(chunks[count - i:])

    msg = f"ImportError: {path} ({chunk!a} isn't exists)"
    raise ImportError(msg)


def get_child(path, parent, child):
    if ismodule(parent):
        __import__(parent.__name__, globals(), locals(), [str(child)])

    if not hasattr(parent, child):
        from kalib.misc import sourcefile

        if not ismodule(parent):
            raise ImportError(
                f"{path} (object {Who(parent)!a} hasn't attribute "
                f"{child!a}{sourcefile(parent, 'in %a')})")

        if not set(dir(parent)) - IGNORED_OBJECT_FIELDS:
            chunk = f'{Who(parent)}.{child}'
            raise ImportError(
                f'{path} (from partially initialized module '
                f'{chunk!a}, most likely due to a circular import'
                f'{sourcefile(parent, "from %a")}) or just not found')

        raise ImportError(
            f"{path} (module {Who(parent)!a} hasn't member {child!a}"
            f"{sourcefile(parent, 'in %a')})")

    return getattr(parent, child)


def import_object(path, something=None):
    if path is something is None:
        raise TypeError('all arguments is None')

    if isinstance(path, str | bytes):
        path = to_ascii(path)

    if not isinstance(path, str):
        if something is None:
            msg = (
                f"{Who.Is(path)} isn't str, but "
                f'second argument (import path) is None')
            raise TypeError(msg)
        path, something = something, path

    logger.debug(f'lookup: {path}')

    if something:
        locator = f'{Who(something)}.{path}'
        sequence = path.split('.')

    else:
        locator = str(path)
        something, sequence = get_module(path)

        if something is None:
            raise ImportError(f"{path} (isn't exists?)")

    if not sequence:
        logger.debug(f'import path: {Who(something)}')

    else:
        logger.debug(
            f'split path: {Who(something)} '
            f'(module) -> {".".join(sequence)} (path)')

    for name in sequence:
        something = get_child(locator, something, name)

    logger.debug('load ok: %s', path)
    return something


@cache
def cached_import(*args, **kw):
    return import_object(*args, **kw)


def required(path, *args, **kw):
    """For dynamic import any from any, usage:

    required('kalib.importer.required')  # import kalib.importer and return function

    """

    throw = kw.pop('throw', True)
    quiet = kw.pop('quiet', False)
    default = kw.pop('default', None)

    try:
        try:
            return cached_import(path, *args, **kw)

        except TypeError:
            return import_object(path, *args, **kw)

    except ImportError as e:

        if not quiet or throw:
            msg = f"couldn't import required({path=}, *{args=}, **{kw=})"

            base = path.split('.', 1)[0]
            if base not in sys.modules:
                package = (PACKAGES_MAP.get(base) or base).replace('_', '-')
                msg = f'{msg}; (need extra {package=}?)'

            if not quiet:
                Logging.Default.warning(msg, trace=True)

            if throw:
                raise ImportError(msg) from e

    return default


def optional(path, *args, **kw):
    kw.setdefault('quiet', True)
    kw.setdefault('throw', False)
    return required(path, *args, **kw)


sort = optional('natsort.natsorted', quiet=True, default=sorted)


def get_path(path, root=None):  # noqa: PLR0912

    if root is None:

        base = Path(__file__).stem
        for file in iter_stack(1, offset=1):
            if Path(file).stem != base:
                break
        root = Path(file).parent

    if isinstance(root, Path | str):
        root = Path(root)
    else:
        raise TypeError(
            f'root={root!r} can be str | {Who(Path)} | None, not {Who.Is(root)}')

    spath = str(path).strip('/')

    if set(spath) == {'.'}:
        dots = len(spath) - 2
        if dots == -1:
            return path

        path = root.resolve()
        for _ in range(dots + 1):
            path = path.parent

        return path.resolve()

    elif spath.startswith('../'):
        return (root / path).resolve()

    elif sep in path and ('../' not in spath and '/..' not in spath):
        try:
            idx = str(root).index(str(path))
        except ValueError as e:
            raise ValueError(f'{path=} not found in {root=}') from e
        return Path(str(root)[:idx])

    subdir = str(root)
    while subdir != sep:

        future = Path(subdir)
        subdir = str(future.parent)

        if path == future.name:
            return future

    raise ValueError(f'{path=} not found in {root=}')


def add_path(path, **kw):
    """Add resolved path to sys.path and return Path object, usage:

    add_path('..')      # ../
    add_path('...')     # ../../
    add_path('....')    # ../../../

    app_path(__file__)  # add current file directory to sys.path
    app_path('/etc/hosts')  # add /etc to sys.path, hosts is file

    """

    path = Path(path)
    request = path

    if path.is_file():
        path = path.resolve().parent

    elif not (str(path).startswith(sep) or path == path.resolve()):
        root = get_path(path, **kw)
        if not root:
            raise ValueError(f'{path=} not found, {logger.Args(**kw)}')
        path = root if str(path).startswith('.') else (root / path).resolve()

    if path not in sys.path:
        sys.path.append(str(path.resolve()))
        sys.path = list(unique(sys.path))
        exists = path.is_dir()
        logger.info(f'path {request} resolved to {path}, {exists=}')
    return path
