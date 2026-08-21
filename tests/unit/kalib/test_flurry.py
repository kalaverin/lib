"""Tests for `zx.lib.flurry` — seed-derived 62-bit time-ordered ids."""

import re
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

import pytest
import time_machine
from base58 import b58encode_int
from faker import Faker

from zx.lib.flurry import MACHINE_ID, Flurry, flurry_seed

FLURRY_SEED_ENV_VAR = "FLURRY_SEED"
SHA256_DIGEST_LENGTH = 32
ENV_SEED_VALUE = "seed-from-environment"
HOSTNAME_SENTINEL = "host-from-socket"
INVALID_BASE58_TEXT = "0OIl"

TOTAL_BITS = Flurry.BitsStamp + Flurry.BitsPod + Flurry.BitsRandom
FAR_FUTURE = datetime(year=2100, month=1, day=1, tzinfo=UTC)
FIXED_PRESENT = datetime(year=2026, month=6, day=15, tzinfo=UTC)

BYTE_LENGTH_FAULTS = (0, 7, 9)
BYTE_LENGTH_FAULT_IDS = ("empty", "short", "long")

PARSE_TEXT_FAULTS: tuple[tuple[str, str], ...] = (
    ("", "empty Flurry id"),
    ("   ", "empty Flurry id"),
    (INVALID_BASE58_TEXT, "invalid Flurry id"),
)
PARSE_TEXT_FAULT_IDS = ("empty", "whitespace-only", "illegal-alphabet")

TYPE_ERROR_MATCH = "expected str, int, or bytes"

REJECTION_OPERATIONS: tuple[
    tuple[Callable[[], Flurry], type[Exception], str],
    ...,
] = (
    (lambda: Flurry(-1), ValueError, "Flurry value out of range"),
    (
        lambda: Flurry(Flurry.MaxId + 1),
        ValueError,
        "Flurry value out of range",
    ),
)
REJECTION_OPERATION_IDS = ("negative", "beyond-max-id")

PARSE_TYPE_FAULTS: tuple[object, ...] = (True, False, None, 1.5)
PARSE_TYPE_FAULT_IDS = ("bool-true", "bool-false", "none", "float")


# --- seed derivation ---


def test_flurry_seed_env_var_takes_precedence_over_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: FLURRY_SEED is set and socket.gethostname returns another value.
    When: the seed is derived.
    Then: the sha256 digest of the env value is returned, not the hostname.
    """
    # --- Arrange ---
    monkeypatch.setenv(FLURRY_SEED_ENV_VAR, ENV_SEED_VALUE)
    monkeypatch.setattr(socket, "gethostname", lambda: HOSTNAME_SENTINEL)

    # --- Act ---
    seed = flurry_seed()

    # --- Assert ---
    assert seed == sha256(ENV_SEED_VALUE.encode()).digest()
    assert len(seed) == SHA256_DIGEST_LENGTH


def test_flurry_seed_without_env_falls_back_to_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: FLURRY_SEED is unset and socket.gethostname returns a sentinel.
    When: the seed is derived.
    Then: the sha256 digest of the hostname is returned.
    """
    # --- Arrange ---
    monkeypatch.delenv(FLURRY_SEED_ENV_VAR, raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: HOSTNAME_SENTINEL)

    # --- Act ---
    seed = flurry_seed()

    # --- Assert ---
    assert seed == sha256(HOSTNAME_SENTINEL.encode()).digest()


def test_flurry_seed_empty_env_var_falls_back_to_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: FLURRY_SEED is set to an empty (falsy) string.
    When: the seed is derived.
    Then: the hostname fallback kicks in — the empty string is not hashed.
    """
    # --- Arrange ---
    monkeypatch.setenv(FLURRY_SEED_ENV_VAR, "")
    monkeypatch.setattr(socket, "gethostname", lambda: HOSTNAME_SENTINEL)

    # --- Act ---
    seed = flurry_seed()

    # --- Assert ---
    assert seed == sha256(HOSTNAME_SENTINEL.encode()).digest()


def test_machine_id_is_sha256_digest() -> None:
    """
    Given: the module-level MACHINE_ID computed at import time.
    When: its shape is inspected.
    Then: it is a raw bytes digest of sha256 length.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert isinstance(MACHINE_ID, bytes)
    assert len(MACHINE_ID) == SHA256_DIGEST_LENGTH


def test_flurry_id_uses_first_machine_id_byte() -> None:
    """
    Given: MACHINE_ID and the Flurry.Id class constant.
    When: they are compared.
    Then: Id is exactly the first machine-id byte masked to 8 bits.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert Flurry.Id == MACHINE_ID[0] & 0xFF


# --- int round-trip ---


def test_flurry_int_str_round_trip(fake: Faker) -> None:
    """
    Given: a faker-driven int within the Flurry budget.
    When: it goes int -> str (base58) -> parse -> int.
    Then: every hop preserves the value.
    """
    # --- Arrange ---
    value = fake.random_int(min=0, max=Flurry.MaxId)

    # --- Act ---
    flurry = Flurry.from_int(value)
    text = flurry.to_str()

    # --- Assert ---
    assert text
    assert str(flurry) == text
    assert Flurry.from_str(text).to_int() == value
    assert Flurry.parse(text).to_int() == value


def test_flurry_int_bytes_round_trip(fake: Faker) -> None:
    """
    Given: a faker-driven int within the Flurry budget.
    When: it goes int -> bytes (8 bytes big-endian) -> from_bytes -> int.
    Then: every hop preserves the value and the wire length.
    """
    # --- Arrange ---
    value = fake.random_int(min=0, max=Flurry.MaxId)

    # --- Act ---
    flurry = Flurry.from_int(value)
    raw = flurry.to_bytes()

    # --- Assert ---
    assert len(raw) == Flurry.BytesLength
    assert int.from_bytes(raw, byteorder="big") == value
    assert Flurry.from_bytes(raw).to_int() == value
    assert Flurry.parse(raw).to_int() == value


# --- structural pins ---


def test_flurry_default_init_value_fits_bit_budget() -> None:
    """
    Given: time frozen at a fixed post-epoch instant.
    When: a default Flurry id is generated.
    Then: its value is non-negative and fits the 62-bit total budget.
    """
    # --- Arrange — fixed travel: faker destinations may be pre-EPOCH
    # (negative stamps are the known bugs/zx.lib/011 anomaly).
    with time_machine.travel(FIXED_PRESENT, tick=False):
        flurry = Flurry()

        # --- Act ---
        value = flurry.to_int()

        # --- Assert ---
        assert value >= 0
        assert value.bit_length() <= TOTAL_BITS
        assert len(flurry.to_bytes()) == Flurry.BytesLength


def test_flurry_successive_instances_under_frozen_time_differ(
    frozen_time: time_machine.travel,
) -> None:
    """
    Given: time frozen so successive ids share stamp and machine id.
    When: two default Flurry ids are generated one after another.
    Then: they differ — the 13-bit randbits component separates them.
    """
    # --- Arrange ---

    # --- Act ---
    first = Flurry()
    second = Flurry()

    # --- Assert ---
    assert first.to_int() != second.to_int()


def test_flurry_init_past_stamp_budget_raises_overflow_error() -> None:
    """
    Given: time moved past the 41-bit stamp budget (year 2100).
    When: a default Flurry id is materialized.
    Then: an OverflowError is raised by the stamp property.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with (
        time_machine.travel(FAR_FUTURE, tick=False),
        pytest.raises(OverflowError),
    ):
        Flurry().to_int()


# --- rejection matrix ---


@pytest.mark.parametrize(
    "length",
    BYTE_LENGTH_FAULTS,
    ids=BYTE_LENGTH_FAULT_IDS,
)
def test_flurry_from_bytes_wrong_length_raises_value_error(
    fake: Faker,
    length: int,
) -> None:
    """
    Given: a byte string whose length is not the 8-byte wire length.
    When: it is parsed via from_bytes.
    Then: a ValueError naming both lengths is raised.
    """
    # --- Arrange ---
    raw = fake.binary(length=length)

    # --- Act / Assert ---
    with pytest.raises(
        ValueError,
        match=f"expected {Flurry.BytesLength} bytes, got {length}",
    ):
        Flurry.from_bytes(raw)


@pytest.mark.parametrize(
    "text,match",
    PARSE_TEXT_FAULTS,
    ids=PARSE_TEXT_FAULT_IDS,
)
def test_flurry_from_str_rejects_invalid_text(text: str, match: str) -> None:
    """
    Given: a base58 text that is empty, whitespace-only, or off-alphabet.
    When: it is parsed via from_str.
    Then: a ValueError with the corresponding message is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ValueError, match=match):
        Flurry.from_str(text)


@pytest.mark.parametrize(
    "operation,fault,match",
    REJECTION_OPERATIONS,
    ids=REJECTION_OPERATION_IDS,
)
def test_flurry_rejection_matrix_raises_expected_fault(
    operation: Callable[[], Flurry],
    fault: type[Exception],
    match: str,
) -> None:
    """
    Given: a rejected construction or parse input from the fault table.
    When: the operation runs.
    Then: the expected exception with the expected message is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(fault, match=match):
        operation()


@pytest.mark.parametrize("value", PARSE_TYPE_FAULTS, ids=PARSE_TYPE_FAULT_IDS)
def test_flurry_parse_foreign_type_raises_type_error(value: object) -> None:
    """
    Given: a non str/int/bytes parse input (bool, None, float).
    When: it is parsed.
    Then: a TypeError explaining the accepted types is raised.
    """
    # --- Arrange — value parametrized.

    # --- Act / Assert ---
    with pytest.raises(TypeError, match=TYPE_ERROR_MATCH):
        Flurry.parse(value)


# --- edge cases: boundary round trips, bit layout, whitespace, repr ---

PRE_EPOCH = datetime(year=2020, month=1, day=1, tzinfo=UTC)

POD_MASK = (1 << Flurry.BitsPod) - 1
RANDOM_MASK = (1 << Flurry.BitsRandom) - 1
BASE58_ALPHABET_PATTERN = r"[1-9A-HJ-NP-Za-km-z]+"


def test_flurry_from_str_decoded_beyond_max_id_raises_value_error() -> None:
    """
    Given: a base58 text decoding to an integer above Flurry.MaxId.
    When: it is parsed via from_str.
    Then: a ValueError reporting the value out of range is raised.
    """

    # --- Arrange ---
    text = b58encode_int(Flurry.MaxId + 1).decode()

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="out of range"):
        Flurry.from_str(text)


@pytest.mark.parametrize(
    "value",
    (0, Flurry.MaxId),
    ids=("zero", "max-id"),
)
def test_flurry_from_int_boundaries_round_trip(value: int) -> None:
    """
    Given: a parametrized boundary value (0 or MaxId).
    When: it goes int -> bytes -> parse and int -> str -> from_str.
    Then: every hop preserves the exact value.
    """

    # --- Arrange ---
    flurry = Flurry.from_int(value)

    # --- Act / Assert ---
    assert flurry.to_int() == value
    assert Flurry.parse(flurry.to_bytes()).to_int() == value
    assert Flurry.from_str(flurry.to_str()).to_int() == value


def test_flurry_parse_instance_returns_identity() -> None:
    """
    Given: an existing Flurry instance.
    When: it is passed to Flurry.parse.
    Then: the very same object is returned unchanged.
    """

    # --- Arrange ---
    instance = Flurry.from_int(42)

    # --- Act ---
    result = Flurry.parse(instance)

    # --- Assert ---
    assert result is instance


def test_flurry_repr_uses_arrow_format() -> None:
    """
    Given: a Flurry built from a known int.
    When: its repr is rendered.
    Then: it matches the `<address -> base58>` pattern.

    pin: current behavior — the repr embeds the base58 form after an arrow.
    """

    # --- Arrange ---
    flurry = Flurry.from_int(42)

    # --- Act / Assert ---
    assert re.fullmatch(
        rf"<.+ -> {BASE58_ALPHABET_PATTERN}>",
        repr(flurry),
    )


def test_flurry_value_decomposes_into_stamp_pod_random_bits() -> None:
    """
    Given: time frozen at a fixed post-epoch instant.
    When: a default Flurry id is generated and decomposed.
    Then: the high 41 bits are the ms stamp since the Flurry epoch, the
        middle 8 bits are the machine id, the low 13 bits are random.
    """

    # --- Arrange ---
    with time_machine.travel(FIXED_PRESENT, tick=False):
        flurry = Flurry()
        stamp = int(FIXED_PRESENT.timestamp() * 1e3) - Flurry.Epoch

        # --- Act ---
        value = flurry.to_int()

        # --- Assert ---
        assert value >> (Flurry.BitsPod + Flurry.BitsRandom) == stamp
        assert (value >> Flurry.BitsRandom) & POD_MASK == Flurry.Id
        recomposed = (
            (stamp << (Flurry.BitsPod + Flurry.BitsRandom))
            | (Flurry.Id << Flurry.BitsRandom)
            | (value & RANDOM_MASK)
        )
        assert recomposed == value


def test_flurry_pre_epoch_stamp_produces_negative_value() -> None:
    """
    Given: time moved before the Flurry epoch (year 2020).
    When: a default Flurry id is generated.
    Then: the value is negative — the bit packing wraps around zero.

    pin: known anomaly — pre-epoch instants yield negative stamps/values
    (bugs/zx.lib/011).
    """

    # --- Arrange ---

    # --- Act / Assert ---
    with time_machine.travel(PRE_EPOCH, tick=False):
        assert Flurry().to_int() < 0


def test_flurry_from_str_with_surrounding_whitespace_round_trips(
    fake: Faker,
) -> None:
    """
    Given: a valid base58 text padded with surrounding whitespace.
    When: it is parsed via from_str.
    Then: the whitespace is trimmed and the value round-trips.
    """

    # --- Arrange ---
    value = fake.random_int(min=0, max=Flurry.MaxId)
    text = Flurry.from_int(value).to_str()

    # --- Act ---
    result = Flurry.from_str(f"  {text}\n")

    # --- Assert ---
    assert result.to_int() == value
