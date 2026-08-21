"""Typed record models with schema-strict parsing.

Models are plain frozen dataclasses declared with the `@model` decorator
and (de)serialized by pyserde. Fields present in the input but absent
from the schema are parse errors; inherit `Open` instead of `Model` to
capture them into an `extra` catch-all bucket that round-trips back on
serialization, so partially-known schemas stay prototype-friendly.

    from zx.lib import models

    @models.model
    class User(models.Model):
        id: int
        name: str

    @models.model
    class Prototype(models.Open):
        id: int

    Prototype.loads(b'{"id": 1, "role": "admin"}').extra
    # {"role": "admin"}
"""

import dataclasses
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Self, dataclass_transform, overload

import orjson
from serde import SerdeError, field, from_dict, serde, to_dict

from zx.core import Who
from zx.lib import serial

__all__ = (
    "Model",
    "ModelDiff",
    "ModelError",
    "ModelMergeError",
    "ModelParseError",
    "ModelPatch",
    "ModelSchemeError",
    "Open",
    "field",
    "model",
)


class ModelError(Exception):
    """Any model-layer failure."""


class ModelSchemeError(ModelError):
    """The model declaration or the API usage is invalid."""


class ModelParseError(ModelError):
    """The input data does not fit the model schema."""


class ModelMergeError(ModelError):
    """Merged values of the same field have conflicting types."""


@overload
def model[ModelT: Model](cls: type[ModelT], /) -> type[ModelT]: ...


@overload
def model[ModelT: Model](
    *,
    frozen: bool = True,
    deny_unknown_fields: bool = True,
    # Pass-through to @serde: options are heterogeneous by design.
    **serde_options: Any,  # noqa: ANN401
) -> Callable[[type[ModelT]], type[ModelT]]: ...


@dataclass_transform(
    kw_only_default=True,
    field_specifiers=(dataclasses.field, field),
)
def model[ModelT: Model](
    cls: type[ModelT] | None = None,
    /,
    *,
    frozen: bool = True,
    deny_unknown_fields: bool = True,
    # Pass-through to @serde: options are heterogeneous by design.
    **serde_options: Any,
) -> type[ModelT] | Callable[[type[ModelT]], type[ModelT]]:
    """Decorator: a frozen kw-only serde model with project conventions.

    Stacks `@serde(deny_unknown_fields=True)` over
    `@dataclass(frozen=True, kw_only=True)`: unknown input fields are
    parse errors. A `flatten` field (as in `Open`) neutralizes the
    denial by capturing unknown fields first. `frozen=False` is legal
    only for classes that do NOT inherit `Model`: dataclasses forbid
    mixing frozen and non-frozen classes within one hierarchy, and
    `Model` is frozen.

    Args:
      cls: The decorated class (bare `@model` form).
      frozen: Whether the resulting model is immutable.
      deny_unknown_fields: Whether unknown input fields are rejected.
      serde_options: Class attributes forwarded to `@serde`.

    Returns:
      The class converted into a serde-powered frozen dataclass.
    """

    def wrap(target: type[ModelT]) -> type[ModelT]:
        try:
            declared = dataclasses.dataclass(frozen=frozen, kw_only=True)(
                target,
            )
        except TypeError as e:
            msg = f"{Who.Is(target)}: invalid model declaration: {e}"
            raise ModelSchemeError(msg) from e
        return serde(
            deny_unknown_fields=deny_unknown_fields,
            **serde_options,
        )(declared)

    if cls is None:
        return wrap
    return wrap(cls)


def _merged(
    base: dict[str, Any],
    over: dict[str, Any],
    owner: str,
) -> dict[str, Any]:
    """Merges `over` into `base`, right side wins, types must match.

    None on either side is treated as absence: it never conflicts and the
    right-hand value wins regardless.
    """
    for key, value in over.items():
        current = base.get(key)
        if (
            value is not None
            and current is not None
            and type(value) is not type(current)
        ):
            msg = (
                f"{owner}: field {key!r} type conflict on merge: "
                f"{type(current).__name__} vs {type(value).__name__}"
            )
            raise ModelMergeError(msg)
        base[key] = value
    return base


@model
class ModelPatch:
    """A sparse subset of model fields produced by shape-changing algebra.

    Attributes:
        data: Surviving field values, including anything caught by `extra`.
    """

    data: dict[str, Any] = field(default_factory=dict)

    def apply(self, base: "Model") -> "Model":
        """Applies the patch over a base model; patch values win.

        Args:
          base: The model the patch is applied to.

        Returns:
          A new model of the base's class with patched fields.

        Raises:
          ModelMergeError: If a patched field conflicts in type.
          ModelParseError: If the patched data violates the schema.
        """
        return type(base).load(
            _merged(base.as_dict(), self.data, Who.Is(base)),
        )


@model
class ModelDiff:
    """A difference report between two models.

    Attributes:
        delta: Keys present on both sides with different values, mapped
            to (own, other) pairs.
        ours: Keys present only on the other side.
        theirs: Keys present only on this side.
    """

    delta: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    ours: dict[str, Any] = field(default_factory=dict)
    theirs: dict[str, Any] = field(default_factory=dict)


@model
class Model:
    """Base record model, strict: unknown input fields are parse errors.

    Inherit `Open` instead to collect unknown fields into `extra`.
    """

    @classmethod
    def load(cls, data: object) -> Self:
        """Parses a mapping into the model; parses are the validation.

        Args:
          data: A mapping of field values, or an existing instance
            (returned unchanged).

        Returns:
          A validated model instance.

        Raises:
          ModelSchemeError: If the argument itself is not a mapping.
          ModelParseError: If the data does not fit the schema.
        """
        if isinstance(data, cls):
            return data
        if not isinstance(data, Mapping):
            msg = f"{Who.Is(cls)}: expected a mapping, got {Who.Is(data)}"
            raise ModelSchemeError(msg)
        try:
            return from_dict(cls, dict(data))
        except SerdeError as e:
            msg = f"{Who.Is(cls)}: {e}"
            raise ModelParseError(msg) from e

    @classmethod
    def loads(cls, body: str | bytes) -> Self:
        """Parses a JSON document into the model.

        Args:
          body: A JSON string or bytes.

        Returns:
          A validated model instance.

        Raises:
          ModelParseError: If the data does not fit the schema.
        """
        return cls.load(orjson.loads(body))

    @classmethod
    def from_file(cls, path: str | Path) -> Self:
        """Parses a JSON file into the model.

        Args:
          path: The path to a JSON document.

        Returns:
          A validated model instance.

        Raises:
          ModelParseError: If the data does not fit the schema.
        """
        return cls.loads(Path(path).read_bytes())

    def as_dict(self) -> dict[str, Any]:
        """A plain-dict view; `extra` contents are flattened into it."""
        return to_dict(self)

    def as_json(self, *, minify: bool = True) -> bytes:
        """The model as JSON bytes with the project orjson conventions.

        Args:
          minify: Compact output when true, two-space indent otherwise.

        Returns:
          The serialized model.
        """
        return serial.dumps(self.as_dict(), minify=minify)

    @property
    def fields(self) -> tuple[str, ...]:
        """Declared field names, excluding the `extra` bucket of `Open`."""
        return tuple(
            f.name for f in dataclasses.fields(self) if f.name != "extra"
        )

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        """Declared literal defaults keyed by field name."""
        return {
            f.name: f.default
            for f in dataclasses.fields(cls)
            if f.default is not dataclasses.MISSING
        }

    def __or__(self, other: Self) -> Self:
        """Merges two models of the same class; the right side wins.

        Raises:
          TypeError: If the classes differ.
          ModelMergeError: If a shared field conflicts in type.
        """
        if type(other) is not type(self):
            msg = f"cannot merge {Who.Is(self)} with {Who.Is(other)}"
            raise TypeError(msg)
        return type(self).load(
            _merged(self.as_dict(), other.as_dict(), Who.Is(self)),
        )

    def __sub__(self, other: "Model") -> ModelPatch:
        """A patch of fields whose keys are absent from the other model."""
        theirs = other.as_dict()
        return ModelPatch(
            data={
                key: value
                for key, value in self.as_dict().items()
                if key not in theirs
            },
        )

    def __and__(self, other: "Model") -> ModelPatch:
        """A patch of fields both models share with equal values."""
        theirs = other.as_dict()
        return ModelPatch(
            data={
                key: value
                for key, value in self.as_dict().items()
                if key in theirs and theirs[key] == value
            },
        )

    def __xor__(self, other: "Model") -> ModelPatch:
        """A patch of fields present on exactly one side."""
        mine, theirs = self.as_dict(), other.as_dict()
        return ModelPatch(
            data={
                **{k: v for k, v in mine.items() if k not in theirs},
                **{k: v for k, v in theirs.items() if k not in mine},
            },
        )

    def diff(self, other: "Model") -> ModelDiff:
        """A full difference report against another model."""
        mine, theirs = self.as_dict(), other.as_dict()
        return ModelDiff(
            delta={
                key: (value, theirs[key])
                for key, value in mine.items()
                if key in theirs and theirs[key] != value
            },
            ours={
                key: value for key, value in theirs.items() if key not in mine
            },
            theirs={
                key: value for key, value in mine.items() if key not in theirs
            },
        )


@model
class Open(Model):
    """A `Model` that captures unknown input fields into `extra`.

    The catch-all bucket round-trips: `extra` contents are flattened
    back into the output of `as_dict` and `as_json`.

    Attributes:
        extra: Fields present in the input but not declared in the schema.
    """

    extra: dict[str, Any] = field(flatten=True, default_factory=dict)
