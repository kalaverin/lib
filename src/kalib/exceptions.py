from contextlib import suppress
from traceback import format_exception
from typing import NamedTuple

from charded import Str
from kain import Who

from kalib.datastructures import json, serializer


class Error(NamedTuple):
    type      : str
    arguments : tuple | None
    message   : str | None
    reason    : str
    trace     : tuple | None

    @property
    def as_dict(self):  # typing: ignore[flake8-typing-imports]
        return self._asdict()


@serializer(Error)
def from_error(error):
    return error._asdict()


def exception(e):
    def trim(x):
        return tuple(i.rstrip() for i in x)

    arguments = None
    if (args := getattr(e, 'args', None)):
        result = []
        for item in args:
            with suppress(Exception):
                result.append(str(json.cast(item, throw=True)))
                continue

            with suppress(Exception):
                result.append(Who.Cast(item))
                continue

            with suppress(Exception):
                result.append(repr(item))

        arguments = tuple(result)

    reason = f'{Who(e)}({json.repr(arguments)[1:-1]})'
    if message := getattr(e, 'message', '').strip():
        reason = f'{reason}: {message}'

    return Error(
        Who(e),
        arguments,
        Str(e).strip() or None,
        reason,
        trim(format_exception(e)) or None)
