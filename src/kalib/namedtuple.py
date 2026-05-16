from collections import namedtuple
from functools import lru_cache
from keyword import kwlist

from natsort import natsorted

from kain import Who

RESERVED_KEYSET = frozenset(kwlist)


@lru_cache(2 * 10)
def namedtuple_builder(*fields, name=None):

    fields_set = set(fields)
    if len(fields) != len(fields_set):
        raise ValueError(f"{fields=} must be unique")

    if RESERVED_KEYSET & fields_set:
        reserved = tuple(natsorted(RESERVED_KEYSET & fields_set))
        raise ValueError(
            f"{fields=} must not contain keywords what's {reserved=}",
        )

    return namedtuple(name or "Tuple", fields)


def Tuple(*args, **kw):  # noqa: N802
    name = kw.pop("name", None)
    rename = kw.pop("rename", False)
    sort_keys = kw.pop("sort_keys", True)

    if not name and kw and len(args) == 1 and isinstance(args[0], str):
        # this is: Tuple('MyTuple', **kw)
        return make_namedtuple(kw, args[0], rename, sort_keys)

    if not kw and len(args) == 1:
        # this is: Tuple(namedtuple) or Tuple(dict, **kw)
        return make_namedtuple(args[0], name, rename, sort_keys)

    if not args and kw:  # this is Tuple(**data) style
        if name is None and rename is False and sort_keys is True:
            # this is: Tuple(**data)
            return make_namedtuple(kw, name, rename, sort_keys)

        fields = []
        if name is not None:
            fields.append(name)

        if rename is not False:
            fields.append(rename)

        if sort_keys is not True:
            fields.append(sort_keys)

        fields.sorted()

        raise TypeError(
            "Tuple() used with **kw style but kw contains "
            f"Tuple{fields} reserved keys",
        )

    raise TypeError(f"Tuple({Who.Args(*args, **kw)})")


def make_namedtuple(
    data: dict | tuple,
    name: str | None,
    rename: bool,
    sort_keys: bool,
):
    if isinstance(data, tuple) and hasattr(data, "_asdict"):
        return data  # collections.namedtuple itself

    if not isinstance(data, dict):
        raise TypeError(f"expected dict, got {Who.Is(data)}")

    keys = tuple(natsorted(data) if sort_keys else data)

    if not rename:
        fields = tuple(keys)
    else:
        fields = tuple(f"{k}_" if k in RESERVED_KEYSET else k for k in keys)

    return namedtuple_builder(*fields, name=name)(*map(data.__getitem__, keys))
