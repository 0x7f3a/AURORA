"""Minimal declarative validation, standard library only.

The configuration and scope schemas are validated by :class:`Field` and
:class:`Model` below. They used to be Pydantic models; AURORA has to start
from a bare interpreter (``python3 aurora.py``) on a machine with no package
manager, so the small set of features those models relied on lives here:

* explicitly typed fields with bounds, choices and length limits;
* nested models and tuples of models;
* rejection of unknown keys, so a typo in a safety limit is an error;
* validation errors that carry the path to the offending field.

:class:`ValidationError` is a :class:`ValueError`, matching the behaviour the
models had before, and exposes ``errors()`` the way configuration loading
formats it.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

__all__ = ["Field", "Model", "ValidationError"]

_MISSING = object()


class ValidationError(ValueError):
    """One or more field problems, each with the path to the offending field."""

    def __init__(self, problems: Iterable[tuple[tuple[Any, ...], str]]) -> None:
        self.problems: list[tuple[tuple[Any, ...], str]] = list(problems)
        super().__init__(
            "; ".join(f"{format_location(loc)}: {message}" for loc, message in self.problems)
        )

    def errors(self) -> list[dict[str, Any]]:
        """Field problems as ``{"loc": ..., "msg": ...}`` mappings."""

        return [{"loc": location, "msg": message} for location, message in self.problems]


def format_location(location: Sequence[Any]) -> str:
    """Render a field path the way configuration errors show it."""

    return ".".join(str(part) for part in location) or "<root>"


class Field:
    """One declared field: its kind, its default, and its bounds."""

    __slots__ = (
        "kind",
        "default",
        "factory",
        "model",
        "item",
        "choices",
        "gt",
        "ge",
        "le",
        "min_length",
        "max_length",
        "coerce",
    )

    def __init__(
        self,
        kind: str,
        *,
        default: Any = _MISSING,
        factory: Callable[[], Any] | None = None,
        model: type[Model] | None = None,
        item: Field | None = None,
        choices: tuple[Any, ...] | None = None,
        gt: float | None = None,
        ge: float | None = None,
        le: float | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        coerce: Callable[[Any], Any] | None = None,
    ) -> None:
        self.kind = kind
        self.default = default
        self.factory = factory
        self.model = model
        self.item = item
        self.choices = choices
        self.gt = gt
        self.ge = ge
        self.le = le
        self.min_length = min_length
        self.max_length = max_length
        self.coerce = coerce

    @property
    def has_default(self) -> bool:
        return self.default is not _MISSING or self.factory is not None

    def get_default(self) -> Any:
        return self.factory() if self.factory is not None else self.default


def _check_bounds(field: Field, number: float, location: tuple[Any, ...]) -> None:
    if field.gt is not None and not number > field.gt:
        raise ValidationError([(location, f"must be greater than {field.gt}")])
    if field.ge is not None and not number >= field.ge:
        raise ValidationError([(location, f"must be at least {field.ge}")])
    if field.le is not None and not number <= field.le:
        raise ValidationError([(location, f"must be at most {field.le}")])


def _number(field: Field, value: Any, location: tuple[Any, ...], *, integer: bool) -> int | float:
    if isinstance(value, bool):
        raise ValidationError([(location, "must be a number, not a boolean")])

    if integer:
        if isinstance(value, int):
            number = value
        elif isinstance(value, float) and value.is_integer():
            number = int(value)
        elif isinstance(value, str):
            try:
                number = int(value.strip(), 10)
            except ValueError:
                raise ValidationError([(location, "must be an integer")]) from None
        else:
            raise ValidationError(
                [(location, f"must be an integer, found {type(value).__name__}")]
            )
    else:
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            try:
                number = float(value.strip())
            except ValueError:
                raise ValidationError([(location, "must be a number")]) from None
        else:
            raise ValidationError([(location, f"must be a number, found {type(value).__name__}")])

    _check_bounds(field, number, location)
    return number


def _text(field: Field, value: Any, location: tuple[Any, ...]) -> str:
    if not isinstance(value, str):
        raise ValidationError(
            [(location, f"must be a string, found {type(value).__name__}")]
        )
    candidate = value
    if field.coerce is not None:
        candidate = field.coerce(candidate)
        if not isinstance(candidate, str):
            raise ValidationError([(location, "validator must return a string")])
    if field.min_length is not None and len(candidate) < field.min_length:
        raise ValidationError([(location, f"must be at least {field.min_length} characters")])
    if field.max_length is not None and len(candidate) > field.max_length:
        raise ValidationError([(location, f"must be at most {field.max_length} characters")])
    return candidate


def _validate(field: Field, value: Any, location: tuple[Any, ...]) -> Any:
    kind = field.kind
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValidationError([(location, "must be true or false")])
        return value
    if kind == "int":
        return _number(field, value, location, integer=True)
    if kind == "float":
        return _number(field, value, location, integer=False)
    if kind == "str":
        return _text(field, value, location)
    if kind == "literal":
        choices = field.choices or ()
        if not any(type(value) is type(choice) and value == choice for choice in choices):
            shown = ", ".join(repr(choice) for choice in choices)
            raise ValidationError([(location, f"must be one of {shown}")])
        return value
    if kind == "model":
        assert field.model is not None
        if isinstance(value, field.model):
            return value
        return field.model.model_validate(value, _location=location)
    if kind == "tuple":
        assert field.item is not None
        if not isinstance(value, (list, tuple)):
            raise ValidationError([(location, f"must be a list, found {type(value).__name__}")])
        return tuple(
            _validate(field.item, item, location + (index,)) for index, item in enumerate(value)
        )
    raise AssertionError(f"unknown field kind {kind!r}")


def _dump(value: Any, *, json_safe: bool) -> Any:
    if isinstance(value, Model):
        return value.model_dump(mode="json" if json_safe else "python")
    if isinstance(value, tuple):
        items = [_dump(item, json_safe=json_safe) for item in value]
        return items if json_safe else tuple(items)
    return value


class Model:
    """A validated record: declared fields, no unknown keys, value equality."""

    _fields: dict[str, Field] = {}

    def __init__(self, **values: Any) -> None:
        self._apply(self._validate_mapping(values, ()))

    # -- construction ----------------------------------------------------

    @classmethod
    def model_validate(
        cls, data: Any, *, _location: tuple[Any, ...] = ()
    ) -> "Model":
        """Build an instance from a mapping (for example a JSON object)."""

        if isinstance(data, cls):
            return data
        instance = cls.__new__(cls)
        instance._apply(cls._validate_mapping(data, _location))
        return instance

    @classmethod
    def _before(cls, data: Any) -> Any:
        """Hook for input rewriting before fields are read."""

        return data

    @classmethod
    def _after(
        cls,
        values: dict[str, Any],
        location: tuple[Any, ...],
        problems: list[tuple[tuple[Any, ...], str]],
    ) -> None:
        """Hook for checks that span more than one field."""

    @classmethod
    def _validate_mapping(
        cls, data: Any, location: tuple[Any, ...]
    ) -> dict[str, Any]:
        data = cls._before(data)
        if not isinstance(data, Mapping):
            raise ValidationError(
                [(location, f"must be an object, found {type(data).__name__}")]
            )

        problems: list[tuple[tuple[Any, ...], str]] = []
        values: dict[str, Any] = {}
        for name, field in cls._fields.items():
            if name in data:
                try:
                    values[name] = _validate(field, data[name], location + (name,))
                except ValidationError as exc:
                    problems.extend(exc.problems)
                except ValueError as exc:
                    # A field validator (for example host normalisation) refused
                    # the value; report it against this field, not as a crash.
                    problems.append((location + (name,), str(exc)))
            elif field.has_default:
                values[name] = field.get_default()
            else:
                problems.append((location + (name,), "field required"))

        for name in data:
            if name not in cls._fields:
                problems.append((location + (name,), "unknown field"))

        cls._after(values, location, problems)
        if problems:
            raise ValidationError(problems)
        return values

    def _apply(self, values: dict[str, Any]) -> None:
        for name, value in values.items():
            object.__setattr__(self, name, value)

    # -- output ----------------------------------------------------------

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        """The declared fields, as a plain dict (tuples become lists in JSON mode)."""

        json_safe = mode == "json"
        return {
            name: _dump(getattr(self, name), json_safe=json_safe) for name in self._fields
        }

    def model_copy(self, *, update: Mapping[str, Any] | None = None) -> "Model":
        """A shallow copy, optionally with fields replaced (no revalidation)."""

        clone = copy.copy(self)
        for name, value in (update or {}).items():
            if name not in self._fields:
                raise ValueError(f"unknown field {name!r}")
            object.__setattr__(clone, name, value)
        return clone

    # -- comparison ------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return NotImplemented
        assert isinstance(other, Model)
        return all(
            getattr(self, name) == getattr(other, name) for name in self._fields
        )

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        fields = ", ".join(f"{name}={getattr(self, name)!r}" for name in self._fields)
        return f"{type(self).__name__}({fields})"
