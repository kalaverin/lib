"""Base-N byte codecs with a codec-index header.

Header format: a single raw byte — the index into the codec table
(`Algorithm` definition order).
"""

import base64
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import ClassVar, Literal

import base58

from zx.lib.serial.errors import DeserializeError
from zx.str import varchar
from zx.str.varchar import Charset

type AlgorithmName = Literal["base16", "base32", "base58", "base64", "base85"]

__all__ = (
    "Algorithm",
    "AlgorithmName",
    "Codecs",
    "decode",
    "encode",
)


class Algorithm(StrEnum):
    """Wire codec identifiers; the definition order IS the header index."""

    Base16 = auto()
    Base32 = auto()
    Base58 = auto()
    Base64 = auto()
    Base85 = auto()


@dataclass(frozen=True)
class AlgorithmType:
    charset: Charset
    encode: Callable[[bytes], bytes] | Callable[[bytes], str]
    decode: Callable[[str], bytes]


class Codecs:
    """Codec registry: members mirror `Algorithm`, keyed by the enum."""

    Base16 = AlgorithmType(
        charset=Charset.ASCII,
        encode=base64.b16encode,
        decode=base64.b16decode,
    )
    Base32 = AlgorithmType(
        charset=Charset.ASCII,
        encode=base64.b32encode,
        decode=base64.b32decode,
    )
    Base58 = AlgorithmType(
        charset=Charset.ASCII,
        encode=base58.b58encode,
        decode=base58.b58decode,
    )
    Base64 = AlgorithmType(
        charset=Charset.ASCII,
        encode=base64.b64encode,
        decode=base64.b64decode,
    )
    Base85 = AlgorithmType(
        charset=Charset.ASCII,
        encode=base64.b85encode,
        decode=base64.b85decode,
    )

    Mapping: ClassVar[dict[str, AlgorithmType]] = {
        Algorithm.Base16: Base16,
        Algorithm.Base32: Base32,
        Algorithm.Base58: Base58,
        Algorithm.Base64: Base64,
        Algorithm.Base85: Base85,
    }


ORDER: tuple[Algorithm, ...] = tuple(Algorithm)  # the wire index table


def encode(
    obj: bytes,
    algo: AlgorithmName = "base85",
) -> bytes:
    """Encode `obj`, prefixing the codec-index header byte.

    Args:
        obj: The raw bytes to encode.
        algo: The codec name ("base85" by default).

    Raises:
        ValueError: The name is not a registered `Algorithm`.
    """
    algorithm = Algorithm(algo)
    codec = Codecs.Mapping[algorithm]
    header = bytes([ORDER.index(algorithm)])
    body = varchar.to_bytes(codec.encode(obj), codec.charset)
    return header + body


def decode(obj: bytes) -> bytes:
    if not obj:
        msg = "cannot decode empty object: missing codec header"
        raise DeserializeError(msg)

    index = obj[0]
    try:
        algorithm: Algorithm = ORDER[index]
    except IndexError as exc:
        msg = f"unknown codec index: {index}"
        raise DeserializeError(msg) from exc

    codec = Codecs.Mapping[algorithm]
    return codec.decode(varchar.to_text(obj[1:], codec.charset))
