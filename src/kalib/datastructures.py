import base64
from binascii import Error
from collections import deque
from contextlib import suppress
from datetime import date, datetime
from logging import getLogger
from pathlib import Path
from pickle import UnpicklingError
from pickle import dumps as generic_dumps
from pickle import loads as generic_loads
from typing import Any, ClassVar

import base58
import base2048
import orjson as json
from base2048 import DecodeError as EncoderException
from charded import Str
from charded.string import Charset
from orjson import (
    OPT_INDENT_2,
    OPT_NAIVE_UTC,
    OPT_NON_STR_KEYS,
    OPT_SERIALIZE_DATACLASS,
    OPT_SERIALIZE_NUMPY,
    OPT_SERIALIZE_UUID,
    OPT_SORT_KEYS,
    OPT_STRICT_INTEGER,
    JSONDecodeError,
)
from pydantic import BaseModel
from zstd import Error as CompressorException
from zstd import compress, decompress

from kain import (
    Is,
    Monkey,
    Nothing,
    Who,
    required,
    to_ascii,
    to_bytes,
)
from kalib.datetime import format_datetime

__all__ = (
    "dumps",
    "json",
    "loads",
    "pack",
    "unpack",
)

BACKENDS = {b"json": "orjson", b"ujson": "orjson"}
DEADBEEF = b"\xde\xad\xbe\xef"

serializers = {}
logger = getLogger(__name__)

OPT_JSON_FLAGS = (
    OPT_NAIVE_UTC
    | OPT_NON_STR_KEYS
    | OPT_SERIALIZE_DATACLASS
    | OPT_SERIALIZE_NUMPY
    | OPT_SERIALIZE_UUID
    | OPT_SORT_KEYS
    | OPT_STRICT_INTEGER
)


class SerializeError(Exception): ...


def default_serializer(obj, throw=True):

    if obj is Nothing:
        return None

    if isinstance(obj, datetime):
        return format_datetime(obj)

    if isinstance(obj, date):
        return obj.isoformat()

    if isinstance(obj, tuple) and type(obj).__mro__ == (
        type(obj),
        tuple,
        object,
    ):
        return (f"<{Who.Is(obj)}>", obj._asdict())

    with suppress(KeyError):
        result = serializers[Is.classOf(obj)](obj)
        if result is not Nothing:
            return result

    for types, callback in serializers.items():
        if isinstance(obj, types):
            result = callback(obj)
            if result is not Nothing:
                return result

    if throw:
        msg = f"couldn't serialize {Who.Is(obj)}"
        raise TypeError(msg)

    return Nothing


def serializer(*classes):

    direct_call = len(classes) == 2 and Is.function(
        classes[1],
    )

    def name(obj):
        return f"{Who.Addr(obj)} ({Who.File(obj)})"

    def serialize(func):

        order = [classes[0]] if direct_call else classes
        for cls in order:

            if isinstance(cls, bytes | str):
                cls = required(cls)  # noqa: PLW2901

            if cls in serializers:
                if Who.Name(serializers[cls]) == Who.Name(func) and Who.File(
                    serializers[cls],
                ) == Who.File(func):
                    continue

                logger.warning(
                    f"{Who.Is(cls)} already have registered serializer "
                    f"{name(serializers[cls])}, can't add another "
                    f"{name(func)}",
                )

                continue
            serializers[cls] = func

        title = Who.Is(func)
        msg = ", ".join(map(Who.Is, order))
        if not (direct_call or title.endswith(".<lambda>")):
            msg = f"{msg} -> {title}"

        logger.info(msg)
        return func

    return serialize(classes[1]) if direct_call else serialize


@Monkey.wrap(json, "dumps")
def to_json(func, data, /, **kw):

    minify = kw.pop("minify", True)
    option = kw.pop("option", Nothing)

    if option:
        flags = option or (0x0 if minify else OPT_INDENT_2)
        kw["option"] = OPT_JSON_FLAGS | flags

    elif not minify:
        # stdlib json with indent option
        kw.setdefault("indent", 2)
        kw.setdefault("sort_keys", True)

    kw.setdefault("default", default_serializer)
    binary = kw.pop("bytes", False)
    result = func(data, **kw)

    encode = (to_ascii, to_bytes)[binary]
    with suppress(UnicodeEncodeError, UnicodeDecodeError):
        return encode(result)

    encode = (Str.to_text, Str.to_bytes)[binary]
    return encode(result)


if OPT_JSON_FLAGS:
    json.JSONDecodeError = JSONDecodeError


@Monkey.bind(json, "repr")
def try_json(data, /, **kw):
    with suppress(Exception):
        if (
            hasattr(data, "as_dict")
            and (as_dict := data.as_dict)
            and isinstance(as_dict, dict)
        ):
            data = dict(as_dict)

    try:
        return to_json(data, **kw)

    except Exception:  # noqa: BLE001
        return repr(data)


@Monkey.bind(json)
def cast(obj):
    if Is.mapping(obj):
        result = to_json({k: cast(v) for k, v in obj.items()})

    elif isinstance(obj, tuple) and hasattr(obj, "_fields"):  # namedtuple
        result = to_json((f"<{Who.Is(obj)}>", obj._asdict()))

    elif isinstance(obj, deque | list | set | tuple):
        result = to_json(list(map(cast, obj)))

    elif Is.collection(obj):
        msg = f"couldn't serialize {Who.Cast(obj)}"
        raise TypeError(msg)

    else:
        result = to_json(obj)

    return json.loads(result)


class Encoding:

    Base16 = base64.b16encode, base64.b16decode, Charset.ASCII
    Base32 = base64.b32encode, base64.b32decode, Charset.ASCII
    Base58 = base58.b58encode, base58.b58decode, Charset.ASCII
    Base64 = base64.b64encode, base64.b64decode, Charset.ASCII
    Base85 = base64.b85encode, base64.b85decode, Charset.ASCII
    Base2048 = base2048.encode, base2048.decode, Charset.UTF8
    Codecs = (Base16, Base32, Base58, Base64, Base85, Base2048)

    Charsets: ClassVar[dict[str, tuple]] = {
        "0123456789ABCDEF": Base16,
        "234567=ABCDEFGHIJKLMNOPQRSTUVWXYZ": Base32,
        "+/0123456789=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz": Base64,
        (
            "!#$%&()*+-0123456789;<=>?@ABCDEFGHIJKLMNOPQ"
            "RSTUVWXYZ^_`abcdefghijklmnopqrstuvwxyz{|}~"
        ): Base85,
    }


def dumps(value, /, encoder=None, proto=None, ratio=None, charset=None):
    """Pickle & compress any object with any pickler with .dumps/loads methods
    and store module name with value for automatic unpickling."""

    if encoder is None:
        value = generic_dumps(value, proto or -1)

    else:
        encoder = to_bytes(encoder)
        if len(encoder) >= 32 - len(DEADBEEF):
            msg = (
                f"len({encoder=})={len(encoder):d} "
                f"must be lower than {32 - len(DEADBEEF):d}"
            )
            raise ValueError(msg)

        module = required(BACKENDS.get(encoder) or encoder)
        value = module.dumps(value)
        value = (
            encoder + DEADBEEF + to_bytes(value, charset=charset or Charset.UTF8)
        )

    return compress(value, ratio or 9)


def loads(value, /, expect=None):
    """Decompress pickled by dumps function objects with autodetect used module
    for marshallization.

    by default, expecting four exceptions for back compatibility with
    default dumb cache and pass all errors from cache
    """

    if value is None:
        return None

    if expect is None:
        expect = TypeError, ValueError, UnpicklingError, CompressorException

    try:
        value = decompress(value)

    except expect:
        with suppress(Exception):
            return json.loads(value)
        return None

    offset = value[:32].find(DEADBEEF)
    if offset != -1:
        encoder = to_bytes(value[:offset])
        return required(BACKENDS.get(encoder) or encoder).loads(
            value[offset + len(DEADBEEF) :],
        )

    with suppress(expect):
        return generic_loads(value)  # noqa: S301


def pack(value, *args, codec=Encoding.Base2048, **kw):
    """Pack value with codec prefix and encode it with codec"""

    return (
        bytes(hex(Encoding.Codecs.index(codec)), Charset.ASCII)[2:]
        + Str.to_bytes(codec[0](to_bytes(dumps(value, *args, **kw))), codec[2])
    ).decode(codec[2])


def unpack(string, *args, **kw):
    """Unpack string with codec prefix and try to decode it with codec"""

    last = kw.pop("last", False)
    try:
        codec = Encoding.Codecs[int(string[0])][1]
        return loads(codec(string[1:]), *args, **kw)

    except (IndexError, ValueError, Error):
        if last:
            return None

        with suppress(EncoderException, ValueError, Error):
            for charset in reversed(Encoding.Charsets):
                codec = Encoding.Codecs.index(Encoding.Charsets[charset])
                result = unpack(string.__class__(codec) + string, last=True)
                if result:
                    return result

            codec = Encoding.Codecs.index(Encoding.Base2048)
            result = unpack(string.__class__(codec) + string, last=True)
            if result:
                return result

        return loads(string, *args, **kw)


@serializer(Path)
def from_pathlib(obj: Path) -> str:
    return str(obj)


@serializer(BaseModel)
def from_pydantic(obj: BaseModel) -> dict[str, Any]:
    return obj.model_dump()
