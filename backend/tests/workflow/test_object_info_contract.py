"""Wire-contract tests for ``/object_info`` editor rendering hints.

The litegraph-inspired React Flow editor depends on a stable shape:
each input carries a socket ``color`` + (for widget types) a ``widget``
kind, and each node carries an ``output_colors`` array aligned with its
outputs. These tests freeze that contract so accidental changes break
loudly.
"""

from __future__ import annotations

from leagent.workflow.io import IO, NodeOutput, Schema
from leagent.workflow.io.types import (
    DEFAULT_SOCKET_COLOR,
    SOCKET_COLORS,
    all_socket_colors,
    socket_color,
    widget_kind,
)
from leagent.workflow.nodes.base import WorkflowNode
from leagent.workflow.nodes.registry import NodeRegistry


class _TypedNode(WorkflowNode):
    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="TypedNode",
            display_name="Typed",
            category="test",
            inputs=[
                IO.String.Input(id="text", default="", multiline=True),
                IO.Int.Input(id="count", default=1),
                IO.Boolean.Input(id="flag", default=False),
                IO.Combo.Input(id="mode", choices=["a", "b"], default="a"),
                IO.Object.Input(id="payload", optional=True),
            ],
            outputs=[IO.String.Output(id="text_out"), IO.Object.Output(id="obj_out")],
        )

    async def execute(self, **kwargs) -> NodeOutput:  # pragma: no cover - trivial
        return NodeOutput.from_result({"text_out": "", "obj_out": {}})


def test_socket_color_known_and_unknown():
    assert socket_color("STRING") == SOCKET_COLORS["STRING"]
    assert socket_color("DEFINITELY_NOT_A_TYPE") == DEFAULT_SOCKET_COLOR


def test_socket_color_multitype_uses_first_known_member():
    assert socket_color("IMAGE,STRING") == SOCKET_COLORS["IMAGE"]
    assert socket_color("nope,STRING") == SOCKET_COLORS["STRING"]


def test_widget_kind_mapping():
    assert widget_kind("STRING") == "string"
    assert widget_kind("INT") == "int"
    assert widget_kind("BOOLEAN") == "toggle"
    assert widget_kind("COMBO") == "combo"
    # Object/array are link-only — no inline widget.
    assert widget_kind("OBJECT") == ""


def test_info_dict_inputs_carry_color_and_widget():
    info = _TypedNode.get_schema().get_info_dict()
    required = info["input"]["required"]

    text_type, text_opts = required["text"]
    assert text_type == "STRING"
    assert text_opts["color"] == SOCKET_COLORS["STRING"]
    assert text_opts["widget"] == "string"
    assert text_opts["multiline"] is True

    count_type, count_opts = required["count"]
    assert count_opts["color"] == SOCKET_COLORS["INT"]
    assert count_opts["widget"] == "int"

    # COMBO: the wire type becomes the choices list, colour stays COMBO.
    mode_type, mode_opts = required["mode"]
    assert mode_type == ["a", "b"]
    assert mode_opts["color"] == SOCKET_COLORS["COMBO"]
    assert mode_opts["widget"] == "combo"

    # Optional object input lands in the optional bucket, link-only.
    obj_type, obj_opts = info["input"]["optional"]["payload"]
    assert obj_type == "OBJECT"
    assert obj_opts["color"] == SOCKET_COLORS["OBJECT"]
    assert "widget" not in obj_opts


def test_info_dict_output_colors_align_with_outputs():
    info = _TypedNode.get_schema().get_info_dict()
    assert info["output"] == ["STRING", "OBJECT"]
    assert info["output_colors"] == [
        SOCKET_COLORS["STRING"],
        SOCKET_COLORS["OBJECT"],
    ]
    assert len(info["output_colors"]) == len(info["output"])


def test_registry_snapshot_exposes_hints():
    reg = NodeRegistry()
    reg.register(_TypedNode)
    snap = reg.snapshot()
    node = snap["TypedNode"]
    assert "output_colors" in node
    assert node["input"]["required"]["text"][1]["color"] == SOCKET_COLORS["STRING"]


def test_media_socket_types_have_colors_and_are_link_only():
    # First-class media sockets carry stable colours and render link-only
    # (no inline widget) — game-art assets travel by reference.
    for io_type in ("IMAGE", "VIDEO", "MESH3D", "AUDIO"):
        assert io_type in SOCKET_COLORS
        assert socket_color(io_type) == SOCKET_COLORS[io_type]
        assert widget_kind(io_type) == ""


class _MediaNode(WorkflowNode):
    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="MediaNode",
            display_name="Media",
            category="test",
            inputs=[IO.Image.Input(id="image", optional=True)],
            outputs=[
                IO.Image.Output(id="image"),
                IO.Video.Output(id="video"),
                IO.Mesh3D.Output(id="mesh"),
            ],
        )

    async def execute(self, **kwargs) -> NodeOutput:  # pragma: no cover - trivial
        return NodeOutput(values=({}, {}, {}))


def test_media_node_info_dict_exposes_typed_sockets():
    info = _MediaNode.get_schema().get_info_dict()
    assert info["output"] == ["IMAGE", "VIDEO", "MESH3D"]
    assert info["output_colors"] == [
        SOCKET_COLORS["IMAGE"],
        SOCKET_COLORS["VIDEO"],
        SOCKET_COLORS["MESH3D"],
    ]
    img_type, img_opts = info["input"]["optional"]["image"]
    assert img_type == "IMAGE"
    assert img_opts["color"] == SOCKET_COLORS["IMAGE"]
    assert "widget" not in img_opts


def test_all_socket_colors_is_a_copy():
    legend = all_socket_colors()
    assert legend["STRING"] == SOCKET_COLORS["STRING"]
    legend["STRING"] = "#000000"
    # Mutating the returned legend must not corrupt the module-level map.
    assert SOCKET_COLORS["STRING"] != "#000000"
