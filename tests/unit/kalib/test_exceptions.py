"""Tests for `zx.lib.exceptions` — Error snapshots of raised exceptions."""

import dataclasses
from collections.abc import Callable

import orjson
import pytest
from faker import Faker
from pytest_mock import MockerFixture

from zx.lib.exceptions import Error, exception, from_error
from zx.lib.serial import dumps

ERROR_FIELDS = ("type", "arguments", "message", "reason", "trace")
VALUE_ERROR_NAME = "ValueError"
DIRECT_CAUSE_MARKER = "The above exception was the direct cause"
BLANK_MESSAGE = "   "

ExceptionFactory = Callable[[Faker], Exception]


def _raise_with_word(fake: Faker) -> Exception:
    """A ValueError carrying one faker word as its argument."""
    return ValueError(fake.word())


def _raise_bare(fake: Faker) -> Exception:
    """A ValueError raised without arguments."""
    return ValueError()


def _raise_with_word_and_message(fake: Faker) -> Exception:
    """A ValueError with an argument plus a non-standard `.message`."""
    error = ValueError(fake.word())
    error.message = fake.sentence()
    return error


def _raise_bare_with_message(fake: Faker) -> Exception:
    """A ValueError without arguments but with a `.message`."""
    error = ValueError()
    error.message = fake.sentence()
    return error


def _raise_with_blank_message(fake: Faker) -> Exception:
    """A ValueError whose `.message` is whitespace-only."""
    error = ValueError(fake.word())
    error.message = BLANK_MESSAGE
    return error


exception_shapes = pytest.mark.parametrize(
    "make_exc",
    (
        _raise_with_word,
        _raise_bare,
        _raise_with_word_and_message,
        _raise_bare_with_message,
        _raise_with_blank_message,
    ),
    ids=(
        "with-args",
        "without-args",
        "with-args-and-message",
        "without-args-and-message",
        "with-args-and-blank-message",
    ),
)


# --- Error shape ---


def test_error_shape_is_frozen_slots_dataclass() -> None:
    """
    Given: an Error produced from a bare ValueError.
    When: the class shape is inspected.
    Then: it is a frozen, slotted dataclass with the declared fields.
    """
    # --- Arrange ---

    # --- Act ---
    error: Error = exception(ValueError())

    # --- Assert ---
    assert dataclasses.is_dataclass(error)
    names = tuple(field.name for field in dataclasses.fields(error))
    assert names == ERROR_FIELDS
    assert not hasattr(error, "__dict__")


def test_error_reassignment_raises_frozen_instance_error(fake: Faker) -> None:
    """
    Given: an existing Error instance.
    When: a field is reassigned.
    Then: a FrozenInstanceError is raised.
    """
    # --- Arrange ---
    error = exception(ValueError(fake.word()))
    replacement = fake.word()

    # --- Act / Assert ---
    with pytest.raises(dataclasses.FrozenInstanceError):
        error.reason = replacement


# --- exception(): reason and arguments ---


@exception_shapes
def test_exception_reason_follows_parametrized_shape(
    make_exc: ExceptionFactory,
    fake: Faker,
) -> None:
    """
    Given: a parametrized exception shape built from faker payloads.
    When: it is captured via exception().
    Then: the reason is Who.Is(e)(args) with a stripped .message suffix
        appended exactly when a non-blank .message attribute is present.
    """
    # --- Arrange ---
    exc = make_exc(fake)

    # --- Act ---
    error = exception(exc)

    # --- Assert ---
    arguments = [orjson.dumps(item).decode() for item in exc.args] or None
    rendered = orjson.dumps(arguments or []).decode()
    expected_reason = f"ValueError({rendered[1:-1]})"
    suffix = getattr(exc, "message", "").strip()
    if suffix:
        expected_reason = f"{expected_reason}: {suffix}"
    assert error.type == VALUE_ERROR_NAME
    assert error.arguments == arguments
    assert error.reason == expected_reason


@exception_shapes
def test_exception_message_field_is_exception_text(
    make_exc: ExceptionFactory,
    fake: Faker,
) -> None:
    """
    Given: a parametrized exception shape.
    When: it is captured via exception().
    Then: the message field holds the exception's own message text.
    """
    # --- Arrange ---
    exc = make_exc(fake)

    # --- Act ---
    error = exception(exc)

    # --- Assert ---
    assert error.message == (str(exc).strip() or None)


def test_exception_message_is_stripped_of_surrounding_whitespace(
    fake: Faker,
) -> None:
    """
    Given: an exception whose str() carries surrounding whitespace.
    When: it is captured via exception().
    Then: the message field is stripped; an empty message becomes None.
    """
    # --- Arrange ---
    payload = fake.sentence()

    # --- Act ---
    padded = exception(ValueError(f"  {payload}  "))
    bare = exception(ValueError())

    # --- Assert ---
    assert padded.message == payload
    assert bare.message is None


def _raise_value_error(payload: str) -> None:
    """Raise a ValueError with the given payload (TRY301 helper)."""
    raise ValueError(payload)


def _raise_chained_value_error(payload: str, cause_payload: str) -> None:
    """Raise a ValueError with an explicit KeyError cause."""
    try:
        _raise_key_error(cause_payload)
    except KeyError as cause:
        raise ValueError(payload) from cause


def _raise_key_error(payload: str) -> None:
    """Raise a KeyError with the given payload (TRY301 helper)."""
    raise KeyError(payload)


# --- exception(): trace ---


def test_exception_trace_lines_are_trimmed_of_trailing_whitespace(
    fake: Faker,
) -> None:
    """
    Given: a caught ValueError with a faker sentence as its argument.
    When: it is captured via exception().
    Then: every trace line is trimmed of trailing whitespace.
    """
    # --- Arrange ---
    payload = fake.sentence()

    # --- Act ---
    try:
        _raise_value_error(payload)
    except ValueError as caught:
        error = exception(caught)

    # --- Assert ---
    assert error.trace is not None
    assert all(line == line.rstrip() for line in error.trace)
    assert error.trace[-1] == f"ValueError: {payload}"


def test_exception_cause_chain_is_included_in_trace(fake: Faker) -> None:
    """
    Given: a ValueError raised with an explicit KeyError cause.
    When: it is captured via exception().
    Then: the trace records both the cause and the direct-cause marker.
    """
    # --- Arrange ---
    cause_payload = fake.word()
    payload = fake.word()

    # --- Act ---
    try:
        _raise_chained_value_error(payload, cause_payload)
    except ValueError as caught:
        error = exception(caught)

    # --- Assert ---
    assert error.type == VALUE_ERROR_NAME
    assert error.trace is not None
    assert any(DIRECT_CAUSE_MARKER in line for line in error.trace)
    assert any(f"KeyError: '{cause_payload}'" in line for line in error.trace)


def test_exception_empty_trace_rounds_to_none(
    mocker: MockerFixture,
    fake: Faker,
) -> None:
    """
    Given: an exception whose formatted trace is empty.
    When: it is captured via exception().
    Then: the trace field is None rather than an empty list.
    """
    # --- Arrange ---
    mocker.patch("zx.lib.exceptions.format_exception", return_value=[])

    # --- Act ---
    error = exception(ValueError(fake.word()))

    # --- Assert ---
    assert error.trace is None


# --- serializer registry round-trip ---


@exception_shapes
def test_dumps_error_round_trips_registered_serializer(
    make_exc: ExceptionFactory,
    fake: Faker,
) -> None:
    """
    Given: an Error captured from a parametrized exception shape.
    When: it is dumped via the serializer registry and loaded back.
    Then: the payload equals the asdict of the Error, and from_error,
        registered at import, agrees with it.
    """
    # --- Arrange ---
    exc = make_exc(fake)
    error = exception(exc)

    # --- Act ---
    payload = orjson.loads(dumps(error))

    # --- Assert ---
    assert payload == dataclasses.asdict(error)
    assert from_error(error) == dataclasses.asdict(error)


# --- appended contract tests: argument rendering edges ---


def test_exception_multiple_args_renders_every_argument() -> None:
    """
    Given: a ValueError carrying two plain string arguments.
    When: it is captured via exception().
    Then: arguments lists both rendered args in order, and message is
        the exception's own str() text.
    """
    # --- Arrange ---

    # --- Act ---
    error = exception(ValueError("a", "b"))

    # --- Assert ---
    assert error.arguments == ['"a"', '"b"']
    assert error.message == "('a', 'b')"


@pytest.mark.parametrize(
    "argument,rendered",
    (
        (42, "42"),
        (None, "null"),
        (b"x", '"x"'),
    ),
    ids=("int-arg", "none-arg", "bytes-arg"),
)
def test_exception_non_str_arg_renders_via_stringify(
    argument: object,
    rendered: str,
) -> None:
    """
    Given: a ValueError carrying a single non-str argument.
    When: it is captured via exception().
    Then: the argument is rendered through stringify with
        on_error="name" — JSON scalars verbatim, unserializable leaves
        degrade to the class name.
    """
    # --- Arrange ---

    # --- Act ---
    error = exception(ValueError(argument))

    # --- Assert ---
    assert error.arguments == [rendered]


def test_exception_nested_exception_arg_renders_type_name() -> None:
    """
    Given: a ValueError whose argument is another exception.
    When: it is captured via exception().
    Then: the unserializable leaf degrades to its class name.
    """
    # --- Arrange ---
    nested = ValueError("inner")

    # --- Act ---
    error = exception(ValueError(nested))

    # --- Assert ---
    assert error.arguments == ['"ValueError"']


def test_exception_whitespace_only_arg_message_none_args_kept() -> None:
    """
    Given: a ValueError carrying a whitespace-only string.
    When: it is captured via exception().
    Then: message is None after strip, but arguments keep the payload.
    """
    # --- Arrange ---

    # --- Act ---
    error = exception(ValueError("  "))

    # --- Assert ---
    assert error.message is None
    assert error.arguments == ['"  "']


def test_exception_non_str_message_attribute_raises_attr_error(
    fake: Faker,
) -> None:
    """
    Given: an exception whose `.message` attribute is a non-str (42).
    When: it is captured via exception().
    Then: `.strip()` on the int raises AttributeError — the reason
        suffix arm does not guard attribute types.
        # expected: verify
    """
    # --- Arrange ---
    caught = ValueError(fake.word())
    caught.message = 42

    # --- Act / Assert ---
    with pytest.raises(AttributeError):
        exception(caught)


# --- appended contract tests: round trip & trace trim ---


def test_error_round_trip_with_unicode_arguments(fake: Faker) -> None:
    """
    Given: an Error captured from a unicode-heavy argument.
    When: it is dumped via the serializer registry and loaded back.
    Then: the payload equals the asdict of the Error and the unicode
        text survives the round trip intact.
    """
    # --- Arrange ---
    payload = f"héllo wörld — {fake.word()} ✓"
    error = exception(ValueError(payload))

    # --- Act ---
    loaded = orjson.loads(dumps(error))

    # --- Assert ---
    assert loaded == dataclasses.asdict(error)
    assert loaded["message"] == payload
    assert loaded["arguments"] == [orjson.dumps(payload).decode()]


def test_exception_trace_trims_padded_format_lines(
    mocker: MockerFixture,
    fake: Faker,
) -> None:
    """
    Given: a format_exception patched to return padded lines (trailing
        spaces, a bare blank line, a trailing tab).
    When: the exception is captured.
    Then: every trace line is rstripped — the blank line survives as
        an empty string, the tab and spaces are gone.
    """
    # --- Arrange ---
    padded = [
        f"  File x, line 1, in {fake.word()}   ",
        "",
        f"ValueError: {fake.word()}\t",
    ]
    mocker.patch(
        "zx.lib.exceptions.format_exception",
        return_value=padded,
    )

    # --- Act ---
    error = exception(ValueError(fake.word()))

    # --- Assert ---
    assert error.trace is not None
    assert error.trace == [line.rstrip() for line in padded]
    assert all(line == line.rstrip() for line in error.trace)
