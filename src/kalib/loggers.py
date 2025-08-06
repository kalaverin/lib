import logging as syslog
import traceback
from argparse import Namespace
from asyncio import ensure_future, iscoroutinefunction
from collections import OrderedDict, defaultdict
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from functools import wraps as base_wraps
from hashlib import md5
from inspect import (
    stack,
)
from itertools import filterfalse
from logging import CRITICAL, DEBUG, ERROR, INFO, NOTSET, WARNING
from logging import Logger as BaseLogger
from os import getenv, sep
from os.path import splitext
from pathlib import Path
from re import match, search
from sys import _getframe, argv, getrefcount, modules
from sysconfig import get_paths
from time import time
from traceback import extract_stack, format_stack
from typing import ClassVar
from weakref import ref

from charded import Str
from kain import (
    Is,
    Monkey,
    Nothing,
    Who,
    cache,
    class_property,
    optional,
    pin,
    to_bytes,
    unique,
)
from kain.internals import WinNT, simple_repr

from kalib.misc import toml_read

NOTICE    = INFO + 5
DEPRECATE = INFO - 3
VERBOSE   = INFO - 6

CUSTOM_LEVELS = {
    CRITICAL  : 'CRIT',
    DEPRECATE : 'DEPR',
    NOTICE    : 'NOTE',
    NOTSET    : 'NONE',
    VERBOSE   : 'VERB',
    WARNING   : 'WARN',
}

CUSTOM_NAMES = {
    CRITICAL  : 'Critical',
    DEPRECATE : 'Deprecate',
    NOTICE    : 'Notice',
    NOTSET    : 'NotSet',
    VERBOSE   : 'Verbose',
    WARNING   : 'Warning',
}


DEDUP_ORDER_SIZE = 2 ** 16
DEFAULT_LOG_CONFIG = 'logging.toml'
RE_TYPE_ERROR = (
    r'TypeError: (.+)\(\) takes (\d+) positional '
    r'argument but (\d+) were given')

#

@cache
def trim_module_path(full):
    dirs = get_paths()

    path = str(full)
    if WinNT:
        path = path.lower()

    for scheme, reason in (
        ('stdlib', True),
        ('purelib', False),
        ('platlib', False),
        ('platstdlib', True),
    ):
        subdir = dirs[scheme]
        if WinNT:
            subdir = subdir.lower()

        if path.startswith(subdir):
            return reason, str(full)[len(subdir) +1:]

    subdir = str(Path(__file__).parent.parent)

    if WinNT:
        subdir = subdir.lower()

    if path.startswith(subdir):
        return False, str(full)[len(subdir) +1:]

    return None, str(full)


def stackoffset(order=None, /, shift=0):
    stack = extract_stack()[:-1]

    def normalize(x):
        if not isinstance(x, bytes | str):
            x = Who.File(x)
            if not x:
                raise TypeError(f'{Who.Cast(x)} must be str or bytes')

        return str(Path(x))

    @cache
    def is_ignored_frame(x):
        for path in order:
            if x.startswith(path):
                return True
    if order:
        counter = 0
        if isinstance(order, str | bytes):
            order = [order]
        order = set(map(normalize, filter(bool, order)))

        for no, frame in enumerate(reversed(stack)):
            if not is_ignored_frame(frame.filename):
                if counter >= shift:
                    return len(stack) - no -1
                else:
                    counter += 1
    return 0


def stackfilter(line):
    line = line.lstrip()
    if line.startswith('File "<frozen importlib._'):
        return True

    for regex in (
        r'kalib/descriptors\.py", line \d+, in (__get__|call|type_checker)',
    ):
        if search(regex, line):
            return True


def stacktrace(count=None, /, join=True):
    if count is None:
        count = stackoffset(__file__) + 1

    stack = format_stack()

    if count > 0:
        stack = stack[:count]

    elif count <= 0:
        return stack[len(stack) + count -2].rstrip()

    stack = tuple(map(str.strip, filterfalse(stackfilter, stack)))
    return '\n'.join(stack) if join else stack


@cache
def get_module_from_path(path):
    def get_path_without_extension(path):
        return splitext(Path(path).absolute().resolve())[0]  # noqa: PTH122

    stem = get_path_without_extension(path)
    for name, module in modules.items():
        with suppress(AttributeError):
            if module.__file__ and stem == get_path_without_extension(module.__file__):
                return name

#


def stack_length():
    result = 0
    f = _getframe(1)
    while f:
        result += 1
        f = f.f_back
    return result


def wraps(func):
    if Is.classOf(func) is classmethod:
        msg = (
            'classmethod is not supported, use @classmethod '
            'decorator directly before method definition')

        with suppress(Exception):
            Logging.Default.exception(msg)

        raise TypeError(msg)
    return base_wraps(func)


def extract_options_from_kwargs(func=None, /, **fields):
    if func is None:
        return partial(extract_options_from_kwargs, **fields)

    elif not fields:
        return func

    fieldset = set(fields)
    annotation = {'__annotations__': {k: Is.classOf(v) for k, v in fields.items()}}
    Options = dataclass(kw_only=True)(type('Options', (), annotation | fields))  # noqa: N806

    @wraps(func)
    def wrapper(self, *args, **kw):
        kw['options'] = Options(**{
            key: kw.pop(key) for key in fieldset & set(kw)
        } if kw else {})
        return func(self, *args, **kw)

    wrapper.Options = Options
    return wrapper


class NumericOrSetter:

    def __init__(self, instance, attribute, value):
        self.instance  = instance
        self.attribute = attribute
        self.value     = value

    def __int__(self):
        return int(self.value)

    def __radd__(self, something):
        if isinstance(something, Is.classOf(self)):
            return self.value + something.value

        elif isinstance(something, float | int):
            return self.value + something

        msg = (
            f'{Who(something)} can add only self or numeric, '
            f'not ({Who(something)}) {something!r}')
        raise TypeError(msg)

    __add__ = __radd__

    def __call__(self, value):
        value = getattr(self.instance, self.attribute) + value
        setattr(self.instance, self.attribute, value)
        return self.instance

    def __repr__(self):
        return f'<{Who(self)}[{id(self):x}]={self.value!r}>'


class Logger(BaseLogger):

    _instances: ClassVar[dict] = {}

    #

    @pin.cls.here
    def Args(cls):  # noqa: N802
        return Who.Args

    @pin.cls.here
    def Call(cls):  # noqa: N802
        return Logging.Call

    @pin.cls.here
    def Catch(cls):  # noqa: N802
        return Logging.Catch

    @pin.cls.here
    def Intercept(cls):  # noqa: N802
        return Logging.Intercept

    @pin.cls.here
    def Inject(cls):  # noqa: N802
        return Logging.Inject

    #

    @pin.cls.here
    def digest(cls):
        return optional(
            'xxhash.xxh32_hexdigest',
            default=lambda x: md5(x).digest())  # noqa: S324

    @pin.cls.here
    def getter(cls):
        func = syslog.getLogger
        if func.__name__ != 'getLogger':
            return Monkey.mapping[func]
        return func

    @classmethod
    def make_for(cls, node, name=None):
        if isinstance(node, str):
            name = name or node
        else:
            node, name = Is.classOf(node), name or Who(node)

        try:
            logger = cls._instances[name]

        except KeyError:
            logger = cls._instances[name] = cls.getter(name)

        logger.owner = node
        return logger

    def __init__(self, *args, **kw):
        self._owner = None
        self._stack = kw.pop('stack', 0)
        self._shift = kw.pop('shift', 0)
        super().__init__(*args, **kw)

    @pin.cls.here
    def _already_logged(cls):
        return defaultdict(OrderedDict)

    @pin.cls.here
    def levels(cls):
        """Return levels dictionary."""

        def make_wrapper(name, level):
            qname = f'{Who(cls, full=False)}.{name}'

            def wrapper(self):
                if self.isEnabledFor(level):
                    def wrapped(*args, **kw):
                        return self.log(level, *args, **kw)
                else:
                    def wrapped(*args, **kw):
                        ...

                wrapped.__name__ = name
                wrapped.__qualname__ = qname
                wrapped.level = level
                return wrapped

            wrapper.__name__ = name
            wrapper.__qualname__ = qname
            return pin(wrapper)

        syslog.setLoggerClass(cls)
        for value, name in CUSTOM_LEVELS.items():
            syslog.addLevelName(value, name)

        for value in DEBUG, VERBOSE, NOTICE, INFO, WARNING, ERROR, CRITICAL:
            name = syslog._levelToName[value].lower()  # noqa: SLF001

            if name == (CUSTOM_NAMES.get(value) or name).lower():
                setattr(cls, name, make_wrapper(name, value))

            else:
                full = CUSTOM_NAMES[value].lower()
                func = make_wrapper(full, value)
                setattr(cls, full, func)
                setattr(cls, name, func)

        result = {
            **{k: v.capitalize() for k, v in syslog._levelToName.items()},  # noqa: SLF001
            **CUSTOM_NAMES,
        }
        levels = {k: result[k] for k in sorted(result)}

        for level, name in levels.items():
            setattr(Logging, name, level)

        cls.Levels = Namespace(
            **{name: level for level, name in levels.items()})

        return dict(levels)

    @pin
    def by_level(self):
        """Return method by level."""

        @cache
        def wrapper(level):
            if isinstance(level, bool) or level is None:
                level = {
                    True  : Logging.Warning,
                    False : Logging.Info,
                    None  : Logging.Debug,
                }[level]

            elif not isinstance(level, int) or level < 0:
                msg = f'({Who(level)}) {level=} must me positive integer'
                raise TypeError(msg)

            return getattr(
                self, (self.levels.get(level) or self.Levels.Verbose).lower())

        wrapper.__name__ = 'by_level'
        wrapper.__qname__ = f'{Who(self)}.by_level'
        return wrapper

    @property
    def owner(self):
        """Return owner of logger."""
        if (owner := self._owner) and (owner := owner()):
            return owner

    @owner.setter
    def owner(self, value):
        """Set owner of logger."""
        try:
            self._owner = ref(value)
        except TypeError:
            self._owner = None

    @property
    def refs(self):
        """Return number of references to owner."""
        if (owner := self.owner):
            return getrefcount(owner)
        return 0

    @property
    def stack(self):
        return NumericOrSetter(self, 'stack', self._stack)

    @stack.setter
    def stack(self, stack):
        self._stack += stack
        return self

    @property
    def shift(self):
        return NumericOrSetter(self, 'shift', self._shift)

    @shift.setter
    def shift(self, shift):
        self._shift += shift
        return self

    @extract_options_from_kwargs(
        shift   = 0,
        stack   = 0,
        count   = 0,

        once    = None,   # show this line only once, if False — show trace only once
        skip    = None,   # ignore files or sources with objects from this list

        trace   = False,  # show traceback
        context = True,   # with all lines instead selected one
    )
    def log(self, level, msg, *args, **kw):
        """Log message with level."""

        if not self.isEnabledFor(level):
            return msg

        var = kw.pop('options')

        skip = [__file__]
        if isinstance(var.skip, bytes | str):
            skip.append(var.skip)
        elif Is.iterable(var.skip):
            skip.extend(var.skip)

        trace = var.trace
        base_offset = stackoffset(skip)

        if var.once is not None:

            frame = stack()[-base_offset -1]
            frame = f'{frame.filename}:{frame.lineno:d}'
            cache = self._already_logged[frame]

            key = None if var.once else self.digest(to_bytes(f'{msg!a}:{args!a}'))
            already = key in cache

            if not already:
                cache[key] = int(time())
                if len(cache) >= DEDUP_ORDER_SIZE:
                    for _ in range(min(1, DEDUP_ORDER_SIZE - len(cache) + 10)):
                        cache.popitem(last=False)

            elif var.once:
                return msg

            elif trace:
                trace = False

        trace_offset = (self.stack + var.stack) + (stack_length() - base_offset)
        stack_offset = (self.shift + var.shift) + base_offset + 1

        kw.setdefault('extra', {'refs': self.refs})
        kw.setdefault('stack_info', False)
        kw.setdefault('stacklevel', trace_offset)

        method = super().log
        if not trace or len(args) > 1:
            method(level, msg, *args, **kw)
            return msg

        lines = stacktrace(
            stack_offset * (-1, 1)[bool(var.context)],
            join=not var.count)

        if lines:
            lines = lines[-var.count:]

        msg = '{0}\n{1}\n{2}: {0}'.format(
            msg, ''.join(lines).rstrip(),
            self.levels.get(level, f'UnknownLevel{level:d}'))
        method(level, msg, *args, **kw)
        return msg

    def deprecate(self, msg, *args, **kw):
        kw.setdefault('once', True)
        kw.setdefault('trace', True)
        kw.setdefault('context', False)
        return self.log(DEPRECATE, msg, *args, **kw)

    def trace(self, msg, *args, **kw):
        kw.setdefault('once', False)
        kw.setdefault('trace', True)
        kw.setdefault('context', False)
        return self.log(WARNING, msg, *args, **kw)

    def fail(self, exception, *args, **kw):

        try:
            from tools.exceptions import exception  # noqa: PLC0415
            e = exception(exception)

            title = e.message or 'Unknown exception'
            message = str(e.traceback)

        except ImportError:
            def trim(x):
                return tuple(i.rstrip() for i in x)

            title = Str(exception).strip() or 'Unknown exception'
            message = '\n'.join(trim(traceback.format_exception(exception)))

        except Exception as e:  # noqa: BLE001
            msg = f'{exception!r} {e}'
            self.log.warning(msg, *args, **kw)
            return msg

        title = f'{title.rstrip().rstrip(":")}:'
        return self.log(CRITICAL, f'{title}\n{message}', *args, **kw)


class Logging:

    @pin.cls
    def Mixin(klass):  # noqa: N802

        class Mixin:

            @pin.cls
            def log(cls):
                return klass.get(cls)

            @pin.cls
            def logger(cls):
                log = cls.log
                log.deprecate(f'-> {Who(cls)}.log', shift=-5, stack=5)
                return log

        return Mixin

    loggers          : ClassVar[dict] = {}
    path_nodes       : ClassVar[list] = []
    configured_files : ClassVar[list] = []

    LOGGING_LEVEL    = INFO
    LOGGING_PRECISE  = 3
    LOGGING_PREFIX   = None
    LOGGING_FULLNAME = True
    LOGGING_FORMAT   = '%(name)s:%(funcName)s:%(lineno)d %(message)s'

    #

    @classmethod
    def Args(cls, *args, **kw):  # noqa: N802
        return Who.Args(*args, **kw)

    @classmethod
    def Call(cls, level=None):  # noqa: N802
        """Decorator for logging method call."""

        def method_wrapper(func):
            @wraps(func)
            def call(*args, **kw):
                try:
                    node = args[0]  # self, cls or other

                except AttributeError as e:
                    msg = (
                        "{0}.logger attribute for {0}.{1} method wrapper isn't "
                        'exists; try implement logger as data-descrtiptor, inherit '
                        'your {0} from {2} or from {3}'
                        .format(Who(args[0]), Who(func), Who(cls), Who(Logging)))
                    raise AttributeError(msg) from e

                except IndexError as e:
                    msg = (
                        f"class or instance reference isn't passed to method, looks "
                        f'like as call with staticmethod or similar context without '
                        f'any args, pass into {Who(func)} something with logger as '
                        f'data-descriptor or another attribute at first call argument')
                    raise IndexError(msg) from e

                key = '__logger_{:d}__'.format(
                    level or getattr(cls, 'LOGGING_LEVEL', INFO))

                try:
                    logger = getattr(func, key)

                except AttributeError:
                    try:
                        logger = node.owner.log

                    except AttributeError:
                        who = Who(args[0], full=cls.LOGGING_FULLNAME)
                        name = f'{who}.{Who.Name(func)}'
                        logger = Logging.get(node, name=name, level=level)

                    with suppress(Exception):
                        setattr(func, key, logger)

                start = time()
                result = func(*args, **kw)
                spent = time() - start

                arguments = f'({Who.Args(*args[1:], **kw)}) '
                time_spent = template.format(spent) if around(spent) else ''
                value = '' if result is None else f'-> {simple_repr(result)}'

                logger.info(
                    f'{arguments if len(arguments) > 3 else ""}{value}{time_spent}')  # noqa: PLR2004

                return result

            return call

        precise = cls.LOGGING_PRECISE
        power = 10 ** precise
        template = f' ({{:0.{precise:d}f}}s)'
        around = lambda x: int(x * power)  # noqa: E731

        if Is.function(level) or Is.classOf(level) is classmethod:
            func, level = level, None
            return method_wrapper(func)

        elif isinstance(level, int):
            return method_wrapper

        msg = (
            f'{Who(cls)}.Call receive only one argument: logging.LEVEL '
            f'as int | None, not {Who.Is(level)}')
        raise ValueError(msg)

    @classmethod
    def Catch(cls, *exceptions, **kw):  # noqa: N802
        """Decorator for catching exceptions when method call."""

        modified = 'throw' in kw
        throw = kw.pop('throw', True)
        default = kw.pop('default', None)

        from kalib.exceptions import exception  # noqa: PLC0415

        def method_wrapper(func):

            def get_logger(exc, args, kw):
                head = (
                    f'.{Who(func)}({Who.Args(*args, **kw)}) hit '
                    f'{exception(exc).reason}')

                if args:
                    if logger := getattr(args[0], 'log', None):
                        return logger, head

                    if logger := getattr(args[0], 'logger', None):
                        return logger, head

                return cls.Default, head

            @wraps(func)
            def expect(*args, **kw):
                try:
                    return func(*args, **kw)

                except exceptions as e:
                    logger, head = get_logger(e, args, kw)

                    msg = f'expected exception {Who(e)}:'
                    if throw:
                        logger.warning(msg)
                        raise

                    if default is not None:
                        logger.info(f'{msg}; return {Who.Is(default)}')

                except Exception as e:
                    logger, head = get_logger(e, args, kw)
                    logger.exception(f'unexpected exception {Who(e)}:')  # noqa: TRY401
                    raise

                return default

            return expect

        if (
            not kw and not modified
            and len(exceptions) == 1
            and Is.callable(exceptions[0])
        ):
            func = exceptions[0]
            exceptions = (Exception,)
            return method_wrapper(func)

        if not exceptions:
            exceptions = (Exception,)

        return method_wrapper

    @classmethod
    def Intercept(cls, *exceptions, **kw):  # noqa: N802
        """Decorator for intercepting exceptions when method call, just logging."""

        kw.setdefault('throw', False)
        return cls.Catch(*exceptions, **kw)

    @classmethod
    def Inject(cls, func):  # noqa: N802
        """Decorator for injecting logger to function as first positional argument."""

        logger = cls.from_object(func, name=Who.Module(func))
        func.log = logger

        @wraps(func)
        def wrapper(*args, **kw):
            try:
                value = func(logger, *args, **kw)

            except TypeError as e:
                from kalib.exceptions import exception  # noqa: PLC0415
                message = exception(e).message

                if (
                    (sig := match(RE_TYPE_ERROR, message or '')) and
                    (sig.group(1) == Who.Name(func)) and
                    (int(sig.group(2)) + 1 == int(sig.group(3)))
                ):
                    raise TypeError(
                        f'{message}, may be you forgot to pass logger as '
                        f'first positional argument to {Who(func)}?') from e
                raise

            if iscoroutinefunction(func):
                value = ensure_future(value)
            return value

        return wrapper

    #

    @classmethod
    def from_filename(cls, path, **kw):
        """Return logger for file."""

        reason, short = trim_module_path(path)
        if reason is not None:
            short = short.rsplit('.', 1)[0]

            if short.endswith('__init__'):
                short = short.rsplit(sep, 1)[0]

            return cls.get(short.replace(sep, '.'), **kw)

        if Path(argv[0]).absolute() == Path(path).absolute():
            return cls.get(Path(path).stem, **kw)

    @class_property
    def Default(cls):  # noqa: N802
        """Return default logger for current module."""

        def get_lastframe():
            for frame in stack()[2:]:
                if (
                    f'{cls.__name__}.Default' in
                    repr(frame.code_context or '')
                ):
                    return frame

        if pointer := get_lastframe():
            cls.path_nodes.append(pointer.filename)
            if logger := cls.from_filename(pointer.filename):
                return logger

        return cls.get('<unknown>')

    @pin.cls.here
    def config(cls):
        """Return logging configuration object."""
        import logging.config as config  # noqa: PLC0415,PLR0402
        return config

    @pin.cls.here
    def Force(cls):  # noqa: N802
        """Force logging to be enabled."""

        def get():
            result = getenv('LOGGING_FORCE', '')
            if not result or result.lower() == 'false':
                return False

            elif result.isdigit():
                return bool(int(result))

            return result or False

        if (force := get()):
            LOGGING_FORCE = getenv('LOGGING_FORCE', '')  # noqa: N806
            cls.log.verbose(f'={force} ({LOGGING_FORCE=})', stack=-1)
        return force

    @pin.cls.here
    def Debugging(cls):  # noqa: N802
        """Force debugging to be enabled."""

        result = getenv('DEBUG', '')
        if not result or result.lower() == 'false':
            return False

        elif result.isdigit():
            return bool(int(result))

        return result or False

    @pin.cls.here
    def config_path(cls):
        """Return path to logging configuration file."""

        if (
            (path := getenv('LOGGING', None)) and
            Path(path).is_file()
        ):
            return str(path)
        return getenv('LOGGING_CONFIG', None)

    @pin.cls
    def directories_from_callstack(cls):
        """Return directories from callstack."""

        seen = set()

        def iterfiles():
            yield __file__
            yield from unique(cls.path_nodes)
            for frame in stack():
                if not Path(frame.filename).is_file():
                    continue
                yield frame.filename

        def iterpath():
            for path in unique(iterfiles()):
                path = str(Path(path).resolve().parent)  # noqa: PLW2901
                if path not in seen:
                    seen.add(path)
                    yield Path(path)

        return tuple(iterpath())

    @classmethod
    def iter_config_files(cls, iterable=None):
        """Iterate over logging configuration files."""

        if isinstance(iterable, str):
            iterable = [Path(iterable)]

        iterable = list(iterable or cls.directories_from_callstack)

        seen = set()
        for root in (Path(argv[0]), Path.cwd(), *iterable):
            if root.is_file():
                root = root.parent  # noqa: PLW2901

            last = None
            while True:
                path = (root / DEFAULT_LOG_CONFIG).resolve()
                if last is not None and last == path:
                    break

                if path.is_file() and path not in seen:
                    seen.add(path)
                    yield path

                if str(root) == sep:
                    break
                root = root.parent  # noqa: PLW2901
                last = path

    @classmethod
    def configure(cls, path=None):  # noqa: PLR0912
        """Configure logging from file."""

        if not path and cls.config_path and cls.configured_files:
            return

        def iterconfigs(path):
            if not path:
                yield from cls.iter_config_files(cls.directories_from_callstack)
            else:
                yield path

        default_logger = cls.log
        for file in unique(iterconfigs(path or cls.config_path)):
            if str(file) in cls.configured_files:
                continue

            if not Path(file).is_file():
                default_logger.error(f"logging file file {file!r} isn't accessible")

            config = dict(toml_read(file))
            if not cls.config_path:
                if config.get('disable_existing_loggers'):
                    default_logger.verbose(
                        f'{file} try to override '
                        f'{config["disable_existing_loggers"]=}')

                config['incremental'] = True
                config['disable_existing_loggers'] = path and not cls.loggers

                loggers = {}

                for name, logger in config.get('loggers', {}).items():
                    if cls.Debugging:
                        logger['level'] = 'DEBUG'

                    if name not in cls.loggers:
                        level = logger['level']
                        msg = f'{file} {level}({syslog.getLevelName(level)}): {name}'
                        default_logger.debug(msg)

                    else:
                        before, after = cls.loggers[name]['level'], logger['level']
                        if before != after:
                            aft = syslog.getLevelName(after)
                            bef = syslog.getLevelName(before)

                            if bef == aft:
                                continue

                            msg = f'{file} {before}({bef}): {name} -> {after}({aft})'
                            if bef > aft:
                                msg = f'{msg} [ignored]'
                            default_logger.info(msg)

                config['loggers'] = loggers
                cls.loggers.update(loggers)

            cls.from_dict(**config)
            cls.configured_files.append(str(file))
            default_logger.info(f'rules applied: {file}')

        return cls

    @classmethod
    def from_dict(cls, **kw):
        """Native logging configure from dict call"""
        cls.config.dictConfig(kw)
        return cls

    @classmethod
    def get(cls, node, configure=True, *args, **kw):  # noqa: ARG003
        """Main logger creating function for something"""

        if configure:
            cls.configure()

        klass = syslog.getLoggerClass()
        if klass is not Logger:
            cls.log.verbose(
                f'somebody override defined logger {Who(Logger)} '
                f"with {Who(klass)}{Who.File(klass, 'from %r')}")
            syslog.setLoggerClass(Logger)

        if cls is not node:
            logger = cls.log.make_for(node, kw.pop('name', None))
        else:
            logger = syslog.getLogger(Who(node))

        if Is.classOf(logger) is not Logger:
            msg = (
                f"couldn't restore defined logger {Who(Logger)} "
                f'instead override {Who(klass)}')
            raise TypeError(msg)

        if (level := (kw.pop('level', DEPRECATE), DEBUG)[cls.Debugging]):
            logger.setLevel(level)
        return logger

    @pin.cls.here
    def log(cls):
        """Logger for itself"""

        order = []
        msg = None
        level = ('DEPR', 'NOTSET')[cls.Debugging]

        if not cls.config_path:
            for no, file in enumerate(cls.iter_config_files(__file__)):
                config = dict(toml_read(file))
                config['disable_existing_loggers'] = not bool(no)
                if not no:
                    loggers = config['loggers']
                    try:
                        loggers['root']['level'] = level

                    except KeyError as e:
                        key = e.args[0]
                        if key != 'root':
                            msg = f'{key=} not found in {loggers=} (from {file=})'
                            raise KeyError(msg) from e

                        msg = (
                            f'root logger not found in {loggers=} '
                            f'(from {file!s}), set default level '
                            f'from {Who(cls)}.LOGGING_LEVEL={cls.LOGGING_LEVEL}')

                        loggers['root'] = {
                            'handlers' : ['stdout'],
                            'level'    : cls.LOGGING_LEVEL,
                            'propagate': False}

                cls.from_dict(**config)
                order.append(str(file))

        logger = cls.get(cls, configure=False, level=DEPRECATE)
        if not cls.config_path and not cls.configured_files:
            logger.verbose(f'autoconfigured from: {", ".join(order)}')
        if msg:
            logger.warning(msg)
        cls.configured_files.extend(order)
        return logger

    @pin.cls.here
    def logger(cls):
        """Compatibility for default .logger behavior"""

        log = cls.log
        log.deprecate(f'-> {Who(cls)}.log', shift=-5, stack=5)
        return log

    def from_object(node, **kw):
        """Universal logger creating function for something.
        When .log attribute is exists, it will be used as logger.
        Instead — create new one.
        """

        if logger := getattr(node, 'log', Nothing):
            return logger
        return Logging.get(node, **kw)


def injector(func, *args, **kw):  # noqa: ARG001
    """Override native logging subsystem globally"""

    if not args:
        for frame in stack():
            if 'getLogger' in repr(frame.code_context or ''):
                if (
                    (result := Logging.from_filename(frame.filename)) or
                    (
                        (result := get_module_from_path(frame.filename)) and
                        (result := Logging.get(get_module_from_path(frame.filename)))
                    )
                ):
                    return result

                if frame.function != '<module>':
                    msg = f'named module, {frame=}'
                    raise NotImplementedError(msg)

        args = (stack()[2].function,)

    if not Is.imported(args[0]):
        name = args[0]
        logger.debug(
            f'incorrect module log name: must be full module path, not {name=}',
            trace=-2, shift=-2, count=1)

    return Logging.get(args, *args[1:], **kw)


Logger.levels  # noqa: B018, add custom levels, set out class instead default
logger = Logging.Default

if Logging.Force:
    Monkey.wrap(syslog, 'getLogger')(injector)

Args = Who.Args
