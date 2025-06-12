from collections import deque, namedtuple
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from contextlib import suppress
from functools import cache, partial
from inspect import (
    getmodule,
    getsourcefile,
    isawaitable,
    isbuiltin,
    isclass,
    iscoroutine,
    isfunction,
    ismethod,
    ismodule,
    stack,
)
from itertools import filterfalse
from operator import itemgetter
from os.path import splitext
from pathlib import Path
from platform import architecture
from re import search, sub
from sys import modules
from sysconfig import get_paths
from traceback import extract_stack, format_stack
from types import FunctionType, LambdaType
from typing import Any, get_origin

Collections = deque, dict, list, set, tuple, bytearray
Primitives  = bool, float, int, str, complex, bytes
Builtins    = Primitives + Collections

is_windows = 'windows' in architecture()[1].lower()


def is_callable(obj):
    return isinstance(obj, Callable) or callable(obj)


def is_collection(obj):
    return (
        isinstance(obj, Collection) and
        isinstance(obj, Sequence) and
        not isinstance(obj, bytes | str)
    ) or is_mapping(obj)


def is_mapping(obj):
    if isinstance(obj, Mapping):
        return True

    if issubclass(class_of(obj), dict):
        return True

    return all(map(
        partial(hasattr, obj),
        ('__getitem__', '__setitem__', '__delitem__')))


def is_iterable(obj):
    return isinstance(obj, Iterable) or hasattr(obj, '__iter__')


def is_from_primivite(obj):
    """
    Check if the object instantiated from primitive type.
    """
    return bool(obj is None or isinstance(obj, Primitives))


def is_from_builtin(obj):
    return bool(isinstance(obj, Collections) or is_from_primivite(obj))


def is_primitive(obj):
    return (
        obj is True or obj is False or
        obj is None or type(obj) in Builtins)


def unique(iterable, /, key=None, include=None, exclude=None):
    skip = include is None

    if not key:
        exclude = set(exclude or ())
        include = frozenset(include or ())

    else:
        exclude = set(map(key, exclude or ()))
        include = frozenset(map(key, include or ()))

    excluded = exclude.__contains__
    included = include.__contains__
    is_dict = isinstance(iterable, dict)

    for element in iterable:

        k = key(element) if key else element
        if not excluded(k) and (skip or included(k)):

            yield (element, iterable[element]) if is_dict else element
            exclude.add(k)

@cache
def trim_module_path(full):
    dirs = get_paths()

    path = str(full)
    if is_windows:
        path = path.lower()

    for scheme, reason in (
        ('stdlib', True),
        ('purelib', False),
        ('platlib', False),
        ('platstdlib', True),
    ):
        subdir = dirs[scheme]
        if is_windows:
            subdir = subdir.lower()

        if path.startswith(subdir):
            return reason, str(full)[len(subdir) +1:]

    subdir = str(Path(__file__).parent.parent)

    if is_windows:
        subdir = subdir.lower()

    if path.startswith(subdir):
        return False, str(full)[len(subdir) +1:]

    return None, str(full)


def is_internal(x):
    if (isbuiltin(x) or isbuiltin(class_of(x))):
        return True

    elif (module := get_module(x)):

        if module.__name__ == 'builtins':
            return True

        is_stdlib = trim_module_path(module.__file__)[0]
        if is_stdlib is not None:
            return is_stdlib

    return False


def class_of(obj):
    return obj if isclass(obj) else type(obj)


def subclass(obj, types):
    if types is None:
        return False

    if types in (Any, obj, object):
        return True

    if obj is None and types is class_of(None):
        return True

    try:
        return issubclass(class_of(obj), types)

    except TypeError as e:
        if origin := get_origin(types):
            return issubclass(class_of(obj), origin)
        raise e


def iter_inheritance(  # noqa: PLR0913
    obj,
    include        = None,
    exclude        = None,
    exclude_self   = True,
    exclude_stdlib = True,
    reverse        = False,
):
    order = class_of(obj).__mro__[:-1]

    if not exclude_self:
        order = unique((obj, *order), key=id)
    else:
        order = unique(filter(lambda x: x is not obj, order), key=id)

    if reverse:
        order = reversed(list(order))

    if include:
        if isinstance(include, FunctionType | LambdaType):
            order = filter(include, order)
        else:
            if not is_iterable(include):
                include = (include,)
            order = filter(include.__contains__, order)

    if exclude:
        if isinstance(exclude, FunctionType | LambdaType):
            order = filterfalse(exclude, order)
        else:
            if not is_iterable(exclude):
                exclude = (exclude,)
            order = filterfalse(exclude.__contains__, order)

    if exclude_stdlib:
        order = filterfalse(is_internal, order)

    yield from order


def get_mro(obj, /, **kw):

    func = kw.pop('func', None)
    glue = kw.pop('glue', None)

    result = iter_inheritance(obj, **kw)

    if func:
        result = tuple(map(func, result))

    if glue:
        result = glue.join(result)

    return result if (func or glue) else tuple(result)


def get_entity(something, name, **kw):

    index = kw.pop('index', 0)
    kw.setdefault('exclude_self', False)
    kw.setdefault('exclude_stdlib', False)

    counter = 0
    for obj in iter_inheritance(something, **kw):
        try:
            attr = obj.__dict__[name]
            if not counter - index:
                return attr, obj
            counter += 1
        except KeyError:
            continue
    raise KeyError


def get_owner(obj, name, **kw):
    try:
        return get_entity(obj, name, **kw)[1]
    except KeyError:
        ...


def get_attr(obj, name, default=None, **kw):
    try:
        return get_entity(obj, name, **kw)[0]
    except KeyError:
        return default


def get_module(x):
    if ismodule(x):
        return x

    elif (
        (module := getmodule(x)) or
        (module := getmodule(class_of(x)))
    ):
        return module


def get_module_name(x):
    if module := get_module(x):
        with suppress(AttributeError):
            return module.__spec__.name


# This function is used to get the name of the object

def objectname(obj, full=True):
    """
    Returns the name of the given object, optionally including the full module path.

    Args:
        obj: The object whose name is to be determined.
        full (bool): If True, the full module path is included in the name.

    Returns:
        str: The name of the object, optionally including the full module path.

    Notes:
        - If the object is a module, its name is returned.
        - If the object is a coroutine, function, or method, its name is constructed
          using its module and qualified name.
        - If the object is a property, the name of its getter function is returned.
        - If the object is of any other type, the name of its class is returned.
    """

    def post(x):
        return sub(r'^([\?\.]+)', '', sub('^(__main__|__builtin__|builtins)', '', x))

    def get_module_from(x):
        return getattr(x, '__module__', get_module_name(x)) or '?'

    def get_object_name(x):
        if obj is Any:
            return 'typing.Any' if full else 'Any'

        name = getattr(x, '__qualname__', x.__name__)
        module = get_module_from(x)

        if not name.startswith(module):
            name = f'{module}.{name}'
        return name

    def main(obj):
        if ismodule(obj):
            return get_module_name(obj)

        for itis in iscoroutine, isfunction, ismethod:
            if itis(obj):
                name = get_object_name(obj)
                with suppress(AttributeError):
                    name = f'{objectname(obj.im_self or obj.im_class)}.{post(name)}'
                return name

        cls = class_of(obj)
        if cls is property:
            return get_object_name(obj.fget)

        return get_object_name(cls)

    name = post(main(obj))
    return name if full else name.rsplit('.', 1)[-1]


def Who(obj, /, full=True, addr=False):  # noqa: N802
    """
    Retrieve the name of an object, optionally including its memory address.
    Parameters:
    obj (object): The object whose name is to be retrieved.
    full (bool, optional): If True, retrieve the full name of the object.
        If False, retrieve a shorter name. Defaults to True.
    addr (bool, optional): If True, append the memory address of the object
        to the name. Defaults to False.
    Returns:
    str: The name of the object, optionally including its memory address.
    """

    key = '__name_full__' if full else '__name_short__'

    def get_name():
        try:
            store = obj.__dict__
            with suppress(KeyError):
                return store[key]
        except AttributeError:
            store = None

        name = objectname(obj, full=full)
        if store is not None:
            with suppress(AttributeError, TypeError):
                setattr(obj, key, name)
        return name

    name = get_name()
    if addr:
        name = f'{name}#{id(obj):x}'
    return name


def Is(obj, /, **kw):  # noqa: N802
    """
    Generate a string representation of an object with optional keyword arguments.
    Parameters:
    obj (Any): The object to generate the string representation for.
    **kw: Arbitrary keyword arguments. Supported keywords:
        - 'addr' (bool): If True, include the address of the object
            in the representation.
    Returns:
    str: A string representation of the object, potentially including its
        address and JSON representation.
    """
    from kalib.datastructures import try_json

    kw.setdefault('addr', True)
    msg = Who(obj, **kw)

    if class_of(obj) is not obj:
        msg = f'({msg}):{try_json(obj)}'
    return msg


def Module(obj):  # noqa: N802
    """
    Extract the module name from a given object's fully qualified name.

    Args:
        obj: The object whose module name is to be extracted.

    Returns:
        str: The module name of the given object.
    """
    return Who(obj).rsplit('.', 1)[0]


def Cast(obj):  # noqa: N802
    return f'({Who(obj)}){obj}'


Who.Name   = partial(Who, full=False)
Who.Is     = Is
Who.Cast   = Cast
Who.Module = Module

#

def sourcefile(obj, **kw):
    kw.setdefault('exclude_self', False)
    kw.setdefault('exclude_stdlib', False)

    for i in iter_inheritance(class_of(obj), **kw):
        with suppress(TypeError):
            return getsourcefile(i)


Who.File = sourcefile


def stackoffset(order=None, /, shift=0):
    stack = extract_stack()[:-1]

    def normalize(x):
        if not isinstance(x, bytes | str):
            x = sourcefile(x)
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


def about(something):
    try:
        path = sourcefile(something)

    except TypeError:
        try:
            path = getsourcefile(something)
        except TypeError:
            path = None

    mro = get_mro(something, glue=', ')
    std = ('3rd party', 'from stdlib')[is_internal(something)]
    return f'{Who.Is(something)} ({std}) from {path=}, {mro=}'


@cache
def is_imported_module(name):

    with suppress(KeyError):
        return bool(modules[name])

    chunks = name.split('.')
    return sum(
        '.'.join(chunks[:no + 1]) in modules
        for no in range(len(chunks))) >= 2  # noqa: PLR2004

@cache
def get_module_from_path(path):
    def get_path_without_extension(path):
        return splitext(Path(path).absolute().resolve())[0]  # noqa: PTH122

    stem = get_path_without_extension(path)
    for name, module in modules.items():
        with suppress(AttributeError):
            if module.__file__ and stem == get_path_without_extension(module.__file__):
                return name


@cache
def get_subclasses_from_path(cls, path):
    from kalib.importer import required

    if module_path := get_module_from_path(path):
        module = required(module_path)

        result = []
        for name in dir(module):
            if name.startswith('__') or name.endswith('__'):
                continue

            with suppress(Exception):
                if (sub := getattr(module, name)) and issubclass(sub, cls):
                    result.append(sub)

        return tuple(result)


def iter_stack(*args, **kw):
    result = stack()[kw.pop('offset', 0):]
    yield from (map(itemgetter(*args), result) if args else result)


is_awaitable = isawaitable
is_builtin   = isbuiltin
is_class     = isclass
is_coroutine = iscoroutine
is_function  = isfunction
is_method    = ismethod
is_module    = ismodule


Is = (
    namedtuple(
        'Is', 'Class awaitable builtin callable classOf collection coroutine '
        'Builtin Primivite function imported internal '
        'iterable mapping method module primitive subclass')(
    is_class, is_awaitable, is_builtin, is_callable, class_of, is_collection,
    is_coroutine, is_from_builtin, is_from_primivite, is_function,
    is_imported_module, is_internal, is_iterable, is_mapping, is_method,
    is_module, is_primitive, subclass))
