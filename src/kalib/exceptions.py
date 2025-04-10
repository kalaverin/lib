from collections import namedtuple
from datetime import date, datetime
from traceback import format_exception

from kalib.datastructures import json
from kalib.internals import Who
from kalib.text import Str


class ExceptionInformation(namedtuple('Exception', 'arguments message reason trace')):
    __slots__ = ()

    @property
    def as_dict(self):
        return self._asdict()


def exception(e):
    def trim(x):
        return tuple(i.rstrip() for i in x)

    def select_primitives_only(e):
        if (args := getattr(e, 'args', None)):
            result = []
            for item in args:
                if not item:
                    continue

                # TODO: replace with datastructures.cast

                if isinstance(item, list | set):
                    item = tuple(item)  # noqa: PLW2901

                elif isinstance(item, date | datetime):
                    item = item.isoformat()  # noqa: PLW2901

                elif isinstance(item, bytes | float | int | str | tuple):
                    ...

                else:
                    try:
                        item = json.dumps(item)  # noqa: PLW2901
                    except Exception:  # noqa: S112, BLE001
                        continue

                result.append(item)

            if result:
                return json.dumps(result)

    arguments = select_primitives_only(e)
    message = Str(e).strip() or None

    return ExceptionInformation(
        arguments, message,
        f'{Who(e)}({arguments}) {message or ""}',
        '\n'.join(trim(format_exception(e))))
