"""The serializer registry and the `@serializer` decorator.

Duplicate registration of a different serializer for the same class raises
`RegistryError`; re-registering the same function is a silent no-op.
"""

from __future__ import annotations

from collections.abc import Callable
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from zx.core import Is, Who, required
from zx.lib.serial.errors import RegistryError

if TYPE_CHECKING:
    from zx.lib.serial.json import JSONType

SerializerFunction = Callable[[object], "JSONType"]
SerializerDecorator = Callable[[SerializerFunction], SerializerFunction]

SERIALIZER_REGISTRY: dict[type, SerializerFunction] = {}

_DIRECT_CALL_ARGUMENTS = 2

logger = getLogger(__name__)


def serializer(
    *classes: type | str | bytes | SerializerFunction,
) -> SerializerFunction | SerializerDecorator:

    direct_call = len(classes) == _DIRECT_CALL_ARGUMENTS and Is.function(
        classes[1],
    )

    def name(obj: object) -> str:
        return f"{Who.Addr(obj)}({Who.File(obj)})"

    def serialize(func: SerializerFunction) -> SerializerFunction:

        order = [classes[0]] if direct_call else classes
        for cls in order:
            if isinstance(cls, bytes | str):
                cls = required(cls)  # noqa: PLW2901

            if cls in SERIALIZER_REGISTRY:
                registered = SERIALIZER_REGISTRY[cls]
                if Who.Name(registered) == Who.Name(func) and Who.File(
                    registered,
                ) == Who.File(func):
                    continue

                msg = (
                    f"serializer already registered for {Who.Cast(cls)}: "
                    f"{name(registered)}; refusing {name(func)}"
                )
                raise RegistryError(msg)
            SERIALIZER_REGISTRY[cls] = func

        title = Who.Is(func)
        msg = ", ".join(map(Who.Is, order))
        if not (direct_call or title.endswith(".<lambda>")):
            msg = f"{msg} -> {title}"

        logger.info(
            "registered serializer",
            extra={
                "serializer": title,
                "class": Who.Cast(order[0]),
                "mapping": msg,
            },
        )
        return func

    return serialize(classes[1]) if direct_call else serialize


@serializer(Path)
def from_pathlib(obj: Path) -> JSONType:
    return str(obj)


@serializer(BaseModel)
def from_pydantic(obj: BaseModel) -> JSONType:
    return obj.model_dump()
