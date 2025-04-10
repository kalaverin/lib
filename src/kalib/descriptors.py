from asyncio import ensure_future, iscoroutinefunction
from contextlib import suppress
from functools import cached_property, lru_cache, partial, wraps
from inspect import iscoroutine, isfunction, ismethod
from time import time

from kalib.classes import Nothing
from kalib.internals import (
    Who,
    class_of,
    get_attr,
    get_owner,
    is_class,
    issubstance,
)

__all__ = 'Property', 'cache'


def cache(limit=None):

    function = partial(lru_cache, maxsize=None, typed=False)

    if isinstance(limit, classmethod | staticmethod):
        msg = f"can't wrap {Who.Is(limit)}, you must use @cache after it"
        raise TypeError(msg)

    for func in isfunction, iscoroutine, ismethod:
        if func(limit):
            return function()(limit)

    if limit is not None and (not isinstance(limit, float | int) or limit <= 0):
        msg = f'limit must be None or positive integer, not {Who.Is(limit)}'
        raise TypeError(msg)

    return function(maxsize=limit) if limit else function()


def call_descriptor(descriptor):
    if issubstance(descriptor, BaseProperty):
        return descriptor.call

    func = getattr(descriptor, 'fget', Nothing)
    if func is Nothing:
        head = f'expected descriptor derived from {Who(BaseProperty)}'

        if class_of(descriptor) is not cached_property:
            raise TypeError(f'{head}, but got {Who(descriptor)} instead')

        raise TypeError(
            f'{head}, but got {Who(descriptor)}, may be you use '
            f'@Property.Bind instead @Property.Cached?')

    return func


def parent_call(func):

    @wraps(func)
    def parent_caller(node, *args, **kw):
        try:
            desc = get_attr(
                class_of(node), func.__name__, exclude_self=True,
                index=bool(func.__name__ not in class_of(node).__dict__))
            return func(node, call_descriptor(desc)(node, *args, **kw), *args, **kw)

        except RecursionError as e:
            raise RecursionError(
                f'{Who(node)}.{func.__name__} call real {Who(func)}, '
                f"couldn't reach parent descriptor; "
                f"maybe {Who(func)} it's mixin of {Who(node)}?") from e

    return parent_caller


class PropertyError(Exception): ...


class ContextFaultError(PropertyError): ...


class AttributeException(PropertyError): ...  # noqa: N818


def invokation_context_check(func):

    @wraps(func)
    def context(self, node, *args, **kw):
        if (
            self.klass is not None and
            (node is None or self.klass != is_class(node))
        ):
            msg = (
                f'{Who(func)} exception, '
                f'{self.header_with_context(node)}, {node=}')

            if node is None and not self.klass:
                msg = f'{msg}; looks like as non-instance invokation'
            raise ContextFaultError(msg)

        return func(self, node, *args, **kw)
    return context


class BaseProperty:

    klass = False
    readonly = False

    def __init__(self, function):
        self.function = function

    @cached_property
    def name(self):
        return self.function.__name__

    @cached_property
    def is_data(self):
        return bool(hasattr(self, '__set__') or hasattr(self, '__delete__'))

    @cached_property
    def title(self):
        mode = 'mixed' if self.klass is None else ('instance', 'class')[self.klass]

        prefix = ('', 'data ')[self.is_data]
        return (
            f'{mode} {prefix}descriptor '
            f'{Who(self, addr=True)}'.strip())

    @cached_property
    def header(self):
        try:
            return f'{self.title}({self.function!a})'
        except Exception:  # noqa: BLE001
            return f'{self.title}({Who(self.function)})'

    def header_with_context(self, node):

        if node is None:
            mode = 'mixed' if self.klass is None else 'undefined'
        else:
            mode = ('instance', 'class')[is_class(node)]

        return f'{self.header} with {mode} ({Who(node, addr=True)}) call'

    @invokation_context_check
    def get_node(self, node):
        return node

    @invokation_context_check
    def call(self, node):
        try:
            value = self.function(node)
            return ensure_future(value) if iscoroutinefunction(self.function) else value

        except AttributeError as e:
            from kalib.exceptions import exception
            error = AttributeException(exception(e).message.rsplit(':', 1)[-1].strip())

            error.exception = e
            raise error from e

    def __str__(self):
        return f'<{self.header}>'

    def __repr__(self):
        return f'<{self.title}>'

    def __get__(self, instance, klass):
        if instance is None and self.klass is False:
            raise ContextFaultError(self.header_with_context(klass))

        return self.call((instance, klass)[self.klass])


class InheritedClass(BaseProperty):
    """By default class property will be used parent class.
    This class change behavior to last inherited child.
    """

    @invokation_context_check
    def get_node(self, node):
        return node

    @classmethod
    def make_from(cls, klass):
        """Make child-aware class from plain parent-based."""

        name = Who(klass, full=False)
        suffix = f'{"_" if name == name.lower() else ""}inherited'.capitalize()
        return type(f'{name}{suffix}', (cls, klass), {})


class Cached(BaseProperty):

    @classmethod
    def expired_by(cls, callback):
        return partial(cls, expired=callback)

    @classmethod
    def ttl(cls, expire: float):
        if not isinstance(expire, float | int):
            raise TypeError(f'expire must be float or int, not {Who.Is(expire)}')

        if expire <= 0:
            raise ValueError(f'expire must be positive number, not {expire!r}')

        def is_fresh(node, value=Nothing):  # noqa: ARG001
            return (value + expire > time()) if value else time()

        return cls.expired_by(is_fresh)

    def __init__(self, function, expired=None):
        super().__init__(function)
        self.expired = expired

    @invokation_context_check
    def get_cache(self, node):
        name = f'__{("instance", "class")[is_class(node)]}_memoized__'

        if hasattr(node, '__dict__'):
            with suppress(KeyError):
                return node.__dict__[name]

        cache = {}
        setattr(node, name, cache)
        return cache

    @invokation_context_check
    def call(self, obj):
        node = self.get_node(obj)

        with suppress(KeyError):

            if not self.expired:
                return self.get_cache(node)[self.name]

            value, stamp = self.get_cache(node)[self.name]
            if self.expired(node, stamp) is not False:
                return value

        return self.__set__(node, super().call(obj))

    @invokation_context_check
    def __set__(self, node, value):
        cache = self.get_cache(node)
        if not self.expired:
            cache[self.name] = value
        else:
            cache[self.name] = value, self.expired(node)
        return value

    @invokation_context_check
    def __delete__(self, node):
        cache = self.get_cache(node)
        with suppress(KeyError):
            del cache[self.name]


class ClassProperty(BaseProperty):
    klass = True

    @invokation_context_check
    def get_node(self, node):
        return get_owner(node, self.name) if is_class(node) else node


class MixedProperty(ClassProperty):
    klass = None

    def __get__(self, instance, klass):
        return self.call(instance or klass)


class ClassCachedProperty(ClassProperty, Cached):
    """Class-level cached property that passes the original class as the first
    positional argument and replaces the original data-descriptor."""
    """"""


class MixedCachedProperty(MixedProperty, Cached):
    """Mixed-level cached property that replaces the original data-descriptor"""


class Property(BaseProperty):
    """
    The Property class is a versatile descriptor used for managing attributes in a class.
    It includes various types of properties for both instances and classes.
    """

    """Replaces the data-descriptor with a calculated result,
    supporting asynchronous operations."""
    Cached = Cached

    """Just replaces the getter with a calculated result for simple cases."""
    Bind = cached_property

    """Passes the class as the first positional argument."""
    Class = ClassProperty

    """Passes the original class where the decorator is used, then replaces its
    own data-descriptor with a calculated result in the original parent."""
    Class.Parent = ClassCachedProperty

    """Passes the inherited class and sets the child class attribute
    with a calculated result."""
    Class.Cached = InheritedClass.make_from(ClassCachedProperty)

    """Can be used with either a class or an instance."""
    Mixed = MixedProperty

    """Replaces the data-descriptor with a calculated result for instances, but when
    used in a class context, passes the class and just returns the result."""
    Mixed.Cached = InheritedClass.make_from(MixedCachedProperty)

    @classmethod
    def Custom(cls, callback):  # noqa: N802
        result = Cached.expired_by(callback)
        result.Class = cls.Class.Cached.expired_by(callback)
        return result


# obsolete interface

class pin(Cached):  # noqa: N801

    attr = Property.Bind

    # class-descriptor, but .root uses class what have
    # declared pin.root, instead last child
    root = Property.Class.Parent
    cls  = Property.Class.Cached

    # mixed-descriptor, do not cache when using in class context, but bind instead
    any  = Property.Mixed.Cached
