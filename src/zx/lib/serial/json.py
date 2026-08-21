"""JSON (de)serialization contour over orjson with project conventions.

The contour funnels every payload through a single pair of entry points
(`dumps`/`to_json`) so that orjson options, the `SERIALIZER_REGISTRY`
lookup, project sentinels (`Nothing`, `Missing`), and error behavior
(`Behavior`) stay consistent across call sites.

All dump functions return bytes (the orjson convention); `stringify` is
the safe string facade for logging and error messages.
"""

from collections import deque
from contextlib import suppress
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from functools import partial
from logging import getLogger
from typing import Any, Literal

from orjson import (
    OPT_INDENT_2,
    OPT_NAIVE_UTC,
    OPT_NON_STR_KEYS,
    OPT_SERIALIZE_DATACLASS,
    OPT_SERIALIZE_NUMPY,
    OPT_SERIALIZE_UUID,
    OPT_SORT_KEYS,
    OPT_STRICT_INTEGER,
)
from orjson import dumps as dumps_function
from orjson import loads as loads_function

from zx.core import Is, Who
from zx.core.classes import Missing, Nothing
from zx.lib.datetime import dt
from zx.lib.serial.errors import SerializationError
from zx.lib.serial.registry import SERIALIZER_REGISTRY
from zx.str import varchar

__all__ = (
    "dumps",
    "jsonize",
    "stringify",
    "to_json",
)

JSONType = dict[str, Any] | list[Any] | float | int | str | None

ORJSON_DEFAULT_OPTIONS = (
    OPT_NAIVE_UTC
    | OPT_NON_STR_KEYS
    | OPT_SERIALIZE_DATACLASS
    | OPT_SERIALIZE_NUMPY
    | OPT_SERIALIZE_UUID
    | OPT_SORT_KEYS
    | OPT_STRICT_INTEGER
)

logger = getLogger(__name__)


type Behavior = Literal[
    "cast",
    "ignore",
    "name",
    "print",
    "raise",
    "repr",
]


def jsonize(obj: object, on_error: Behavior = "raise") -> JSONType:
    """Round-trip an object through JSON into pure JSON-safe types.

    Args:
        obj: Any object the contour can serialize.
        on_error: Behavior forwarded to the nested :func:`to_json` call,
            so recursive normalization honors the caller's policy.

    Returns:
        The equivalent structure built of dict/list/str/int/float/None.
    """
    return loads_function(to_json(obj, on_error=on_error))


def to_json(
    obj: object,
    /,
    minify: bool = True,
    option: int | Missing = Nothing,
    on_error: Behavior = "raise",
) -> bytes:
    """Recursively normalize containers, then dump to JSON bytes.

    Dataclasses, dicts, and sequence/set containers are walked and every
    value is `jsonize`d, so nested custom types always pass through the
    encoding hook. Collections outside the supported set are rejected.

    Args:
        obj: The object to serialize.
        minify: Compact output when True, 2-space indent when False.
        option: Raw orjson option mask; Nothing selects the defaults.
        on_error: Behavior for unserializable leaves.

    Returns:
        The JSON payload as bytes.

    Raises:
        SerializationError: For collections that are not a dataclass,
            deque, dict, list, set, or tuple.
    """
    if is_dataclass(obj if isinstance(obj, type) else type(obj)):
        result = {k: jsonize(v, on_error) for k, v in asdict(obj).items()}

    elif isinstance(obj, dict):
        result = {k: jsonize(v, on_error) for k, v in obj.items()}

    elif isinstance(obj, deque | list | set | tuple):
        result = [jsonize(i, on_error) for i in obj]

    elif Is.collection(obj):
        msg = "collection is not a dataclass, deque, dict, list, set or tuple"
        logger.warning(
            msg,
            extra={"collection": Who.Cast(obj)},
        )
        raise SerializationError(msg)

    else:
        result = obj

    return dumps(
        result,
        minify=minify,
        option=option,
        on_error=on_error,
    )


def dumps(
    obj: object,
    /,
    minify: bool = True,
    option: int | Missing = Nothing,
    on_error: Behavior = "raise",
) -> bytes:
    """Dump an object to JSON bytes via orjson with project defaults.

    Args:
        obj: The object to serialize.
        minify: Compact output when True; False adds OPT_INDENT_2 on top
            of the default option mask.
        option: Raw orjson option mask; Nothing selects
            ORJSON_DEFAULT_OPTIONS (plus indentation when not minifying).
        on_error: Behavior forwarded to the `encode_object` default hook.

    Returns:
        The JSON payload as bytes.
    """
    if isinstance(option, Missing):
        option = ORJSON_DEFAULT_OPTIONS | (0 if minify else OPT_INDENT_2)

    return dumps_function(
        obj,
        default=partial(encode_object, on_error=on_error),
        option=option,
    )


def repr_or_die(
    obj: object,
    /,
    on_error: Behavior = "raise",
) -> str | None:
    """Render an unserializable object per the requested behavior.

    Args:
        obj: The object that failed serialization.
        on_error: cast -> Who.Cast, name -> Who.Is, print -> str,
            repr -> repr, ignore -> None (debug-logged); anything else
            (including "raise") is an error-logged NotImplementedError.

    Returns:
        The rendered string, or None for the "ignore" behavior.

    Raises:
        NotImplementedError: For "raise" or an unknown behavior.
    """
    msg = "unsupported type"

    match on_error:
        case "cast":
            return Who.Cast(obj)

        case "name":
            return Who.Is(obj)

        case "print":
            return str(obj)

        case "repr":
            return repr(obj)

        case "ignore":
            logger.debug(msg, extra={"object": Who.Cast(obj)})
            return None

    logger.error(msg, extra={"object": Who.Cast(obj)})
    raise NotImplementedError(msg)


def encode_object(  # noqa: PLR0911
    obj: object,
    /,
    on_error: Behavior = "raise",
) -> JSONType:
    """Encode one non-native object into JSON-serializable values.

    Dispatch order: Nothing -> None; bytes -> text; str -> verbatim;
    datetime -> naive isoformat verbatim, aware via the project dt
    string; date -> ISO format; exact-class hit
    in SERIALIZER_REGISTRY (a Nothing result skips the class); then an
    isinstance scan of the registry for subclasses. A registry callback
    returning Nothing never produces a value.

    Args:
        obj: The object orjson could not serialize natively.
        on_error: Behavior when no encoder matches.

    Returns:
        A JSON-serializable replacement value.

    Raises:
        TypeError: When on_error is "raise" and no encoder matched.
    """
    if obj is Nothing:
        return None

    if isinstance(obj, bytes):
        return varchar.to_text(obj)

    if isinstance(obj, str):
        return obj

    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            return obj.isoformat()
        return str(dt(obj))

    if isinstance(obj, date):
        return obj.isoformat()

    with suppress(KeyError):
        result = SERIALIZER_REGISTRY[Is.classOf(obj)](obj)
        if result is not Nothing:
            return result

    for types, callback in SERIALIZER_REGISTRY.items():
        if isinstance(obj, types):
            result = callback(obj)
            if result is not Nothing:
                return result

    if on_error == "raise":
        if Is.Class(obj):
            msg = f"cannot serialize class {Who.Is(obj)}"
        else:
            msg = f"couldn't serialize {Who.Is(obj)}"
        raise TypeError(msg)

    return repr_or_die(obj, on_error=on_error)


def stringify(
    obj: object,
    /,
    minify: bool = True,
    option: int | Missing = Nothing,
    on_error: Behavior = "raise",
) -> str:
    """Serialize anything to a JSON string, never raising.

    The first attempt honors the requested behavior; on any failure the
    exception is logged and the object is re-serialized with
    on_error="name", so unserializable leaves degrade to class names.

    Args:
        obj: The object to serialize.
        minify: Compact output when True, 2-space indent when False.
        option: Raw orjson option mask; Nothing selects the defaults.
        on_error: Behavior for the first (strict) attempt.

    Returns:
        The JSON payload as text.
    """
    try:
        return varchar.to_text(
            to_json(
                obj,
                minify=minify,
                option=option,
                on_error=on_error,
            ),
        )

    except Exception:
        logger.exception(
            "failed to serialize object",
            extra={"object": Who.Cast(obj)},
        )

    return varchar.to_text(
        to_json(
            obj,
            minify=minify,
            option=option,
            on_error="name",
        ),
    )
