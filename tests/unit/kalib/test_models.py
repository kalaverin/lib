"""Tests for `zx.lib.models` — the typed model convention over pyserde."""

import dataclasses
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Any

import orjson
import pytest
from faker import Faker
from serde import SerdeError

from zx.lib import models

JSON_INDENT_WIDTH = 2


@models.model
class User(models.Model):
    """Strict test model with two required fields."""

    id: int
    name: str


@models.model
class Proto(models.Open):
    """Tolerant test model capturing unknown fields into `extra`."""

    id: int


@models.model
class Opt(models.Model):
    """Strict test model with a single optional field."""

    v: int | None = None


@models.model
class Outer(models.Model):
    """Strict test model nesting another model."""

    user: User


@models.model(deny_unknown_fields=False)
class Lenient(models.Model):
    """Strict-by-default model with the denial explicitly disabled."""

    id: int


@models.model
class Pet(models.Model):
    """Another strict model, for cross-class merge tests."""

    id: int


@models.model()
class Empty(models.Model):
    """A model without fields, declared via the empty-parentheses form."""


PayloadFactory = Callable[..., dict[str, Any]]


@pytest.fixture
def user_payload(fake: Faker) -> PayloadFactory:
    """A builder of valid `User` payloads with per-call overrides."""

    def _make_user_payload(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
        return {
            "id": fake.pyint(),
            "name": fake.first_name(),
            **overrides,
        }

    return _make_user_payload


@pytest.fixture
def proto_payload(fake: Faker) -> PayloadFactory:
    """A builder of valid `Proto` payloads with per-call overrides."""

    def _make_proto_payload(
        **overrides: object,
    ) -> dict[str, Any]:
        return {"id": fake.pyint(), **overrides}

    return _make_proto_payload


# --- decorator contract ---


def test_model_decorator_bare_form_produces_frozen_dataclass() -> None:
    """
    Given: the User model declared with the bare @models.model form.
    When: the class shape is inspected.
    Then: it is a frozen dataclass exposing the declared fields.
    """
    # --- Arrange ---

    # --- Act ---
    field_names = tuple(f.name for f in dataclasses.fields(User))

    # --- Assert ---
    assert dataclasses.is_dataclass(User)
    assert field_names == ("id", "name")


def test_model_field_assignment_raises_frozen_instance_error(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: an existing User instance.
    When: a field is reassigned.
    Then: a FrozenInstanceError is raised.
    """
    # --- Arrange ---
    user = User.load(user_payload())

    # --- Act / Assert ---
    with pytest.raises(dataclasses.FrozenInstanceError):
        user.name = "mutated"


def test_model_positional_arguments_raise_type_error(
    fake: Faker,
) -> None:
    """
    Given: the kw-only User model.
    When: it is constructed with positional arguments.
    Then: a TypeError is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(TypeError):
        User(fake.pyint(), fake.first_name())  # type: ignore[misc]


# --- load / loads / from_file ---


def test_load_with_self_instance_returns_identical_object(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: an existing User instance.
    When: it is passed to User.load.
    Then: the same object is returned unchanged.
    """
    # --- Arrange ---
    user = User.load(user_payload())

    # --- Act ---
    result = User.load(user)

    # --- Assert ---
    assert result is user


def test_load_with_valid_mapping_returns_model(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a mapping with valid User fields.
    When: it is loaded.
    Then: a model equal to direct construction is returned.
    """
    # --- Arrange ---
    payload = user_payload()

    # --- Act ---
    loaded = User.load(payload)

    # --- Assert ---
    assert loaded == User(id=payload["id"], name=payload["name"])


def test_load_with_unknown_field_raises_parse_error(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: a payload carrying a field absent from the schema.
    When: it is loaded into a strict model.
    Then: a ModelParseError naming the model is raised.
    """
    # --- Arrange ---
    payload = user_payload(**{fake.word(): fake.pyint()})

    # --- Act / Assert ---
    with pytest.raises(models.ModelParseError, match="unknown fields"):
        User.load(payload)


def test_load_with_missing_required_field_raises_parse_error(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a payload without the required name field.
    When: it is loaded.
    Then: a ModelParseError naming the model is raised.
    """
    # --- Arrange ---
    payload = user_payload()
    del payload["name"]

    # --- Act / Assert ---
    with pytest.raises(models.ModelParseError, match="missing required field"):
        User.load(payload)


def test_load_with_wrong_field_type_raises_parse_error(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: a payload with a string where an int is declared.
    When: it is loaded.
    Then: a ModelParseError naming the model is raised.
    """
    # --- Arrange ---
    payload = user_payload(id=fake.word())

    # --- Act / Assert ---
    with pytest.raises(models.ModelParseError, match="violates type hint"):
        User.load(payload)


def test_loads_with_valid_json_bytes_returns_model(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a JSON document with valid User fields.
    When: it is parsed via loads.
    Then: a model with the payload values is returned.
    """
    # --- Arrange ---
    payload = user_payload()
    body = orjson.dumps(payload)

    # --- Act ---
    loaded = User.loads(body)

    # --- Assert ---
    assert loaded == User(id=payload["id"], name=payload["name"])


def test_loads_with_malformed_json_raises_json_decode_error() -> None:
    """
    Given: a byte string that is not valid JSON.
    When: it is parsed via loads.
    Then: an orjson.JSONDecodeError is raised.
    """
    # --- Arrange ---
    body = b"{not json"

    # --- Act ---
    with pytest.raises(orjson.JSONDecodeError) as exc_info:
        User.loads(body)

    # --- Assert ---
    assert exc_info.type is orjson.JSONDecodeError


def test_from_file_with_valid_json_returns_model(
    tmp_path: Path,
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a JSON file with valid User fields.
    When: it is parsed via from_file.
    Then: a model with the file values is returned.
    """
    # --- Arrange ---
    payload = user_payload()
    document = tmp_path / "user.json"
    document.write_bytes(orjson.dumps(payload))

    # --- Act ---
    loaded = User.from_file(document)

    # --- Assert ---
    assert loaded == User(id=payload["id"], name=payload["name"])


def test_from_file_with_str_path_returns_model(
    tmp_path: Path,
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a JSON file referenced by a plain string path.
    When: it is parsed via from_file.
    Then: a model with the file values is returned.
    """
    # --- Arrange ---
    payload = user_payload()
    document = tmp_path / "user.json"
    document.write_bytes(orjson.dumps(payload))

    # --- Act ---
    loaded = User.from_file(str(document))

    # --- Assert ---
    assert loaded == User(id=payload["id"], name=payload["name"])


def test_from_file_with_missing_file_raises_file_not_found_error(
    tmp_path: Path,
) -> None:
    """
    Given: a path pointing to a nonexistent file.
    When: from_file is called.
    Then: a FileNotFoundError is raised.
    """
    # --- Arrange ---
    document = tmp_path / "absent.json"

    # --- Act / Assert ---
    with pytest.raises(FileNotFoundError):
        User.from_file(document)


# --- serialization ---


def test_as_dict_returns_field_values_as_plain_dict(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a User built from a payload.
    When: as_dict is called.
    Then: the payload values are returned as a plain dict.
    """
    # --- Arrange ---
    payload = user_payload()
    user = User.load(payload)

    # --- Act ---
    result = user.as_dict()

    # --- Assert ---
    assert result == payload


def test_as_json_default_returns_sorted_minified_bytes(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a User built from a payload.
    When: as_json is called with defaults.
    Then: sorted minified JSON bytes are returned.
    """
    # --- Arrange ---
    payload = user_payload()
    user = User.load(payload)

    # --- Act ---
    body = user.as_json()

    # --- Assert ---
    assert body == orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)


def test_as_json_with_minify_false_returns_indented_bytes(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a User built from a payload.
    When: as_json is called with minify disabled.
    Then: JSON bytes with a two-space indent are returned.
    """
    # --- Arrange ---
    payload = user_payload()
    user = User.load(payload)

    # --- Act ---
    body = user.as_json(minify=False)

    # --- Assert ---
    assert body == orjson.dumps(payload, option=orjson.OPT_INDENT_2)
    assert f"\n{' ' * JSON_INDENT_WIDTH}".encode() in body


def test_round_trip_loads_of_as_json_returns_equal_model(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a User built from a payload.
    When: it is serialized and parsed back.
    Then: the round trip yields an equal model.
    """
    # --- Arrange ---
    user = User.load(user_payload())

    # --- Act ---
    restored = User.loads(user.as_json())

    # --- Assert ---
    assert restored == user


# --- introspection ---


def test_fields_returns_declared_field_names() -> None:
    """
    Given: the User model class.
    When: fields are introspected on an instance.
    Then: the declared field names are returned in order.
    """
    # --- Arrange ---
    user = User(id=0, name="")

    # --- Act ---
    result = user.fields

    # --- Assert ---
    assert result == ("id", "name")


def test_fields_on_open_model_excludes_extra() -> None:
    """
    Given: the Proto model class with the extra catch-all.
    When: fields are introspected on an instance.
    Then: the catch-all bucket is not listed.
    """
    # --- Arrange ---
    proto = Proto(id=0)

    # --- Act ---
    result = proto.fields

    # --- Assert ---
    assert result == ("id",)


def test_defaults_returns_only_fields_with_defaults() -> None:
    """
    Given: the Opt model with a single defaulted field.
    When: defaults are introspected.
    Then: only the defaulted field is reported.
    """
    # --- Arrange ---

    # --- Act ---
    result = Opt.defaults()

    # --- Assert ---
    assert result == {"v": None}


def test_defaults_without_defaults_returns_empty_dict() -> None:
    """
    Given: the User model without defaulted fields.
    When: defaults are introspected.
    Then: an empty mapping is returned.
    """
    # --- Arrange ---

    # --- Act ---
    result = User.defaults()

    # --- Assert ---
    assert result == {}


# --- merge `|` ---


def test_merge_with_same_class_right_side_wins(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Users differing in the name field.
    When: they are merged.
    Then: the right side value wins.
    """
    # --- Arrange ---
    payload = user_payload()
    left = User.load(payload)
    right = User.load(user_payload(name=fake.first_name()))

    # --- Act ---
    merged = left | right

    # --- Assert ---
    assert merged == right


def test_merge_with_different_class_raises_type_error(
    fake: Faker,
) -> None:
    """
    Given: a User and a Pet.
    When: they are merged.
    Then: a TypeError naming both models is raised.
    """
    # --- Arrange ---
    user = User(id=fake.pyint(), name=fake.first_name())
    pet = Pet(id=fake.pyint())

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="cannot merge"):
        user | pet  # type: ignore[operator]


def test_merge_with_conflicting_field_types_raises_merge_error(
    proto_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Protos whose shared extra key has conflicting types.
    When: they are merged.
    Then: a ModelMergeError describing the conflict is raised.
    """
    # --- Arrange ---
    key = fake.word()
    left = Proto.load(proto_payload(**{key: fake.pyint()}))
    right = Proto.load(proto_payload(**{key: fake.word()}))

    # --- Act ---
    with pytest.raises(
        models.ModelMergeError,
        match="type conflict",
    ) as exc_info:
        left | right

    # --- Assert ---
    assert exc_info.type is models.ModelMergeError


@pytest.mark.parametrize(
    "left_value,right_value,expected",
    (
        (None, 5, 5),
        (5, None, None),
        (None, None, None),
        (1, 2, 2),
    ),
    ids=[
        "left-none-right-wins",
        "right-none-right-wins",
        "both-none-stays-none",
        "both-set-right-wins",
    ],
)
def test_merge_optional_field_none_rule(
    left_value: int | None,
    right_value: int | None,
    expected: int | None,
) -> None:
    """
    Given: two Opts with parametrized values.
    When: they are merged.
    Then: the right side wins and None skips the type check.
    """
    # --- Arrange ---
    left = Opt(v=left_value)
    right = Opt(v=right_value)

    # --- Act ---
    merged = left | right

    # --- Assert ---
    assert merged == Opt(v=expected)


def test_merge_with_open_models_merges_extra_fields(
    proto_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Protos with disjoint extra keys.
    When: they are merged.
    Then: the merged model carries both extra keys.
    """
    # --- Arrange ---
    own_key, their_key = fake.word(), fake.word()
    own_value, their_value = fake.pyint(), fake.word()
    left = Proto.load(proto_payload(**{own_key: own_value}))
    right = Proto.load(proto_payload(**{their_key: their_value}))

    # --- Act ---
    merged = left | right

    # --- Assert ---
    assert merged.extra == {own_key: own_value, their_key: their_value}


# --- patch algebra ---


def test_subtract_with_identical_models_returns_empty_patch(
    proto_payload: PayloadFactory,
) -> None:
    """
    Given: two equal Protos.
    When: one is subtracted from the other.
    Then: an empty patch is produced.
    """
    # --- Arrange ---
    payload = proto_payload()
    left = Proto.load(payload)
    right = Proto.load(payload)

    # --- Act ---
    patch = left - right

    # --- Assert ---
    assert patch.data == {}


def test_subtract_returns_keys_absent_from_other(
    proto_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Protos with partly disjoint extra keys.
    When: the right one is subtracted from the left one.
    Then: the patch holds only the keys unique to the left side.
    """
    # --- Arrange ---
    own_key, shared_key = fake.word(), fake.word()
    own_value, shared_value = fake.pyint(), fake.pyint()
    left = Proto.load(
        proto_payload(**{own_key: own_value, shared_key: shared_value}),
    )
    right = Proto.load(proto_payload(**{shared_key: shared_value}))

    # --- Act ---
    patch = left - right

    # --- Assert ---
    assert patch.data == {own_key: own_value}


def test_intersect_returns_shared_equal_values(
    proto_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Protos sharing one extra key with an equal value.
    When: they are intersected.
    Then: the patch holds the shared equal entries.
    """
    # --- Arrange ---
    shared_key, own_key = fake.word(), fake.word()
    shared_value = fake.pyint()
    payload = proto_payload()
    left = Proto.load(
        {**payload, shared_key: shared_value, own_key: fake.pyint()},
    )
    right = Proto.load({**payload, shared_key: shared_value})

    # --- Act ---
    patch = left & right

    # --- Assert ---
    assert patch.data == {"id": payload["id"], shared_key: shared_value}


def test_xor_returns_symmetric_difference(
    proto_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Protos with disjoint extra keys.
    When: the symmetric difference is taken.
    Then: the patch holds the unique keys of both sides.
    """
    # --- Arrange ---
    own_key, their_key = fake.word(), fake.word()
    own_value, their_value = fake.pyint(), fake.word()
    left = Proto.load(proto_payload(**{own_key: own_value}))
    right = Proto.load(proto_payload(**{their_key: their_value}))

    # --- Act ---
    patch = left ^ right

    # --- Assert ---
    assert patch.data == {own_key: own_value, their_key: their_value}


def test_patch_apply_with_compatible_patch_returns_patched_model(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: a User and a patch changing its name.
    When: the patch is applied.
    Then: a new User with the patched field is returned.
    """
    # --- Arrange ---
    payload = user_payload()
    base = User.load(payload)
    new_name = fake.first_name()
    patch = models.ModelPatch(data={"name": new_name})

    # --- Act ---
    patched = patch.apply(base)

    # --- Assert ---
    assert patched == User(id=payload["id"], name=new_name)


def test_patch_apply_with_conflicting_type_raises_merge_error(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: a User and a patch whose value conflicts in type.
    When: the patch is applied.
    Then: a ModelMergeError is raised.
    """
    # --- Arrange ---
    base = User.load(user_payload())
    patch = models.ModelPatch(data={"id": fake.word()})

    # --- Act / Assert ---
    with pytest.raises(models.ModelMergeError, match="type conflict"):
        patch.apply(base)


def test_patch_apply_with_unknown_key_raises_parse_error(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: a strict User and a patch with a key outside the schema.
    When: the patch is applied.
    Then: a ModelParseError naming the model is raised.
    """
    # --- Arrange ---
    base = User.load(user_payload())
    patch = models.ModelPatch(data={fake.word(): fake.pyint()})

    # --- Act / Assert ---
    with pytest.raises(models.ModelParseError, match="unknown fields"):
        patch.apply(base)


# --- diff ---


def test_diff_with_equal_models_returns_empty_report(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: two equal Users.
    When: theirs diff is computed.
    Then: an empty report is returned.
    """
    # --- Arrange ---
    payload = user_payload()
    left = User.load(payload)
    right = User.load(payload)

    # --- Act ---
    report = left.diff(right)

    # --- Assert ---
    assert report == models.ModelDiff()


def test_diff_with_changed_field_reports_old_and_new_values(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Users differing in the name field.
    When: theirs diff is computed.
    Then: the changed entry holds the old and new values.
    """
    # --- Arrange ---
    payload = user_payload()
    left = User.load(payload)
    right = User.load(user_payload(id=payload["id"], name=fake.first_name()))

    # --- Act ---
    report = left.diff(right)

    # --- Assert ---
    assert report.delta == {"name": (payload["name"], right.name)}


def test_diff_with_one_sided_keys_reports_missing_on_both_sides(
    proto_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Protos with disjoint extra keys.
    When: theirs diff is computed.
    Then: each side's unique keys are reported as missing on the other.
    """
    # --- Arrange ---
    own_key, their_key = fake.word(), fake.word()
    own_value, their_value = fake.pyint(), fake.word()
    left = Proto.load(proto_payload(**{own_key: own_value}))
    right = Proto.load(proto_payload(**{their_key: their_value}))

    # --- Act ---
    report = left.diff(right)

    # --- Assert ---
    assert report.ours == {their_key: their_value}
    assert report.theirs == {own_key: own_value}


# --- Open catch-all ---


def test_open_load_captures_unknown_fields_into_extra(
    proto_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: a payload with a field absent from the Proto schema.
    When: it is loaded into the tolerant model.
    Then: the unknown field lands in the extra bucket.
    """
    # --- Arrange ---
    unknown_key, unknown_value = fake.word(), fake.word()
    payload = proto_payload(**{unknown_key: unknown_value})

    # --- Act ---
    proto = Proto.load(payload)

    # --- Assert ---
    assert proto.extra == {unknown_key: unknown_value}


def test_open_load_with_only_known_fields_returns_empty_extra(
    proto_payload: PayloadFactory,
) -> None:
    """
    Given: a payload with only the declared Proto fields.
    When: it is loaded.
    Then: the extra bucket is empty.
    """
    # --- Arrange ---
    payload = proto_payload()

    # --- Act ---
    proto = Proto.load(payload)

    # --- Assert ---
    assert proto.extra == {}


def test_open_as_json_round_trips_extra_fields(
    proto_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: a Proto with captured extra fields.
    When: it is serialized and parsed back.
    Then: the round trip yields an equal model with the extras intact.
    """
    # --- Arrange ---
    proto = Proto.load(
        proto_payload(**{fake.word(): fake.word()}),
    )

    # --- Act ---
    restored = Proto.loads(proto.as_json())

    # --- Assert ---
    assert restored == proto


# --- nested models ---


def test_nested_model_loads_returns_typed_inner_model(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a JSON document with a nested user object.
    When: it is parsed into Outer.
    Then: the inner value is a typed User instance.
    """
    # --- Arrange ---
    payload = user_payload()
    body = orjson.dumps({"user": payload})

    # --- Act ---
    outer = Outer.loads(body)

    # --- Assert ---
    assert outer.user == User(id=payload["id"], name=payload["name"])


def test_nested_model_with_unknown_inner_field_raises_parse_error(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: a JSON document whose nested user carries an unknown field.
    When: it is parsed into Outer.
    Then: a ModelParseError is raised.
    """
    # --- Arrange ---
    inner = user_payload(**{fake.word(): fake.pyint()})
    body = orjson.dumps({"user": inner})

    # --- Act / Assert ---
    with pytest.raises(models.ModelParseError):
        Outer.loads(body)


# --- deny_unknown_fields override ---


def test_model_with_deny_unknown_fields_false_ignores_unknown_input(
    fake: Faker,
) -> None:
    """
    Given: the Lenient model with the denial disabled.
    When: a payload with unknown fields is loaded.
    Then: the unknown fields are silently ignored.
    """
    # --- Arrange ---
    payload = {
        "id": fake.pyint(),
        fake.word(): fake.word(),
    }

    # --- Act ---
    lenient = Lenient.load(payload)

    # --- Assert ---
    assert lenient == Lenient(id=payload["id"])


# --- error taxonomy ---


def test_model_error_taxonomy() -> None:
    """
    Given: the models error classes.
    When: theirs inheritance is inspected.
    Then: all of them derive from ModelError.
    """
    # --- Arrange ---

    # --- Act ---
    taxonomy = (
        issubclass(models.ModelParseError, models.ModelError),
        issubclass(models.ModelMergeError, models.ModelError),
        issubclass(models.ModelSchemeError, models.ModelError),
        issubclass(models.ModelError, Exception),
    )

    # --- Assert ---
    assert all(taxonomy)


# --- hardening: boundary shapes and operator exclusion semantics ---


def test_loads_with_str_input_returns_model(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a JSON document as a plain string.
    When: it is parsed via loads.
    Then: a model with the payload values is returned.
    """
    # --- Arrange ---
    payload = user_payload()
    body = orjson.dumps(payload).decode()

    # --- Act ---
    loaded = User.loads(body)

    # --- Assert ---
    assert loaded == User(id=payload["id"], name=payload["name"])


def test_load_with_read_only_mapping_returns_model(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a payload wrapped in a read-only mapping proxy.
    When: it is loaded.
    Then: a model with the payload values is returned.
    """
    # --- Arrange ---
    payload = user_payload()

    # --- Act ---
    loaded = User.load(MappingProxyType(payload))

    # --- Assert ---
    assert loaded == User(id=payload["id"], name=payload["name"])


def test_defaults_on_open_model_excludes_extra() -> None:
    """
    Given: the Proto model whose extra bucket has a default factory.
    When: defaults are introspected.
    Then: the catch-all bucket is not reported as a default.
    """
    # --- Arrange ---

    # --- Act ---
    result = Proto.defaults()

    # --- Assert ---
    assert result == {}


def test_subtract_with_same_key_different_value_returns_empty_patch(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Users sharing all keys but differing in name.
    When: the right one is subtracted from the left one.
    Then: the patch is empty — subtraction is key-based, not value-based.
    """
    # --- Arrange ---
    payload = user_payload()
    left = User.load(payload)
    right = User.load(user_payload(id=payload["id"], name=fake.first_name()))

    # --- Act ---
    patch = left - right

    # --- Assert ---
    assert patch.data == {}


def test_intersect_with_same_key_different_value_excludes_key(
    user_payload: PayloadFactory,
    fake: Faker,
) -> None:
    """
    Given: two Users sharing all keys but differing in name.
    When: they are intersected.
    Then: the patch holds only entries with equal values.
    """
    # --- Arrange ---
    payload = user_payload()
    left = User.load(payload)
    right = User.load(user_payload(id=payload["id"], name=fake.first_name()))

    # --- Act ---
    patch = left & right

    # --- Assert ---
    assert patch.data == {"id": payload["id"]}


def test_patch_apply_with_empty_patch_returns_equal_model(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a User and an empty patch.
    When: the patch is applied.
    Then: an equal model is returned.
    """
    # --- Arrange ---
    base = User.load(user_payload())
    patch = models.ModelPatch()

    # --- Act ---
    patched = patch.apply(base)

    # --- Assert ---
    assert patched == base


def test_merge_with_bool_and_int_conflict_raises_merge_error(
    fake: Faker,
) -> None:
    """
    Given: two Users whose id holds bool on one side and int on the other.
    When: they are merged.
    Then: a ModelMergeError is raised despite bool being an int subclass.
    """
    # --- Arrange ---
    left = User(id=True, name=fake.first_name())
    right = User(id=fake.pyint(), name=fake.first_name())

    # --- Act / Assert ---
    with pytest.raises(models.ModelMergeError, match="type conflict"):
        left | right


def test_model_decorator_empty_parentheses_form_produces_working_model() -> (
    None
):
    """
    Given: the Empty model declared via the @models.model() form.
    When: an empty JSON document is parsed.
    Then: a model instance is returned.
    """
    # --- Arrange ---

    # --- Act ---
    empty = Empty.loads(b"{}")

    # --- Assert ---
    assert empty == Empty()


def test_empty_model_with_unknown_field_raises_parse_error(
    fake: Faker,
) -> None:
    """
    Given: the Empty model declared with no fields.
    When: a document with an unknown field is parsed.
    Then: a ModelParseError is raised.
    """
    # --- Arrange ---
    body = orjson.dumps({fake.word(): fake.pyint()})

    # --- Act / Assert ---
    with pytest.raises(models.ModelParseError, match="unknown fields"):
        Empty.loads(body)


def test_from_file_with_directory_raises_is_a_directory_error(
    tmp_path: Path,
) -> None:
    """
    Given: a path pointing to a directory.
    When: from_file is called.
    Then: an IsADirectoryError is raised.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(IsADirectoryError):
        User.from_file(tmp_path)


def test_diff_with_different_classes_compares_field_dicts(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a User and a Proto built from the same id.
    When: theirs diff is computed.
    Then: the User-only field is reported as missing on the Proto side.
    """
    # --- Arrange ---
    payload = user_payload()
    user = User.load(payload)
    proto = Proto(id=payload["id"])

    # --- Act ---
    report = user.diff(proto)

    # --- Assert ---
    assert report.theirs == {"name": payload["name"]}
    assert report.ours == {}
    assert report.delta == {}


# --- edge cases: contract escapes, cross-class algebra, extra shadowing ---


@pytest.mark.parametrize("data", (None, [1, 2]), ids=("none", "list"))
def test_load_with_non_mapping_raises_serde_error_from_type_check(
    data: object,
) -> None:
    """
    Given: a parametrized non-mapping value.
    When: it is passed to Model.load.
    Then: a ModelSchemeError surfaces — the argument itself is invalid.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(models.ModelSchemeError, match="expected a mapping"):
        User.load(data)


def test_patch_algebra_cross_class_operands_do_not_type_check(
    user_payload: PayloadFactory,
) -> None:
    """
    Given: a User and a Pet carrying the same id.
    When: the patch-algebra operators are applied across the classes.
    Then: they silently compare field dicts.

    pin: current behavior, flagged — unlike __or__, none of __sub__,
    __and__ or __xor__ checks the operand class.
    """

    # --- Arrange ---
    payload = user_payload()
    user = User.load(payload)
    pet = Pet(id=payload["id"])

    # --- Act ---
    subtracted = user - pet
    intersected = user & pet
    xored = user ^ pet

    # --- Assert ---
    assert subtracted.data == {"name": payload["name"]}
    assert intersected.data == {"id": payload["id"]}
    assert xored.data == {"name": payload["name"]}


def test_diff_between_open_models_reports_changed_extra_value() -> None:
    """
    Given: two Protos sharing one extra key with different values.
    When: theirs diff is computed.
    Then: the changed extra key lands in the delta with both values.
    """

    # --- Arrange ---
    left = Proto.load({"id": 1, "role": "admin"})
    right = Proto.load({"id": 1, "role": "user"})

    # --- Act ---
    report = left.diff(right)

    # --- Assert ---
    assert report.delta == {"role": ("admin", "user")}


def test_patch_apply_on_open_model_captures_unknown_keys_into_extra() -> None:
    """
    Given: a Proto base model and a patch with a key outside the schema.
    When: the patch is applied.
    Then: the unknown key is captured into extra, not rejected.
    """

    # --- Arrange ---
    base = Proto(id=1)
    patch = models.ModelPatch(data={"role": "admin"})

    # --- Act ---
    patched = patch.apply(base)

    # --- Assert ---
    assert patched.id == 1
    assert patched.extra == {"role": "admin"}


def test_defaults_excludes_plain_default_factory_fields() -> None:
    """
    Given: a strict model with a plain default_factory field (not extra).
    When: defaults are introspected.
    Then: the factory field is excluded — only literal defaults report.
    """

    # --- Arrange ---
    @models.model
    class Bag(models.Model):
        """Strict model with a defaulted-by-factory list field."""

        items: list[int] = models.field(default_factory=list)

    # --- Act ---
    result = Bag.defaults()

    # --- Assert ---
    assert result == {}
    assert Bag().items == []


def test_loads_with_array_of_pairs_rejected_by_type_check() -> None:
    """
    Given: a JSON document shaped as an array of key-value pairs.
    When: it is parsed via loads.
    Then: a ModelSchemeError surfaces — the decoded document is not a
        mapping, so the argument itself is invalid.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(models.ModelSchemeError, match="expected a mapping"):
        Proto.loads(b'[["id", 7]]')


def test_open_round_trip_declared_field_shadows_same_named_extra_key() -> None:
    """
    Given: a Proto whose extra bucket carries a key named like a declared
        field, with a different value.
    When: it is serialized and parsed back.
    Then: the declared field value wins — extra never overwrites it.
    """

    # --- Arrange ---
    proto = Proto(id=1, extra={"id": 99, "role": "admin"})

    # --- Act ---
    restored = Proto.loads(proto.as_json())

    # --- Assert ---
    assert proto.as_dict() == {"id": 1, "role": "admin"}
    assert restored.id == 1
    assert restored.extra == {"role": "admin"}


def test_model_frozen_false_on_model_subclass_raises_scheme_error() -> None:
    """
    Given: a subclass of Model.
    When: the model decorator is applied with frozen=False.
    Then: ModelSchemeError is raised — frozen and non-frozen dataclasses
        cannot mix within one hierarchy.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(models.ModelSchemeError, match="frozen"):

        @models.model(frozen=False)  # type: ignore[misc]
        class Mutant(models.Model):
            id: int
