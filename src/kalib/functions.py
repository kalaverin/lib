from kalib.internals import Who


def to_bytes(x, charset=None) -> bytes:
    if not isinstance(x, bytes | str):
        msg = f'only bytes | str acceptable, not {Who.Is(x)}'
        raise TypeError(msg)
    return x.encode(charset or 'ascii') if isinstance(x, str) else x


def to_ascii(x, *args, **kw) -> str:
    charset = kw.pop('charset', 'ascii')
    if not isinstance(x, bytes | str):
        msg = f'only bytes | str acceptable, not {Who.Is(x)}'
        raise TypeError(msg)
    return x if isinstance(x, str) else to_bytes(x, *args, **kw).decode(charset)
