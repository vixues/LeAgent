"""Typed IO primitives for the workflow engine.

Every typed primitive declares an ``io_type`` string, a ``Type`` Python
alias, and nested ``Input`` / ``Output`` classes with ``as_dict()`` that
serialize to an OpenAPI-friendly descriptor. The frontend editor uses
this descriptor to render widgets.

A node's ``Schema`` references these ``Input`` / ``Output`` instances;
the validator uses ``io_type`` to check link compatibility
(``upstream.RETURN_TYPES[i] == downstream.INPUT_TYPES[slot]``). The
wildcard ``"*"`` matches any type.

Contract-parity with the reference ``_io.py``:

- :class:`Input` is the slim socket base (id, typing, linkage flags).
- :class:`WidgetInput` extends :class:`Input` with widget metadata
  (``default``, ``multiline``, ``lazy``, ``socketless``, ``widget_type``).
- Every :class:`Input` (and subclass) exposes a
  :meth:`Input.validate` hook the executor calls before ``execute()``.
- Primitive inputs carry rich options (``placeholder``, ``display``,
  ``round``, ``remote``, ``multiselect``, …) under ``as_dict()["options"]``.

The legacy alias ``InputBase`` is still exported as a synonym for
:class:`WidgetInput` so existing node definitions keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


WILDCARD_TYPE = "*"


@dataclass
class Input:
    """Slim socket-only input descriptor.

    Contains just the wire-level metadata: id, io_type, link flags, and
    a pluggable :meth:`validate` hook. Widget-specific fields
    (``default``, ``multiline``, ``lazy``, ``socketless``, …) live on
    :class:`WidgetInput`.
    """

    id: str
    display_name: str | None = None
    optional: bool = False
    tooltip: str | None = None
    force_input: bool = False
    raw_link: bool = False
    advanced: bool = False
    extra_dict: dict[str, Any] = field(default_factory=dict)

    io_type: ClassVar[str] = "UNKNOWN"

    def get_io_type(self) -> str:
        return self.io_type

    def validate(self, value: Any) -> tuple[bool, str | None]:
        """Validate a provided input value.

        Called by the executor before ``execute()`` runs. Returns
        ``(ok, error_message)``. Subclasses override to enforce type,
        range, enum, or regex constraints. Defaults to accepting any
        value.
        """
        return True, None

    def as_dict(self) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if self.tooltip:
            options["tooltip"] = self.tooltip
        if self.force_input:
            options["forceInput"] = True
        if self.raw_link:
            options["rawLink"] = True
        if self.advanced:
            options["advanced"] = True
        if self.display_name:
            options["displayName"] = self.display_name
        if self.extra_dict:
            options.update(self.extra_dict)
        extra = self._options_extra()
        if extra:
            options.update(extra)
        return {
            "id": self.id,
            "type": self.get_io_type(),
            "optional": self.optional,
            "options": options,
        }

    def _options_extra(self) -> dict[str, Any]:
        return {}


@dataclass
class WidgetInput(Input):
    """Input that also renders as an editable widget on the frontend.

    Adds the widget-editor fields (``default``, ``multiline``, ``lazy``,
    ``socketless``, ``widget_type``). Almost all typed primitives subclass
    :class:`WidgetInput`.
    """

    default: Any = None
    multiline: bool = False
    lazy: bool = False
    socketless: bool = False
    widget_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        base = super().as_dict()
        options = base.setdefault("options", {})
        if self.default is not None:
            options["default"] = self.default
        if self.multiline:
            options["multiline"] = True
        if self.lazy:
            options["lazy"] = True
        if self.socketless:
            options["socketless"] = True
        if self.widget_type:
            options["widgetType"] = self.widget_type
        if self.metadata:
            options.update(self.metadata)
        return base


InputBase = WidgetInput


@dataclass
class OutputBase:
    """Base class for all output descriptors."""

    id: str | None = None
    display_name: str | None = None
    tooltip: str | None = None
    is_list: bool = False

    io_type: ClassVar[str] = "UNKNOWN"

    def get_io_type(self) -> str:
        return self.io_type

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.get_io_type(),
            "display_name": self.display_name,
            "tooltip": self.tooltip,
            "is_list": self.is_list,
        }


def _make_typed(io_type: str, py_type: type) -> tuple[type, type]:
    """Factory for a typed (Input, Output) pair bound to ``io_type``.

    The produced input subclass inherits from :class:`WidgetInput` so
    primitive nodes get widget metadata by default.
    """

    input_cls = type(
        f"{io_type}Input",
        (WidgetInput,),
        {"io_type": io_type, "Type": py_type},
    )
    output_cls = type(
        f"{io_type}Output",
        (OutputBase,),
        {"io_type": io_type, "Type": py_type},
    )
    return input_cls, output_cls


class IO:
    """Namespace of typed IO primitives.

    Example:

        IO.String.Input("text", multiline=True, default="")
        IO.Int.Output(id="count")
        IO.Combo.Input("model", choices=["gpt-4", "qwen-max"])
    """

    class _Type:
        Input: type[Input]
        Output: type[OutputBase]
        io_type: str

    class String(_Type):
        io_type = "STRING"
        Type = str

        @dataclass
        class Input(WidgetInput):
            io_type: ClassVar[str] = "STRING"
            Type: ClassVar[type] = str
            placeholder: str | None = None
            dynamic_prompts: bool = False
            pattern: str | None = None
            min_length: int | None = None
            max_length: int | None = None

            def _options_extra(self) -> dict[str, Any]:
                extra: dict[str, Any] = {}
                if self.placeholder:
                    extra["placeholder"] = self.placeholder
                if self.dynamic_prompts:
                    extra["dynamicPrompts"] = True
                if self.pattern:
                    extra["pattern"] = self.pattern
                if self.min_length is not None:
                    extra["minLength"] = self.min_length
                if self.max_length is not None:
                    extra["maxLength"] = self.max_length
                return extra

            def validate(self, value: Any) -> tuple[bool, str | None]:
                if value is None:
                    return (True, None) if self.optional or self.default is not None else (
                        False, f"'{self.id}' is required",
                    )
                if not isinstance(value, str):
                    return False, f"'{self.id}' must be a string, got {type(value).__name__}"
                if self.min_length is not None and len(value) < self.min_length:
                    return False, f"'{self.id}' length < {self.min_length}"
                if self.max_length is not None and len(value) > self.max_length:
                    return False, f"'{self.id}' length > {self.max_length}"
                if self.pattern:
                    import re
                    if not re.fullmatch(self.pattern, value):
                        return False, f"'{self.id}' does not match pattern"
                return True, None

        Output = _make_typed("STRING", str)[1]

    class Int(_Type):
        io_type = "INT"
        Type = int

        @dataclass
        class Input(WidgetInput):
            io_type: ClassVar[str] = "INT"
            Type: ClassVar[type] = int
            min: int | None = None
            max: int | None = None
            step: int = 1
            display: str = "number"  # "number" | "slider"

            def _options_extra(self) -> dict[str, Any]:
                extra: dict[str, Any] = {"step": self.step, "display": self.display}
                if self.min is not None:
                    extra["min"] = self.min
                if self.max is not None:
                    extra["max"] = self.max
                return extra

            def validate(self, value: Any) -> tuple[bool, str | None]:
                if value is None:
                    return (True, None) if self.optional or self.default is not None else (
                        False, f"'{self.id}' is required",
                    )
                if isinstance(value, bool) or not isinstance(value, int):
                    if isinstance(value, str):
                        try:
                            value = int(value)
                        except ValueError:
                            return False, f"'{self.id}' must be an int"
                    else:
                        return False, f"'{self.id}' must be an int"
                if self.min is not None and value < self.min:
                    return False, f"'{self.id}' below min {self.min}"
                if self.max is not None and value > self.max:
                    return False, f"'{self.id}' above max {self.max}"
                return True, None

        Output = _make_typed("INT", int)[1]

    class Float(_Type):
        io_type = "FLOAT"
        Type = float

        @dataclass
        class Input(WidgetInput):
            io_type: ClassVar[str] = "FLOAT"
            Type: ClassVar[type] = float
            min: float | None = None
            max: float | None = None
            step: float = 0.01
            display: str = "number"  # "number" | "slider"
            round: float | None = None

            def _options_extra(self) -> dict[str, Any]:
                extra: dict[str, Any] = {"step": self.step, "display": self.display}
                if self.min is not None:
                    extra["min"] = self.min
                if self.max is not None:
                    extra["max"] = self.max
                if self.round is not None:
                    extra["round"] = self.round
                return extra

            def validate(self, value: Any) -> tuple[bool, str | None]:
                if value is None:
                    return (True, None) if self.optional or self.default is not None else (
                        False, f"'{self.id}' is required",
                    )
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False, f"'{self.id}' must be a number"
                if self.min is not None and value < self.min:
                    return False, f"'{self.id}' below min {self.min}"
                if self.max is not None and value > self.max:
                    return False, f"'{self.id}' above max {self.max}"
                return True, None

        Output = _make_typed("FLOAT", float)[1]

    class Boolean(_Type):
        io_type = "BOOLEAN"
        Type = bool

        @dataclass
        class Input(WidgetInput):
            io_type: ClassVar[str] = "BOOLEAN"
            Type: ClassVar[type] = bool
            label_on: str | None = None
            label_off: str | None = None

            def _options_extra(self) -> dict[str, Any]:
                extra: dict[str, Any] = {}
                if self.label_on:
                    extra["labelOn"] = self.label_on
                if self.label_off:
                    extra["labelOff"] = self.label_off
                return extra

            def validate(self, value: Any) -> tuple[bool, str | None]:
                if value is None:
                    return (True, None) if self.optional or self.default is not None else (
                        False, f"'{self.id}' is required",
                    )
                if not isinstance(value, bool):
                    return False, f"'{self.id}' must be bool"
                return True, None

        Output = _make_typed("BOOLEAN", bool)[1]

    class Combo(_Type):
        io_type = "COMBO"
        Type = str

        @dataclass
        class Input(WidgetInput):
            io_type: ClassVar[str] = "COMBO"
            Type: ClassVar[type] = str
            choices: list[str] = field(default_factory=list)
            multiselect: bool = False
            remote: dict[str, Any] | None = None

            def _options_extra(self) -> dict[str, Any]:
                extra: dict[str, Any] = {"choices": list(self.choices)}
                if self.multiselect:
                    extra["multiselect"] = True
                if self.remote is not None:
                    extra["remote"] = self.remote
                return extra

            def as_dict(self) -> dict[str, Any]:
                base = super().as_dict()
                base["type"] = list(self.choices)
                return base

            def validate(self, value: Any) -> tuple[bool, str | None]:
                if value is None:
                    return (True, None) if self.optional or self.default is not None else (
                        False, f"'{self.id}' is required",
                    )
                if not self.choices:
                    return True, None
                values = value if self.multiselect and isinstance(value, list) else [value]
                for v in values:
                    if v not in self.choices:
                        return False, f"'{self.id}' must be one of {self.choices}"
                return True, None

        Output = _make_typed("COMBO", str)[1]

    class Object(_Type):
        io_type = "OBJECT"
        Type = dict
        Input, Output = _make_typed("OBJECT", dict)

    class Array(_Type):
        io_type = "ARRAY"
        Type = list
        Input, Output = _make_typed("ARRAY", list)

    class File(_Type):
        io_type = "FILE"
        Type = str  # file id or path

        @dataclass
        class Input(WidgetInput):
            io_type: ClassVar[str] = "FILE"
            Type: ClassVar[type] = str
            accept: str | None = None  # e.g. "image/*,.pdf"

            def _options_extra(self) -> dict[str, Any]:
                extra: dict[str, Any] = {}
                if self.accept:
                    extra["accept"] = self.accept
                return extra

        Output = _make_typed("FILE", str)[1]

    class Datetime(_Type):
        io_type = "DATETIME"
        Type = str  # ISO-8601
        Input, Output = _make_typed("DATETIME", str)

    class Any_(_Type):
        io_type = WILDCARD_TYPE
        Type = object
        Input, Output = _make_typed(WILDCARD_TYPE, object)

    Any = Any_  # alias

    class MultiType(_Type):
        """Accepts any of several types. Wire type is ``"<T1>,<T2>"``."""

        io_type = "MULTI"
        Type = object

        @dataclass
        class Input(WidgetInput):
            types: list[str] = field(default_factory=list)

            def get_io_type(self) -> str:
                return ",".join(self.types) if self.types else "MULTI"

        @dataclass
        class Output(OutputBase):
            types: list[str] = field(default_factory=list)

            def get_io_type(self) -> str:
                return ",".join(self.types) if self.types else "MULTI"


def types_compatible(upstream: str, downstream: str) -> bool:
    """Return True if a link from ``upstream`` output type into ``downstream``
    input type is compatible.

    Rules:
    1. Wildcard ``"*"`` on either side always matches.
    2. Exact string equality matches.
    3. Multi-type descriptors (``"A,B"``) match if the sets intersect.
    """
    if upstream == WILDCARD_TYPE or downstream == WILDCARD_TYPE:
        return True
    if upstream == downstream:
        return True
    up_set = set(upstream.split(",")) if "," in upstream else {upstream}
    down_set = set(downstream.split(",")) if "," in downstream else {downstream}
    return bool(up_set & down_set)
