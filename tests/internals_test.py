import syspath  # noqa: F401

from kalib.internals import Who


class DummyClass:

    def __init__(self, value):
        self.value = value


def test_is_with_address():
    obj = DummyClass(10)
    result = Who.Is(obj, addr=True)
    assert result.startswith(f'({Who(obj)}#')


def test_is_without_address():
    obj = DummyClass(10)
    result = Who.Is(obj, addr=False)
    assert result == Who.Is(obj, addr=False)


def test_is_with_class():
    obj = DummyClass
    result = Who.Is(obj, addr=True)
    assert result.startswith(f'{Who(obj)}#')


def test_is_with_none():
    obj = None
    result = Who.Is(obj, addr=True)
    assert result.startswith(f'({Who(obj)}#')
