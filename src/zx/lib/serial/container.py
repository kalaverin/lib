"""Binary container: marshalled payload with a codec header, compressed."""

import pickle as pc
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from logging import getLogger
from typing import ClassVar, Literal

import lz4.block
import zstd
from orjson import loads as loads_function
from zstd import Error as CompressorException

from zx.core import Who, to_ascii, to_bytes
from zx.lib.serial.json import dumps

__all__ = (
    "CompressorName",
    "MarshallName",
    "pack",
    "unpack",
)

type MarshallName = Literal["json", "pickle"]
type CompressorName = Literal["zstd", "lz4"]

DEADBEEF = b"\xde\xad\xbe\xef"

UNPICKLING_EXPECTED_EXCEPTIONS = (
    CompressorException,
    TypeError,
    ValueError,
    pc.UnpicklingError,
)

logger = getLogger(__name__)


class Marshall(StrEnum):
    JSON = auto()
    Pickle = auto()


class Compressor(StrEnum):
    ZSTD = auto()
    LZ4 = auto()


@dataclass(frozen=True)
class MarshallType:
    encode: Callable[[object], bytes]
    decode: Callable[[bytes], object]


@dataclass(frozen=True)
class CompressorType:
    shrink: Callable[[bytes], bytes]
    expand: Callable[[bytes], bytes]


class Marshallers:
    JSON = MarshallType(
        encode=dumps,
        decode=loads_function,
    )
    Pickle = MarshallType(
        encode=pc.dumps,
        decode=pc.loads,
    )
    Mapping: ClassVar[dict[str, MarshallType]] = {
        Marshall.JSON: JSON,
        Marshall.Pickle: Pickle,
    }


class Compressors:
    ZSTD = CompressorType(shrink=zstd.compress, expand=zstd.decompress)
    LZ4 = CompressorType(
        shrink=lz4.block.compress,
        expand=lz4.block.decompress,
    )
    Mapping: ClassVar[dict[str, CompressorType]] = {
        Compressor.ZSTD: ZSTD,
        Compressor.LZ4: LZ4,
    }


def pack(
    obj: object,
    /,
    encoder: MarshallName = "json",
    compressor: CompressorName = "zstd",
    **kw: int | str,
) -> bytes:
    """Marshal `obj`, compress the payload, prefix a plain codec header.

    `kw` is forwarded verbatim to the compressor callable. Note: the stock
    zstd binding takes no keyword arguments, so `kw` is inert unless
    `Compressors.Mapping` is customized with kwarg-accepting callables.
    """
    data_encoder = Marshallers.Mapping[Marshall(encoder)]
    data_compressor = Compressors.Mapping[Compressor(compressor)]
    header = to_bytes(f"{compressor}:{encoder}")
    return (
        header
        + DEADBEEF
        + data_compressor.shrink(data_encoder.encode(obj), **kw)
    )


def unpack(obj: bytes) -> object:
    """Inverse of `pack`: parse the plain header, expand, decode."""
    offset = obj[:32].find(DEADBEEF)
    if offset == -1:
        raise ValueError("invalid packed object: missing DEADBEEF marker")

    compressor_name, encoder_name = to_ascii(obj[:offset]).split(":", 1)
    decoder = Marshallers.Mapping[Marshall(encoder_name)]
    decompressor = Compressors.Mapping[Compressor(compressor_name)]

    try:
        decompressed = decompressor.expand(obj[offset + len(DEADBEEF) :])
    except UNPICKLING_EXPECTED_EXCEPTIONS:
        logger.exception(
            "failed to decompress object",
            extra={"object": Who.Cast(obj)},
        )
        raise
    except Exception:
        logger.exception(
            "unexpected error during decompression",
            extra={"object": Who.Cast(obj)},
        )
        raise

    try:
        return decoder.decode(decompressed)
    except UNPICKLING_EXPECTED_EXCEPTIONS:
        logger.exception(
            "failed to decode object",
            extra={"object": Who.Cast(obj)},
        )
        raise
    except Exception:
        logger.exception(
            "unexpected error during decoding",
            extra={"object": Who.Cast(obj)},
        )
        raise
