"""Tests for `zx.lib.serial.container` — marshalled compressed payloads."""

import logging
import pickle as pc

import lz4.block
import orjson
import pytest
import zstd
from faker import Faker

from zx.lib.serial.container import (
    DEADBEEF,
    Compressor,
    Marshall,
    pack,
    unpack,
)

TRUNCATED_BYTES = 5

JSON_SAFE_PAYLOADS: tuple[object, ...] = (
    {},
    [],
    None,
    0,
    "Unicode ✓ текст テスト",
    ["mixed", 1, None, {"nested": True}],
)
JSON_SAFE_IDS = (
    "empty-dict",
    "empty-list",
    "none",
    "zero",
    "unicode-text",
    "nested-mixed",
)

PICKLE_ONLY_PAYLOADS: tuple[bytes, ...] = (
    b"prefix" + DEADBEEF + b"middle" + DEADBEEF + b"suffix",
    bytes(range(256)) * 16,
)
PICKLE_ONLY_IDS = ("embedded-deadbeef", "all-byte-values-x16")

UNPACK_FAULTS: tuple[tuple[bytes, str], ...] = (
    (b"", "missing DEADBEEF marker"),
    (b"\x00" * 16, "missing DEADBEEF marker"),
    (b"x" * 40 + DEADBEEF + b"payload", "missing DEADBEEF marker"),
    (b"gzip:json" + DEADBEEF + b"payload", "gzip"),
    (b"zstd:yaml" + DEADBEEF + b"payload", "yaml"),
    (b"zstdjson" + DEADBEEF + b"payload", "not enough values"),
    (DEADBEEF + b"payload", "not enough values"),
    (b"zstd:json:extra" + DEADBEEF + b"payload", "json:extra"),
)
UNPACK_FAULT_IDS = (
    "empty-input",
    "random-garbage",
    "marker-beyond-32-byte-window",
    "unknown-compressor",
    "unknown-marshaller",
    "header-without-separator",
    "empty-header",
    "extra-separator",
)

encoders = pytest.mark.parametrize("encoder", Marshall, ids=str)
compressors = pytest.mark.parametrize("compressor", Compressor, ids=str)


# --- round-trip ---


@encoders
@compressors
@pytest.mark.parametrize("payload", JSON_SAFE_PAYLOADS, ids=JSON_SAFE_IDS)
def test_pack_unpack_round_trip_json_safe_payloads(
    payload: object,
    encoder: Marshall,
    compressor: Compressor,
) -> None:
    """
    Given: a parametrized JSON-safe payload, marshaller and compressor.
    When: the payload is packed and unpacked.
    Then: an equal payload is returned.
    """
    # --- Arrange — all inputs parametrized.

    # --- Act ---
    packed = pack(payload, encoder=encoder, compressor=compressor)

    # --- Assert ---
    assert unpack(packed) == payload


@encoders
@compressors
def test_pack_unpack_round_trip_faker_payload(
    fake: Faker,
    encoder: Marshall,
    compressor: Compressor,
) -> None:
    """
    Given: a faker-driven nested mapping payload.
    When: it is packed and unpacked.
    Then: an equal payload is returned.
    """
    # --- Arrange ---
    payload = {
        "name": fake.first_name(),
        "number": fake.pyint(),
        "tags": fake.words(),
    }

    # --- Act ---
    packed = pack(payload, encoder=encoder, compressor=compressor)

    # --- Assert ---
    assert unpack(packed) == payload


@compressors
@pytest.mark.parametrize("payload", PICKLE_ONLY_PAYLOADS, ids=PICKLE_ONLY_IDS)
def test_pack_unpack_round_trip_pickle_only_payloads(
    payload: bytes,
    compressor: Compressor,
) -> None:
    """
    Given: a bytes payload (incl. embedded DEADBEEF markers).
    When: it is packed via Pickle and unpacked.
    Then: the original bytes are returned — the header parse is positional.
    """
    # --- Arrange — payload parametrized.

    # --- Act ---
    packed = pack(payload, encoder=Marshall.Pickle, compressor=compressor)

    # --- Assert ---
    assert unpack(packed) == payload


# --- wire format ---


@encoders
@compressors
def test_pack_header_is_plain_codec_prefix(
    fake: Faker,
    encoder: Marshall,
    compressor: Compressor,
) -> None:
    """
    Given: a faker-driven payload.
    When: it is packed with parametrized encoder and compressor.
    Then: the packed bytes start with the plain codec header prefix.
    """
    # --- Arrange ---
    payload = fake.word()

    # --- Act ---
    packed = pack(payload, encoder=encoder, compressor=compressor)

    # --- Assert ---
    header = f"{compressor.value}:{encoder.value}".encode()
    assert packed.startswith(header + DEADBEEF)


# --- pack faults ---


def test_pack_keyword_argument_raises_type_error(fake: Faker) -> None:
    """
    Given: a faker-driven payload; the stock zstd binding is positional-only.
    When: a keyword argument is forwarded to the compressor.
    Then: a TypeError is raised — `kw` is inert with stock bindings.
    """
    # --- Arrange ---
    payload = fake.word()

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="takes no keyword arguments"):
        pack(payload, level=1)


def test_pack_set_payload_with_json_encoder_raises_type_error() -> None:
    """
    Given: a set payload, which has no JSON representation.
    When: it is packed with the JSON marshaller.
    Then: a TypeError from orjson is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="not JSON serializable"):
        pack({1, 2, 3}, encoder=Marshall.JSON)


# --- unpack faults ---


@pytest.mark.parametrize("blob,reason", UNPACK_FAULTS, ids=UNPACK_FAULT_IDS)
def test_unpack_malformed_container_raises_value_error(
    blob: bytes,
    reason: str,
) -> None:
    """
    Given: a parametrized malformed container blob.
    When: it is unpacked.
    Then: a ValueError matching the parametrized reason is raised.
    """
    # --- Arrange — blob parametrized.

    # --- Act / Assert ---
    with pytest.raises(ValueError, match=reason):
        unpack(blob)


@pytest.mark.parametrize(
    "compressor,fault",
    (
        (Compressor.ZSTD, zstd.Error),
        (Compressor.LZ4, lz4.block.LZ4BlockError),
    ),
    ids=("zstd", "lz4"),
)
def test_unpack_truncated_payload_raises_compressor_error(
    fake: Faker,
    compressor: Compressor,
    fault: type[Exception],
) -> None:
    """
    Given: a packed payload with its compressed tail truncated.
    When: it is unpacked.
    Then: the compressor-specific error propagates (logged, not swallowed).
    """
    # --- Arrange ---
    packed = pack(fake.text(), compressor=compressor)
    truncated = packed[:-TRUNCATED_BYTES]

    # --- Act / Assert ---
    with pytest.raises(fault):
        unpack(truncated)


# --- edge / contract additions ---


def test_unpack_corrupt_pickle_body_raises_unpickling_error() -> None:
    """
    Given: a container whose marshalled body is a truncated pickle.
    When: it is unpacked.
    Then: UnpicklingError propagates — decode failures are not swallowed.
    """
    # --- Arrange ---
    body = pc.dumps({"a": 1})[:-2]
    blob = b"zstd:pickle" + DEADBEEF + zstd.compress(body)

    # --- Act / Assert ---
    with pytest.raises(pc.UnpicklingError):
        unpack(blob)


def test_unpack_corrupt_json_body_raises_json_decode_error() -> None:
    """
    Given: a container whose marshalled body is truncated JSON.
    When: it is unpacked.
    Then: orjson.JSONDecodeError propagates.
    """
    # --- Arrange ---
    blob = b"zstd:json" + DEADBEEF + zstd.compress(b'{"a": 1')

    # --- Act / Assert ---
    with pytest.raises(orjson.JSONDecodeError):
        unpack(blob)


def test_pack_literal_encoder_and_compressor_names_round_trip() -> None:
    """
    Given: a payload packed with literal "pickle" / "lz4" names.
    When: it is unpacked.
    Then: an equal payload is returned.
    """
    # --- Arrange ---

    # --- Act ---
    packed = pack({"a": 1}, encoder="pickle", compressor="lz4")

    # --- Assert ---
    assert unpack(packed) == {"a": 1}


def test_pack_unknown_encoder_raises_value_error() -> None:
    """
    Given: an encoder name outside the Marshall enum.
    When: pack runs.
    Then: ValueError "is not a valid Marshall" is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="is not a valid Marshall"):
        pack({}, encoder="yaml")  # type: ignore[arg-type]


def test_pack_bytes_payload_with_json_round_trips_as_text() -> None:
    """
    Given: a top-level bytes payload packed with the JSON marshaller.
    When: it is unpacked.
    Then: the decoded text comes back — bytes leave as str.
    """
    # --- Arrange — pin: current behavior — asymmetric bytes -> str
    # --- conversion via the encode_object hook.

    # --- Act / Assert ---
    assert unpack(pack(b"bytes-payload")) == "bytes-payload"


def test_pack_non_str_keys_json_round_trips_with_string_keys() -> None:
    """
    Given: a dict with an integer key packed via JSON.
    When: it is unpacked.
    Then: the key comes back coerced to its string form.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    assert unpack(pack({1: "a"})) == {"1": "a"}


def test_unpack_case_variant_header_raises_value_error() -> None:
    """
    Given: a container with an upper-cased compressor name in the header.
    When: it is unpacked.
    Then: ValueError "is not a valid Compressor" — enum lookup is exact.
    """
    # --- Arrange ---
    blob = b"ZSTD:json" + DEADBEEF + zstd.compress(b"{}")

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="is not a valid Compressor"):
        unpack(blob)


def test_pack_unpack_round_trip_exception_instance() -> None:
    """
    Given: an exception instance packed via Pickle.
    When: it is unpacked.
    Then: an equal exception is returned — pinned via type, args and str.
    """
    # --- Arrange — pin: exceptions do not implement __eq__; identity of
    # --- the payload is asserted through args and rendered message.

    # --- Act ---
    packed = pack(ValueError("boom"), encoder=Marshall.Pickle)
    result = unpack(packed)

    # --- Assert ---
    assert isinstance(result, ValueError)
    assert result.args == ("boom",)
    assert str(result) == "boom"


def test_unpack_corrupt_body_logs_failed_to_decode_at_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: a container whose marshalled body is truncated JSON.
    When: it is unpacked.
    Then: "failed to decode object" is logged at ERROR before the raise.
    """
    # --- Arrange ---
    blob = b"zstd:json" + DEADBEEF + zstd.compress(b'{"a": 1')

    # --- Act / Assert ---
    with (
        caplog.at_level(logging.ERROR, logger="zx.lib.serial.container"),
        pytest.raises(orjson.JSONDecodeError),
    ):
        unpack(blob)
    assert "failed to decode object" in caplog.text
