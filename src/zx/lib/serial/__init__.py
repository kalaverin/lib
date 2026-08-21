"""Serialization scope: JSON contour, serializer registry, binary
container, and base-N codecs."""

from zx.lib.serial.codecs import decode, encode
from zx.lib.serial.container import (
    CompressorName,
    MarshallName,
    pack,
    unpack,
)
from zx.lib.serial.errors import (
    DeserializeError,
    RegistryError,
    SerializationError,
    SerializeError,
)
from zx.lib.serial.json import (
    ORJSON_DEFAULT_OPTIONS,
    JSONType,
    dumps,
    jsonize,
    stringify,
    to_json,
)
from zx.lib.serial.registry import SERIALIZER_REGISTRY, serializer

__all__ = (
    "ORJSON_DEFAULT_OPTIONS",
    "SERIALIZER_REGISTRY",
    "CompressorName",
    "DeserializeError",
    "JSONType",
    "MarshallName",
    "RegistryError",
    "SerializationError",
    "SerializeError",
    "decode",
    "dumps",
    "encode",
    "jsonize",
    "pack",
    "serializer",
    "stringify",
    "to_json",
    "unpack",
)
