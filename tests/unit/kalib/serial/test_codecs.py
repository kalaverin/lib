"""Tests for `zx.lib.serial.codecs` — base-N codecs with an index header."""

import binascii
import dataclasses
from typing import TYPE_CHECKING

import pytest
from faker import Faker

from zx.lib.serial.codecs import (
    ORDER,
    Algorithm,
    AlgorithmType,
    Codecs,
    decode,
    encode,
)
from zx.lib.serial.errors import DeserializeError

if TYPE_CHECKING:
    from collections.abc import Callable

CODEC_IDS = ("base16", "base32", "base58", "base64", "base85")
CODEC_COUNT = len(ORDER)
ASCII_BOUNDARY = 128

EDGE_PAYLOADS: tuple[bytes, ...] = (
    b"",
    b"\x00",
    b"\xff" * 16,
    bytes(range(256)),
    "Unicode ✓ текст テスト".encode(),
)
EDGE_PAYLOAD_IDS = (
    "empty",
    "single-nul",
    "all-ff",
    "all-byte-values",
    "unicode-utf8",
)

RANDOM_PAYLOAD_SIZES = (1, 64, 4096)
RANDOM_PAYLOAD_IDS = tuple(f"binary-{size}" for size in RANDOM_PAYLOAD_SIZES)

codec_indices = pytest.mark.parametrize(
    "codec_index",
    range(CODEC_COUNT),
    ids=CODEC_IDS,
)


# --- round-trip ---


@codec_indices
@pytest.mark.parametrize("payload", EDGE_PAYLOADS, ids=EDGE_PAYLOAD_IDS)
def test_encode_decode_round_trip_edge_payloads(
    payload: bytes,
    codec_index: int,
) -> None:
    """
    Given: a parametrized edge payload and codec.
    When: the payload is encoded and decoded back.
    Then: the original bytes are returned and the header is the codec index.
    """
    # --- Arrange ---
    algorithm = ORDER[codec_index]

    # --- Act ---
    encoded = encode(payload, algorithm.value)

    # --- Assert ---
    assert encoded[0] == codec_index
    assert decode(encoded) == payload


@codec_indices
@pytest.mark.parametrize("size", RANDOM_PAYLOAD_SIZES, ids=RANDOM_PAYLOAD_IDS)
def test_encode_decode_round_trip_random_binary(
    fake: Faker,
    codec_index: int,
    size: int,
) -> None:
    """
    Given: a faker-driven binary payload of parametrized size.
    When: it is encoded and decoded back.
    Then: the original bytes are returned and the header is the codec index.
    """
    # --- Arrange ---
    payload = fake.binary(length=size)
    algorithm = ORDER[codec_index]

    # --- Act ---
    encoded = encode(payload, algorithm.value)

    # --- Assert ---
    assert encoded[0] == codec_index
    assert decode(encoded) == payload


# --- wire format ---


@pytest.mark.parametrize(
    "codec_index,is_ascii",
    (
        (0, True),
        (1, True),
        (2, True),
        (3, True),
        (4, True),
    ),
    ids=CODEC_IDS,
)
def test_encode_body_respects_declared_charset(
    codec_index: int,
    *,
    is_ascii: bool,
) -> None:
    """
    Given: a payload containing every possible byte value.
    When: it is encoded with a parametrized codec.
    Then: the body stays within the codec's declared charset.
    """
    # --- Arrange ---
    payload = bytes(range(256))
    algorithm = ORDER[codec_index]

    # --- Act ---
    encoded = encode(payload, algorithm.value)
    body = encoded[1:]

    # --- Assert ---
    if is_ascii:
        assert all(byte < ASCII_BOUNDARY for byte in body)
    else:
        assert any(byte >= ASCII_BOUNDARY for byte in body)


# --- decode faults ---


def test_decode_empty_input_raises_deserialize_error() -> None:
    """
    Given: an empty byte string carrying no codec header.
    When: it is decoded.
    Then: a DeserializeError explaining the missing header is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(DeserializeError, match="missing codec header"):
        decode(b"")


@pytest.mark.parametrize(
    "index",
    (CODEC_COUNT, 200, 255),
    ids=("first-invalid", "high", "max"),
)
def test_decode_unknown_codec_index_raises_deserialize_error(
    fake: Faker,
    index: int,
) -> None:
    """
    Given: a blob whose header byte is outside the codec table.
    When: it is decoded.
    Then: a DeserializeError naming the unknown index is raised.
    """
    # --- Arrange ---
    blob = bytes([index]) + fake.binary(length=8)

    # --- Act / Assert ---
    with pytest.raises(
        DeserializeError,
        match=f"unknown codec index: {index}",
    ):
        decode(blob)


@codec_indices
def test_decode_invalid_charset_body_raises_unicode_decode_error(
    codec_index: int,
) -> None:
    """
    Given: a valid header followed by bytes illegal in the codec charset.
    When: the blob is decoded.
    Then: a UnicodeDecodeError is raised before codec decoding begins.
    """
    # --- Arrange ---
    blob = bytes([codec_index]) + b"\xff\xff"

    # --- Act / Assert ---
    with pytest.raises(UnicodeDecodeError):
        decode(blob)


@pytest.mark.parametrize(
    "codec_index,fault",
    (
        (0, binascii.Error),
        (1, binascii.Error),
        (2, ValueError),
        (3, None),  # base64 ignores illegal characters — leniency pin
        (4, None),  # base85 ignores illegal characters — leniency pin
    ),
    ids=CODEC_IDS,
)
def test_decode_garbled_body_fault_behavior(
    codec_index: int,
    fault: type[Exception] | None,
) -> None:
    """
    Given: a valid header followed by ASCII garbage outside the alphabet.
    When: the blob is decoded.
    Then: the codec-specific fault behavior holds (strict raise or pass).
    """
    # --- Arrange ---
    blob = bytes([codec_index]) + b"!!!!"

    # --- Act / Assert ---
    if fault is None:
        assert isinstance(decode(blob), bytes)
    else:
        with pytest.raises(fault):
            decode(blob)


# --- codec table integrity ---


def test_codec_table_is_unique_and_positional() -> None:
    """
    Given: the codec table.
    When: indexes are inspected.
    Then: every codec sits at a unique position matching its index lookup.
    """
    # --- Arrange ---

    # --- Act ---
    indexes = [ORDER.index(algorithm) for algorithm in ORDER]

    # --- Assert ---
    assert indexes == list(range(CODEC_COUNT))


def test_algorithm_type_is_frozen_dataclass() -> None:
    """
    Given: an AlgorithmType instance.
    When: its attributes are reassigned.
    Then: a FrozenInstanceError is raised.
    """
    # --- Arrange ---
    codec: AlgorithmType = Codecs.Base64
    replacement: Callable[[bytes], bytes] = bytes

    # --- Act / Assert ---
    with pytest.raises(dataclasses.FrozenInstanceError):
        codec.encode = replacement  # type: ignore[misc]


# --- default algorithm, unknown codecs, header-only decode ---

BASE85_HEADER_INDEX = ORDER.index(Algorithm.Base85)


def test_encode_default_algorithm_uses_base85_header() -> None:
    """
    Given: a payload and no explicit algorithm.
    When: it is encoded.
    Then: the header byte is the Base85 index in Algorithm.Codecs and the
        round trip preserves the payload.
    """
    # --- Arrange ---
    payload = b"\x00payload\xff"

    # --- Act ---
    encoded = encode(payload)

    # --- Assert ---
    assert encoded[0] == BASE85_HEADER_INDEX
    assert decode(encoded) == payload


@pytest.mark.parametrize(
    "name",
    CODEC_IDS,
    ids=CODEC_IDS,
)
def test_encode_accepts_codec_name_strings(name: str) -> None:
    """
    Given: a payload and a codec passed as a plain name string.
    When: it is encoded and decoded back.
    Then: the named codec is used (header index) and the payload survives.
    """
    # --- Arrange ---
    payload = b"\x00name-string\xff"
    expected_index = CODEC_IDS.index(name)

    # --- Act ---
    encoded = encode(payload, name)

    # --- Assert ---
    assert encoded[0] == expected_index
    assert decode(encoded) == payload


def test_encode_rejects_unknown_codec_name() -> None:
    """
    Given: an algorithm name that is not in the codec table.
    When: it is passed to encode.
    Then: a ValueError names the unknown codec.
    """
    # --- Act / Assert ---
    with pytest.raises(ValueError, match="not a valid"):
        encode(b"payload", "base99")  # type: ignore[arg-type]


def test_decode_header_only_blob_returns_empty_bytes() -> None:
    """
    Given: a blob carrying only a codec header byte and no body.
    When: it is decoded.
    Then: an empty byte string is returned — the codec decodes the empty
        body without fault.
    """
    # --- Arrange ---
    blob = bytes([BASE85_HEADER_INDEX])

    # --- Act ---
    result = decode(blob)

    # --- Assert ---
    assert result == b""


def test_decode_str_input_raises_type_error() -> None:
    """
    Given: a str instead of bytes.
    When: it is decoded.
    Then: a TypeError is raised from the tuple index lookup.

    pin: current behavior, flagged — a str header crashes with TypeError
    instead of the documented DeserializeError.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(TypeError):
        decode("str-input")  # type: ignore[arg-type]
