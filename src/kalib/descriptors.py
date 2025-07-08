from asyncio import ensure_future, iscoroutinefunction
from contextlib import suppress
from functools import cached_property, lru_cache, partial, wraps
from inspect import iscoroutine, isfunction, ismethod
from time import time

from kalib.classes import Nothing
from kalib.internals import (
    Is,
    Who,
    get_attr,
    get_owner,
)

__all__ = 'cache', 'class_property', 'mixed_property', 'pin'


class PropertyError(Exception): ...
class ContextFaultError(PropertyError): ...
class ReadOnlyError(PropertyError): ...
class AttributeException(PropertyError): ...  # noqa: N818


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


def extract_wrapped(desc):
    # when it's default instance-method replacer
    if Is.subclass(desc, InsteadProperty):
        return desc.__get__

    # when it's full-featured (cached) property
    if Is.subclass(desc, AbstractProperty):
        return desc.call

    # when it's builtin @property
    if Is.subclass(desc, property):
        return desc.fget

    # when wrapped functions stored in .func
    if Is.subclass(desc, cached_property):
        return desc.func

    raise NotImplementedError(
        f"couldn't extract wrapped function from {Who(desc)}: "
        f'replace it with @property, @cached_property, @{Who(pin)}, '
        f'or other descriptor derived from {Who(AbstractProperty)}')


def parent_call(func):

    @wraps(func)
    def parent_caller(node, *args, **kw):
        try:
            desc = get_attr(
                Is.classOf(node), func.__name__, exclude_self=True,
                index=func.__name__ not in Is.classOf(node).__dict__)

            return func(node, extract_wrapped(desc)(node, *args, **kw), *args, **kw)

        except RecursionError as e:
            raise RecursionError(
                f'{Who(node)}.{func.__name__} call real {Who(func)}, '
                f"couldn't reach parent descriptor; "
                f"maybe {Who(func)} it's mixin of {Who(node)}?") from e

    return parent_caller


def invokation_context_check(func):

    @wraps(func)
    def context(self, node, *args, **kw):
        if (
            (klass := self.klass) is not None and
            (node is None or klass != Is.Class(node))
        ):
            msg = (
                f'{Who(func)} exception, '
                f'{self.header_with_context(node)}, {node=}')

            if node is None and not klass:
                msg = f'{msg}; looks like as non-instance invokation'
            raise ContextFaultError(msg)

        return func(self, node, *args, **kw)
    return context


class AbstractProperty:
    @classmethod
    def with_parent(cls, function):
        return cls(parent_call(function))

    def __init__(self, function):
        self.function = function

    @cached_property
    def name(self):
        return self.function.__name__

    @property
    def title(self):
        raise NotImplementedError

    @cached_property
    def header(self):
        try:
            return f'{self.title}({self.function!a})'
        except Exception:  # noqa: BLE001
            return f'{self.title}({Who(self.function)})'

    def header_with_context(self, node):
        raise NotImplementedError


class CustomCallbackMixin:
    @classmethod
    def by(cls, callback):
        if not Is.subclass(cls, Cached):
            cls = Cached
        return partial(cls, is_actual=callback)

    expired_by = by

    @classmethod
    def ttl(cls, expire: float):
        if not isinstance(expire, float | int):
            raise TypeError(f'expire must be float or int, not {Who.Cast(expire)}')

        if expire <= 0:
            raise ValueError(f'expire must be positive number, not {expire!r}')

        def is_actual(self, node, value=Nothing):  # noqa: ARG001
            return (value + expire > time()) if value else time()

        return cls.by(is_actual)


class InsteadProperty(AbstractProperty, CustomCallbackMixin):
    def __init__(self, function):
        if iscoroutinefunction(function):
            raise TypeError(
                f'{Who(function)} is coroutine function, '
                'you must use @pin.native instead of just @pin')
        super().__init__(function)

    @cached_property
    def title(self):
        return f'instance just-replace-descriptor {Who(self, addr=True)}'

    def header_with_context(self, node):
        return (
            f'{self.header} called with '
            f'{("instance", "class")[Is.Class(node)]} '
            f'({Who(node, addr=True)})')

    def __get__(self, node, klass=Nothing):
        if node is None:
            raise ContextFaultError(self.header_with_context(klass))

        with suppress(KeyError):
            return node.__dict__[self.name]

        value = self.function(node)
        node.__dict__[self.name] = value
        return value

    def __delete__(self, node):
        raise ReadOnlyError(f'{self.header_with_context(node)}: deleter called')


class BaseProperty(AbstractProperty):

    klass = False
    readonly = False

    @InsteadProperty
    def is_data(self):
        return bool(hasattr(self, '__set__') or hasattr(self, '__delete__'))

    @InsteadProperty
    def title(self):
        mode = 'mixed' if self.klass is None else ('instance', 'class')[self.klass]

        prefix = ('', 'data ')[self.is_data]
        return (
            f'{mode} {prefix}descriptor '
            f'{Who(self, addr=True)}'.strip())

    def header_with_context(self, node):
        if node is None:
            mode = 'mixed' if self.klass is None else 'undefined'
        else:
            mode = ('instance', 'class')[Is.Class(node)]
        return (
            f'{self.header} with {mode} type called with'
            f'{("instance", "class")[Is.Class(node)]} '
            f'({Who(node, addr=True)})')

    @invokation_context_check
    def get_node(self, node):
        return node

    @invokation_context_check
    def call(self, node):
        try:
            value = self.function(node)
            if not iscoroutinefunction(self.function):
                return value
            return ensure_future(value)

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
    def make_from(cls, parent):
        """Make child-aware class from plain parent-based."""

        name = Who(parent, full=False)
        suffix = f'{"_" if name == name.lower() else ""}inherited'.capitalize()

        result = type(f'{name}{suffix}', (cls, parent), {})
        result.here = parent
        return result


class Cached(BaseProperty, CustomCallbackMixin):

    def __init__(self, function, is_actual=Nothing):
        super().__init__(function)

        if method := getattr(Is.classOf(self), 'is_actual', None):
            if is_actual:
                raise TypeError(
                    f'{Who.Is(self)}.is_actual method ({Who.Cast(method)}) '
                    f"can't override by is_actual kw: {Who.Cast(is_actual)}")
            is_actual = method
        self.is_actual = is_actual

    @invokation_context_check
    def get_cache(self, node):
        name = f'__{("instance", "class")[Is.Class(node)]}_memoized__'

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

            stored = self.get_cache(node)[self.name]
            if not self.is_actual:
                return stored

            value, stamp = stored
            if self.is_actual(self, node, stamp) is True:
                return value

        return self.__set__(node, super().call(obj))

    @invokation_context_check
    def __set__(self, node, value):
        cache = self.get_cache(node)

        if not self.is_actual:
            cache[self.name] = value
        else:
            cache[self.name] = value, self.is_actual(self, node)
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
        return get_owner(node, self.name) if Is.Class(node) else node


class MixedProperty(ClassProperty):
    klass = None

    def __get__(self, instance, klass):
        return self.call(instance or klass)


class ClassCachedProperty(ClassProperty, Cached):
    """Class-level cached property that passes the original class as the first
    positional argument and replaces the original data-descriptor."""


class MixedCachedProperty(MixedProperty, Cached):
    """Mixed-level cached property that replaces the original data-descriptor"""


class PreCachedProperty(MixedProperty, Cached):

    @invokation_context_check
    def __set__(self, node, value):
        if not Is.Class(node):
            return value
        return super().__set__(node, value)


class PostCachedProperty(MixedProperty, Cached):

    @invokation_context_check
    def __set__(self, node, value):
        if Is.Class(node):
            return value
        return super().__set__(node, value)

#

class pin(InsteadProperty):  # noqa: N801

    native = Cached
    cls = InheritedClass.make_from(ClassCachedProperty)
    any = InheritedClass.make_from(MixedCachedProperty)
    pre = InheritedClass.make_from(PreCachedProperty)
    post = InheritedClass.make_from(PostCachedProperty)


class class_property(ClassProperty): ...
class mixed_property(MixedProperty): ...
