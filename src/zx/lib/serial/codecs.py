"""Base-N byte codecs with a codec-index header.

Header format: a single raw byte — the index into `Algorithm.Codecs`.
"""

import base64
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

import base58
import base2048

from zx.lib.serial.errors import DeserializeError
from zx.str import varchar
from zx.str.varchar import Charset

__all__ = (
    "decode",
    "encode",
)


@dataclass(frozen=True)
class AlgorithmType:
    charset: Charset
    encode: Callable[[bytes], bytes] | Callable[[bytes], str]
    decode: Callable[[str], bytes]


class Algorithm:
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
    Base2k = AlgorithmType(
        charset=Charset.UTF8,
        encode=base2048.encode,
        decode=base2048.decode,
    )

    # ensure the order of codecs is preserved for unpacking

    Codecs: ClassVar[tuple[AlgorithmType, ...]] = (
        Base16,
        Base32,
        Base58,
        Base64,
        Base85,
        Base2k,
    )


def encode(
    obj: bytes,
    algo: AlgorithmType = Algorithm.Base2k,
) -> bytes:
    header = bytes([Algorithm.Codecs.index(algo)])
    body = varchar.to_bytes(algo.encode(obj), algo.charset)
    return header + body


def decode(obj: bytes) -> bytes:
    if not obj:
        msg = "cannot decode empty object: missing codec header"
        raise DeserializeError(msg)

    index = obj[0]
    try:
        algo: AlgorithmType = Algorithm.Codecs[index]
    except IndexError as exc:
        msg = f"unknown codec index: {index}"
        raise DeserializeError(msg) from exc

    return algo.decode(varchar.to_text(obj[1:], algo.charset))
