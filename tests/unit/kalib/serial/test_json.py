"""Tests for `zx.lib.serial.json` — orjson contour, hooks and fallbacks."""

import dataclasses
import logging
from collections import deque
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from types import MappingProxyType
from uuid import UUID

import orjson
import pytest

from zx.core import Who
from zx.core.classes import Nothing
from zx.lib.serial import dumps as package_dumps
from zx.lib.serial.errors import SerializationError
from zx.lib.serial.json import (
    dumps,
    encode_object,
    jsonize,
    repr_or_die,
    stringify,
    to_json,
)
from zx.lib.serial.registry import serializer

RegistrySnapshot = Iterator[None]

DUMPS_CASES: tuple[tuple[bool, dict, bytes], ...] = (
    (True, {"b": 1, "a": 2}, b'{"a":2,"b":1}'),
    (True, {1: "a"}, b'{"1":"a"}'),
    (True, {"k": "✓"}, '{"k":"✓"}'.encode()),
    (False, {"b": 1, "a": 2}, b'{\n  "a": 2,\n  "b": 1\n}'),
    (False, {1: "a"}, b'{\n  "1": "a"\n}'),
)
DUMPS_IDS = (
    "minified-sorted",
    "minified-non-str-keys",
    "minified-unicode-preserved",
    "pretty-sorted",
    "pretty-non-str-keys",
)

CONTAINER_CASES: tuple[tuple[object, bytes], ...] = (
    ([1, 2], b"[1,2]"),
    ((1, 2), b"[1,2]"),
    (deque([1, 2]), b"[1,2]"),
)
CONTAINER_IDS = ("list", "tuple", "deque")


# --- dumps options ---


@pytest.mark.parametrize("minify,payload,expected", DUMPS_CASES, ids=DUMPS_IDS)
def test_dumps_option_matrix(
    *,
    minify: bool,
    payload: dict,
    expected: bytes,
) -> None:
    """
    Given: a parametrized payload and minify flag.
    When: it is dumped with default options.
    Then: the exact orjson rendering matches the pinned bytes.

    Pins: OPT_SORT_KEYS and OPT_NON_STR_KEYS survive in both modes;
    unicode is emitted raw; pretty mode uses a two-space indent.
    """
    # --- Arrange — payload parametrized.

    # --- Act ---
    result = dumps(payload, minify=minify)

    # --- Assert ---
    assert result == expected


def test_dumps_with_explicit_option_replaces_default_options() -> None:
    """
    Given: a payload with a non-string key.
    When: it is dumped with an explicit option mask.
    Then: the defaults are replaced wholesale — OPT_NON_STR_KEYS is gone.
    """
    # --- Arrange — option=OPT_SORT_KEYS drops OPT_NON_STR_KEYS.

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="Dict key must be str"):
        dumps({1: "a"}, option=orjson.OPT_SORT_KEYS)


# --- facades ---


def test_package_facades_reexport_same_objects() -> None:
    """
    Given: the zx.lib and zx.lib.serial facades.
    When: re-exported names are inspected.
    Then: they are the identical objects from zx.lib.serial.json.
    """
    # --- Arrange ---
    from zx.lib import dumps as root_dumps  # noqa: PLC0415

    # --- Act / Assert ---
    assert root_dumps is dumps
    assert package_dumps is dumps


# --- encode_object dispatch ---


def test_encode_object_nothing_returns_none() -> None:
    """
    Given: the Nothing sentinel.
    When: it passes through encode_object.
    Then: None is returned (JSON null).
    """
    # --- Arrange ---

    # --- Act / Assert ---
    assert encode_object(Nothing) is None


def test_encode_object_bytes_returns_decoded_text() -> None:
    """
    Given: a UTF-8 byte string.
    When: it passes through encode_object.
    Then: the decoded text is returned.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    assert encode_object("текст ✓".encode()) == "текст ✓"


def test_encode_object_str_passthrough() -> None:
    """
    Given: a plain string.
    When: it passes through encode_object.
    Then: the same string is returned.
    """
    # --- Arrange ---
    value = "plain"

    # --- Act / Assert ---
    assert encode_object(value) == value


def test_encode_object_datetime_returns_z_suffixed_iso() -> None:
    """
    Given: an aware UTC datetime.
    When: it passes through encode_object.
    Then: the dt-rendered ISO form with a Z suffix is returned.
    """
    # --- Arrange ---
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    # --- Act / Assert ---
    assert encode_object(moment) == "2026-01-02T03:04:05Z"


@pytest.mark.parametrize(
    "moment,expected",
    (
        (datetime(2026, 1, 2, 3, 4, 5), "2026-01-02T03:04:05"),  # noqa: DTZ001
        (
            datetime(2026, 1, 2, 3, 4, 5, 123456),  # noqa: DTZ001
            "2026-01-02T03:04:05.123456",
        ),
    ),
    ids=("second-precision", "microsecond-precision"),
)
def test_encode_object_naive_datetime_returns_verbatim_isoformat(
    moment: datetime,
    expected: str,
) -> None:
    """
    Given: a naive datetime without timezone information.
    When: it passes through encode_object.
    Then: its verbatim isoformat is returned — no timezone is invented.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    assert encode_object(moment) == expected


def test_encode_object_date_returns_isoformat() -> None:
    """
    Given: a date.
    When: it passes through encode_object.
    Then: its isoformat string is returned.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    assert encode_object(date(2026, 1, 2)) == "2026-01-02"


def test_encode_object_exact_class_registry_hit(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a throwaway class with a registered serializer.
    When: an instance passes through encode_object.
    Then: the registered serializer result is returned.
    """

    # --- Arrange ---
    class Subject: ...

    serializer(Subject, lambda _: {"via": "exact"})

    # --- Act / Assert ---
    assert encode_object(Subject()) == {"via": "exact"}


def test_encode_object_isinstance_registry_hit(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a serializer registered for a base class only.
    When: a subclass instance passes through encode_object.
    Then: the isinstance fallback loop finds the base serializer.
    """

    # --- Arrange ---
    class Base: ...

    class Derived(Base): ...

    serializer(Base, lambda _: {"via": "isinstance"})

    # --- Act / Assert ---
    assert encode_object(Derived()) == {"via": "isinstance"}


def test_encode_object_registry_hit_returning_nothing_falls_through(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a registered serializer that returns the Nothing sentinel.
    When: an instance passes through encode_object with on_error="name".
    Then: the hit is discarded and the error behavior is applied.
    """

    # --- Arrange ---
    class Subject: ...

    serializer(Subject, lambda _: Nothing)

    # --- Act / Assert ---
    assert encode_object(Subject(), on_error="name") == Who.Is(Subject())


def test_encode_object_unregistered_instance_raises_type_error() -> None:
    """
    Given: an instance of an unregistered class.
    When: it passes through encode_object with on_error="raise".
    Then: a TypeError "couldn't serialize" is raised.
    """

    # --- Arrange ---
    class Subject: ...

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="couldn't serialize"):
        encode_object(Subject())


def test_encode_object_unregistered_class_raises_type_error() -> None:
    """
    Given: an unregistered class object itself.
    When: it passes through encode_object with on_error="raise".
    Then: a TypeError "cannot serialize class" is raised.
    """

    # --- Arrange ---
    class Subject: ...

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="cannot serialize class"):
        encode_object(Subject)


def test_encode_object_non_raise_delegates_to_repr_or_die() -> None:
    """
    Given: an unregistered instance.
    When: encode_object runs with on_error="repr".
    Then: the repr_or_die delegation result (repr) is returned.
    """

    # --- Arrange ---
    class Subject:
        def __repr__(self) -> str:
            return "<Subject pinned>"

    # --- Act / Assert ---
    assert encode_object(Subject(), on_error="repr") == "<Subject pinned>"


# --- to_json / jsonize containers ---


def test_to_json_dataclass_returns_sorted_field_object() -> None:
    """
    Given: a frozen dataclass instance with two fields.
    When: it is converted via to_json.
    Then: a sorted JSON object of its fields is returned.
    """

    # --- Arrange ---
    @dataclasses.dataclass(frozen=True)
    class Record:
        b: int
        a: str

    # --- Act / Assert ---
    assert to_json(Record(b=1, a="x")) == b'{"a":"x","b":1}'


def test_to_json_nested_dataclass_recurses() -> None:
    """
    Given: a dataclass nesting another dataclass.
    When: it is converted via to_json.
    Then: the inner dataclass is jsonized recursively.
    """

    # --- Arrange ---
    @dataclasses.dataclass(frozen=True)
    class Inner:
        v: int

    @dataclasses.dataclass(frozen=True)
    class Outer:
        inner: Inner

    # --- Act / Assert ---
    assert to_json(Outer(inner=Inner(v=1))) == b'{"inner":{"v":1}}'


@pytest.mark.parametrize(
    "payload,expected",
    CONTAINER_CASES,
    ids=CONTAINER_IDS,
)
def test_to_json_sequence_containers_return_arrays(
    payload: object,
    expected: bytes,
) -> None:
    """
    Given: a list, tuple or deque payload.
    When: it is converted via to_json.
    Then: a JSON array with the same elements is returned.
    """
    # --- Arrange — payload parametrized.

    # --- Act / Assert ---
    assert to_json(payload) == expected


def test_to_json_set_returns_array_of_elements() -> None:
    """
    Given: a set payload.
    When: it is converted via jsonize.
    Then: all elements are present — order is not part of the contract.
    """
    # --- Arrange ---

    # --- Act ---
    result = jsonize({2, 1})

    # --- Assert ---
    assert sorted(result) == [1, 2]


@pytest.mark.parametrize(
    "payload,fault,reason",
    (
        (MappingProxyType({"a": 1}), SerializationError, "collection is not"),
        (frozenset({1, 2}), TypeError, "not JSON serializable"),
    ),
    ids=("mapping-proxy", "frozenset"),
)
def test_to_json_unsupported_collection_raises_serialization_error(
    payload: object,
    fault: type[Exception],
    reason: str,
) -> None:
    """
    Given: a collection outside the dataclass/dict/deque/list/set/tuple set.
    When: it is converted via to_json.
    Then: it is rejected — by the guard or by orjson itself.
    """
    # --- Arrange — payload parametrized.

    # --- Act / Assert ---
    with pytest.raises(fault, match=reason):
        to_json(payload)


def test_jsonize_equals_loads_of_to_json() -> None:
    """
    Given: a nested mixed payload.
    When: it passes through jsonize.
    Then: the result equals orjson.loads of to_json.
    """
    # --- Arrange ---
    payload = {"items": [1, "x", None], "day": date(2026, 1, 2)}

    # --- Act / Assert ---
    assert jsonize(payload) == orjson.loads(to_json(payload))


# --- repr_or_die ---


@pytest.mark.parametrize(
    "on_error,expected",
    (
        ("cast", Who.Cast),
        ("name", Who.Is),
        ("print", str),
        ("repr", repr),
    ),
    ids=("cast", "name", "print", "repr"),
)
def test_repr_or_die_behavior_arms(
    on_error: str,
    expected: object,
) -> None:
    """
    Given: an unregistered instance and a parametrized behavior.
    When: repr_or_die runs.
    Then: the behavior-specific stringification is returned.
    """

    # --- Arrange ---
    class Subject: ...

    instance = Subject()
    render = expected

    # --- Act / Assert ---
    assert repr_or_die(instance, on_error=on_error) == render(instance)


def test_repr_or_die_ignore_returns_none_and_logs_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: an unregistered instance.
    When: repr_or_die runs with on_error="ignore".
    Then: None is returned and a debug record is logged.
    """

    # --- Arrange ---
    class Subject: ...

    # --- Act ---
    with caplog.at_level(logging.DEBUG, logger="zx.lib.serial.json"):
        result = repr_or_die(Subject(), on_error="ignore")

    # --- Assert ---
    assert result is None
    assert "unsupported type" in caplog.text


def test_repr_or_die_raise_raises_not_implemented_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: an unregistered instance.
    When: repr_or_die runs with on_error="raise".
    Then: NotImplementedError is raised and an error record is logged.
    """

    # --- Arrange ---
    class Subject: ...

    # --- Act / Assert ---
    with (
        caplog.at_level(logging.ERROR, logger="zx.lib.serial.json"),
        pytest.raises(NotImplementedError, match="unsupported type"),
    ):
        repr_or_die(Subject())
    assert "unsupported type" in caplog.text


# --- stringify ---


def test_stringify_success_returns_text_of_to_json() -> None:
    """
    Given: a JSON-safe payload.
    When: it is stringified.
    Then: the decoded text of the to_json bytes is returned.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    assert stringify({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_stringify_failure_falls_back_to_name_behavior(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: an unregistered instance that raises under on_error="raise".
    When: it is stringified.
    Then: the fallback renders the type name as a JSON string instead.
    """

    # --- Arrange ---
    class Subject: ...

    instance = Subject()

    # --- Act ---
    with caplog.at_level(logging.ERROR, logger="zx.lib.serial.json"):
        result = stringify(instance)

    # --- Assert ---
    assert orjson.loads(result) == Who.Is(instance)
    assert "failed to serialize object" in caplog.text


# --- edge / contract additions ---


SCALAR_CASES: tuple[tuple[object, bytes], ...] = (
    (42, b"42"),
    ("x", b'"x"'),
    (None, b"null"),
    (True, b"true"),
)
SCALAR_IDS = ("int", "str", "none", "bool")


def test_repr_or_die_unknown_behavior_raises_not_implemented_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: an unregistered instance.
    When: repr_or_die runs with an unknown on_error behavior.
    Then: NotImplementedError "unsupported type" is raised, error-logged.
    """

    # --- Arrange ---
    class Subject: ...

    # --- Act / Assert ---
    with (
        caplog.at_level(logging.ERROR, logger="zx.lib.serial.json"),
        pytest.raises(NotImplementedError, match="unsupported type"),
    ):
        repr_or_die(Subject(), on_error="bogus")  # type: ignore[arg-type]
    assert "unsupported type" in caplog.text


def test_to_json_ignore_behavior_propagates_to_nested_leaves() -> None:
    """
    Given: a dict with an unserializable leaf and on_error="ignore".
    When: it is converted via to_json.
    Then: the behavior propagates through the recursive normalization
        and the leaf renders as null.
    """
    # --- Arrange ---

    # --- Act ---
    result = to_json({"x": object()}, on_error="ignore")

    # --- Assert ---
    assert result == b'{"x":null}'


def test_dumps_ignore_behavior_renders_null_leaf() -> None:
    """
    Given: a dict with an unserializable leaf, dumped directly.
    When: dumps runs with on_error="ignore".
    Then: the leaf becomes JSON null — None, not omission.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    assert dumps({"x": object()}, on_error="ignore") == b'{"x":null}'


def test_encode_object_non_utc_aware_datetime_normalizes_to_utc_z() -> None:
    """
    Given: an aware datetime with a +02:00 offset.
    When: it passes through encode_object.
    Then: the dt wrapper normalizes to UTC — the rendered string carries
        a Z suffix and the shifted wall time, not the original offset.
    """
    # --- Arrange — pin: current behavior; audit expected the verbatim
    # --- "+02:00" offset form, but dt.ensure_tz astimezones to UTC.
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2)))

    # --- Act / Assert ---
    assert encode_object(moment) == "2026-01-02T01:04:05Z"


def test_dumps_binary_bytes_raise_type_error() -> None:
    """
    Given: bytes with control bytes that are not valid UTF-8.
    When: they are dumped at the top level.
    Then: TypeError surfaces from orjson's native bytes handling — orjson
        serializes bytes itself and never reaches the default hook, so the
        varchar decoding path is bypassed entirely.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="not JSON serializable"):
        dumps(b"\xff\x00\xfe")


@pytest.mark.parametrize(
    "on_error,render",
    (
        ("cast", Who.Cast),
        ("print", str),
    ),
    ids=("cast", "print"),
)
def test_encode_object_cast_and_print_arms(
    on_error: str,
    render: Callable[[object], str],
) -> None:
    """
    Given: an unregistered instance with pinned __repr__ and __str__.
    When: encode_object runs with the "cast" or "print" behavior.
    Then: Who.Cast / str renderings are returned respectively.
    """

    # --- Arrange ---
    class WithRepr:
        def __repr__(self) -> str:
            return "REPR!"

        def __str__(self) -> str:
            return "STR!"

    # --- Act / Assert ---
    assert encode_object(
        WithRepr(),
        on_error=on_error,  # type: ignore[arg-type]
    ) == render(WithRepr())


def test_encode_object_isinstance_scan_first_registered_wins(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: two base classes, both with registered serializers.
    When: an instance of both passes through encode_object.
    Then: the first-registered serializer wins — registry scan order.
    """

    # --- Arrange ---
    class BaseA: ...

    class BaseB: ...

    class Derived(BaseA, BaseB): ...

    serializer(BaseA, lambda _: {"via": "first"})
    serializer(BaseB, lambda _: {"via": "second"})

    # --- Act / Assert ---
    assert encode_object(Derived()) == {"via": "first"}


def test_encode_object_exact_class_hit_short_circuits_isinstance_scan(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a base serializer registered before a derived exact one.
    When: a derived instance passes through encode_object.
    Then: the exact-class lookup wins over the earlier isinstance hit.
    """

    # --- Arrange ---
    class Base: ...

    class Derived(Base): ...

    serializer(Base, lambda _: {"via": "isinstance"})
    serializer(Derived, lambda _: {"via": "exact"})

    # --- Act / Assert ---
    assert encode_object(Derived()) == {"via": "exact"}


def test_encode_object_isinstance_hit_returning_nothing_falls_through(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a base serializer returning Nothing, matched via isinstance.
    When: a derived instance passes through with on_error="raise".
    Then: the Nothing hit is discarded and TypeError is raised.
    """

    # --- Arrange ---
    class Base: ...

    class Derived(Base): ...

    serializer(Base, lambda _: Nothing)

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="couldn't serialize"):
        encode_object(Derived())


@pytest.mark.parametrize(
    "payload,expected",
    SCALAR_CASES,
    ids=SCALAR_IDS,
)
def test_to_json_scalar_passthrough(
    payload: object,
    expected: bytes,
) -> None:
    """
    Given: a parametrized scalar payload.
    When: it is converted via to_json.
    Then: orjson renders it natively, byte-identical.
    """
    # --- Arrange — payload parametrized.

    # --- Act / Assert ---
    assert to_json(payload) == expected


def test_to_json_non_str_keys_coerced_to_strings() -> None:
    """
    Given: a dict with an integer key.
    When: it is converted via to_json.
    Then: OPT_NON_STR_KEYS coerces the key to its string form.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    assert to_json({1: "a"}) == b'{"1":"a"}'


def test_to_json_dataclass_class_object_raises_type_error() -> None:
    """
    Given: a dataclass instance and its class object.
    When: the class object itself is passed to to_json.
    Then: asdict rejects it — TypeError "should be called on dataclass
        instances".
    """

    # --- Arrange ---
    @dataclasses.dataclass(frozen=True)
    class Record:
        a: int

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="should be called on dataclass"):
        to_json(Record)  # pin: current behavior — class object slips past
        # the is_dataclass guard into asdict, which wants an instance.


def test_dumps_explicit_option_bypasses_minify_indent_path() -> None:
    """
    Given: an explicit option mask plus minify=False.
    When: dumps runs.
    Then: the explicit mask replaces the defaults wholesale — no
        OPT_INDENT_2 is added, so the output stays compact (but sorted).
    """
    # --- Arrange — pin: the option/minify interaction; explicit option
    # --- skips the default-mask branch where minify adds indentation.

    # --- Act / Assert ---
    assert (
        dumps({"b": 1, "a": 2}, option=orjson.OPT_SORT_KEYS, minify=False)
        == b'{"a":2,"b":1}'
    )


def test_dumps_uuid_renders_quoted_hex_string() -> None:
    """
    Given: a UUID instance.
    When: it is dumped with the default options.
    Then: OPT_SERIALIZE_UUID renders its hex form as a quoted string.
    """
    # --- Arrange ---
    identifier = UUID("12345678-1234-5678-1234-567812345678")

    # --- Act / Assert ---
    assert dumps(identifier) == b'"12345678-1234-5678-1234-567812345678"'


def test_stringify_name_behavior_recovers_nested_leaves() -> None:
    """
    Given: a dict with an unserializable leaf and on_error="name".
    When: it is stringified.
    Then: the first attempt succeeds — the behavior propagates to nested
        leaves, which degrade to the class name inline.
    """
    # --- Arrange ---

    # --- Act ---
    result = stringify({"x": object()}, on_error="name")

    # --- Assert ---
    assert result == '{"x":"object"}'


def test_stringify_minify_false_indents_with_two_spaces() -> None:
    """
    Given: a small dict payload.
    When: it is stringified with minify=False.
    Then: the output carries newline plus two-space indentation.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    assert stringify({"a": 1}, minify=False) == '{\n  "a": 1\n}'


def test_jsonize_nested_bytes_and_date_round_trip_to_safe_types() -> None:
    """
    Given: a nested payload mixing bytes and date leaves.
    When: it is jsonized.
    Then: leaves become plain str — decoded text and ISO date form.
    """
    # --- Arrange ---
    payload = {"outer": [b"bytes", date(2020, 1, 1)]}

    # --- Act / Assert ---
    assert jsonize(payload) == {"outer": ["bytes", "2020-01-01"]}
