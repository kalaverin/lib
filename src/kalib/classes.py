from kalib.internals import Who

__all__ = 'Nothing', 'Singleton'


class Singleton(type):

    def __init__(cls, name, parents, attrbutes):
        super().__init__(name, parents, attrbutes)

    def __call__(cls, *args, **kw):
        if not hasattr(cls, 'instance'):
            cls.instance = super().__call__(*args, **kw)
        return cls.instance


class Missing(metaclass=Singleton):

    def __bool__(self):
        return False

    def __repr__(self):
        return f'<{Who.Name(self)}>'


# This is a singleton, so it's safe to use it as a sentinel

Nothing = Missing()
