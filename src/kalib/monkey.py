from contextlib import suppress
from functools import wraps
from typing import ClassVar

from kalib.importer import required
from kalib.internals import Who, is_module
from kalib.loggers import Logging


class Monkey(Logging.Mixin):

    mapping: ClassVar[dict] = {}

    @classmethod
    def expect(cls, *exceptions):
        def make_wrapper(func):
            @wraps(func)
            def wrapper(klass, *args, **kw):
                with suppress(exceptions):
                    return func(klass, *args, **kw)
            return classmethod(wrapper)
        return make_wrapper

    @classmethod
    def patch(cls, module, new):

        if isinstance(module, tuple):
            node, name = module

        elif is_module(module):
            node, name = module, new.__name__

        else:
            path, name = module.rsplit('.', 1)
            try:
                node = required(path)
            except ImportError:
                cls.log.error(f'{module=} import error')  # noqa: TRY400
                raise

        if getattr(node, name, None) is new:
            return new

        old = required(node, name) if Who(node, full=False) != name else node

        setattr(node, name, new)
        new = getattr(node, name)
        if old is new:
            raise RuntimeError

        cls.mapping[new] = old
        cls.log.debug(f'{Who(old, addr=True)} -> {Who(new, addr=True)}')
        return new

    @classmethod
    def bind(cls, node, name=None, decorator=None):
        node = required(node) if isinstance(node, str) else node

        def bind(func):
            @wraps(func)
            def wrapper(*args, **kw):
                if decorator is classmethod:
                    return func(node, *args, **kw)
                return func(*args, **kw)

            local = name or func.__name__
            setattr(node, local, wrapper)
            cls.log.verbose(f'{Who(node)}.{local} <- {Who(func, addr=True)}')
            return wrapper

        return bind

    @classmethod
    def wrap(cls, node, name=None, decorator=None):
        node = required(node) if isinstance(node, str) else node

        def wrap(func):

            wrapped_name = name or func.__name__
            if Who(node, full=False) != wrapped_name:
                wrapped_func = required(node, wrapped_name)
            else:
                wrapped_func = node

            @wraps(func)
            def wrapper(*args, **kw):
                return func(wrapped_func, *args, **kw)

            cls.log.verbose(
                f'{Who(node)}.{wrapped_name} <- '
                f'{Who(func, addr=True)}')

            wrapped = decorator(wrapper) if decorator else wrapper
            cls.patch((node, wrapped_name), wrapped)
            return wrapper

        return wrap
