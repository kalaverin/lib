import pytest

from kalib.functions import to_ascii, to_bytes


def test_to_bytes_with_str():
    assert to_bytes('hello') == b'hello'
    assert to_bytes('hello', 'utf-8') == b'hello'

def test_to_bytes_with_bytes():
    assert to_bytes(b'hello') == b'hello'

def test_to_bytes_invalid_type():
    with pytest.raises(TypeError):
        to_bytes(123)

def test_to_ascii_with_str():
    assert to_ascii('hello') == 'hello'

def test_to_ascii_with_bytes():
    assert to_ascii(b'hello') == 'hello'
    assert to_ascii(b'hello', charset='utf-8') == 'hello'

def test_to_ascii_invalid_type():
    with pytest.raises(TypeError):
        to_ascii(123)
