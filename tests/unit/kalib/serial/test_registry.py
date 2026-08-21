"""Tests for `zx.lib.serial.registry` — registration forms and duplicates."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from zx.lib.exceptions import Error
from zx.lib.serial.errors import RegistryError
from zx.lib.serial.json import jsonize
from zx.lib.serial.registry import SERIALIZER_REGISTRY, serializer

RegistrySnapshot = Iterator[None]


# --- registration forms ---


def test_serializer_decorator_form_registers(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a throwaway class and the decorator form of serializer.
    When: the decorator is applied.
    Then: the class is registered and the original function is returned.
    """

    # --- Arrange ---
    class Subject: ...

    # --- Act ---
    @serializer(Subject)
    def handler(obj: object) -> str:
        return str(obj)

    # --- Assert ---
    assert SERIALIZER_REGISTRY[Subject] is handler


def test_serializer_multi_class_form_registers_all(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: two throwaway classes and the multi-class decorator form.
    When: the decorator is applied.
    Then: both classes map to the same function.
    """

    # --- Arrange ---
    class First: ...

    class Second: ...

    # --- Act ---
    @serializer(First, Second)
    def handler(obj: object) -> str:
        return str(obj)

    # --- Assert ---
    assert SERIALIZER_REGISTRY[First] is handler
    assert SERIALIZER_REGISTRY[Second] is handler


def test_serializer_direct_call_form_registers(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a throwaway class and a plain function.
    When: serializer is called directly with both.
    Then: the class is registered and the function is returned unchanged.
    """

    # --- Arrange ---
    class Subject: ...

    def handler(obj: object) -> str:
        return str(obj)

    # --- Act ---
    result = serializer(Subject, handler)

    # --- Assert ---
    assert result is handler
    assert SERIALIZER_REGISTRY[Subject] is handler


@pytest.mark.parametrize(
    "reference",
    ("builtins.frozenset", b"builtins.frozenset"),
    ids=("dotted-string", "dotted-bytes"),
)
def test_serializer_dotted_path_form_resolves_class(
    registry_snapshot: RegistrySnapshot,
    reference: str | bytes,
) -> None:
    """
    Given: a dotted class reference as str or bytes.
    When: serializer is called directly with it.
    Then: the reference is resolved and the resolved class is registered.
    """

    # --- Arrange ---
    def handler(obj: object) -> str:
        return str(obj)

    # --- Act ---
    serializer(reference, handler)

    # --- Assert ---
    assert SERIALIZER_REGISTRY[frozenset] is handler


# --- duplicate semantics ---


def test_serializer_duplicate_registration_raises_registry_error(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a class with an already-registered serializer.
    When: a different function is registered for the same class.
    Then: a RegistryError naming the collision is raised.
    """

    # --- Arrange ---
    class Subject: ...

    def first(obj: object) -> str:
        return str(obj)

    def second(obj: object) -> bytes:
        return b"second"

    serializer(Subject, first)

    # --- Act / Assert ---
    with pytest.raises(RegistryError, match="already registered"):
        serializer(Subject, second)


def test_serializer_reregistering_same_function_is_silent_noop(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a class with an already-registered serializer.
    When: the same function is registered again.
    Then: the registration is a silent no-op keeping the original mapping.
    """

    # --- Arrange ---
    class Subject: ...

    def handler(obj: object) -> str:
        return str(obj)

    serializer(Subject, handler)

    # --- Act ---
    serializer(Subject, handler)

    # --- Assert ---
    assert SERIALIZER_REGISTRY[Subject] is handler


# --- built-ins and observability ---


def test_builtin_serializers_registered_at_import() -> None:
    """
    Given: the package imported.
    When: the registry is inspected.
    Then: the built-in serializers for Path, BaseModel and Error are present.
    """
    # --- Arrange ---

    # --- Act ---
    builtins = {
        cls: SERIALIZER_REGISTRY[cls].__name__
        for cls in (Path, BaseModel, Error)
    }

    # --- Assert ---
    assert builtins == {
        Path: "from_pathlib",
        BaseModel: "from_pydantic",
        Error: "from_error",
    }


def test_serializer_logs_registration(
    registry_snapshot: RegistrySnapshot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: a throwaway class.
    When: a serializer is registered for it.
    Then: an INFO record "registered serializer" is logged.
    """

    # --- Arrange ---
    class Subject: ...

    def handler(obj: object) -> str:
        return str(obj)

    # --- Act ---
    with caplog.at_level(logging.INFO, logger="zx.lib.serial.registry"):
        serializer(Subject, handler)

    # --- Assert ---
    assert "registered serializer" in caplog.text


# --- edge cases and end-to-end serialization ---


def test_serializer_unresolvable_reference_raises_import_error() -> None:
    """
    Given: a dotted reference whose module exists but the member does not.
    When: serializer resolves it via required().
    Then: an ImportError naming the failed required() import is raised.
    """

    # --- Arrange ---
    def handler(obj: object) -> str:
        return str(obj)

    # --- Act / Assert ---
    with pytest.raises(ImportError, match="couldn't import required"):
        serializer("builtins.nope", handler)


def test_serializer_distinct_functions_same_class_raises_registry_error(
    registry_snapshot: RegistrySnapshot,
) -> None:
    """
    Given: a class with a registered serializer.
    When: a different function is registered for the same class.
    Then: RegistryError is raised — the guard matches on name and file.

    pin: current behavior, flagged — audit expected a silent no-op for
    same-name collisions, but distinct functions are refused outright.
    """

    # --- Arrange ---
    class Subject: ...

    def _first_encoder(obj: object) -> str:
        return str(obj)

    def _second_encoder(obj: object) -> str:
        return "second"

    first = serializer(Subject, _first_encoder)

    # --- Act / Assert ---
    with pytest.raises(RegistryError, match="already registered"):
        serializer(Subject, _second_encoder)

    # --- Assert ---
    assert SERIALIZER_REGISTRY[Subject] is first


def test_to_json_pydantic_model_end_to_end() -> None:
    """
    Given: a pydantic BaseModel instance.
    When: it is serialized via the registry-driven jsonize contour.
    Then: the built-in from_pydantic serializer dumps it to a plain dict.
    """

    # --- Arrange ---
    class Record(BaseModel):
        id: int

    # --- Act ---
    result = jsonize(Record(id=42))

    # --- Assert ---
    assert result == {"id": 42}


def test_to_json_path_end_to_end() -> None:
    """
    Given: a pathlib.Path instance.
    When: it is serialized via the registry-driven jsonize contour.
    Then: the built-in from_pathlib serializer renders the string form.
    """

    # --- Arrange ---
    path = Path("some/report.txt")

    # --- Act ---
    result = jsonize(path)

    # --- Assert ---
    assert result == str(path)
