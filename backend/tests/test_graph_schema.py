"""Tests for graph / flow schema models used by the visual workflow editor.

Covers InputValue, Tweaks, NodeData, EdgeData, and FlowData including
edge cases for defaults, construction, and serialization.
"""

from __future__ import annotations

import pytest

from leagent.schema.graph import EdgeData, FlowData, InputValue, NodeData, Tweaks


# ===========================================================================
# InputValue
# ===========================================================================


class TestInputValue:
    def test_minimal_creation(self) -> None:
        iv = InputValue(name="amount")
        assert iv.name == "amount"

    def test_type_default(self) -> None:
        assert InputValue(name="x").type == "string"

    def test_required_default_false(self) -> None:
        assert InputValue(name="x").required is False

    def test_description_default(self) -> None:
        assert InputValue(name="x").description == ""

    def test_default_value_is_none(self) -> None:
        assert InputValue(name="x").default is None

    def test_options_is_none(self) -> None:
        assert InputValue(name="x").options is None

    def test_custom_type(self) -> None:
        iv = InputValue(name="count", type="integer", required=True, default=0)
        assert iv.type == "integer"
        assert iv.required is True
        assert iv.default == 0

    def test_with_options(self) -> None:
        iv = InputValue(name="level", type="string", options=["low", "medium", "high"])
        assert iv.options == ["low", "medium", "high"]

    def test_with_value(self) -> None:
        iv = InputValue(name="amount", value=100.0)
        assert iv.value == 100.0


# ===========================================================================
# Tweaks
# ===========================================================================


class TestTweaks:
    def test_creation(self) -> None:
        t = Tweaks(node_id="n1", field="label", value="New Label")
        assert t.node_id == "n1"
        assert t.field == "label"
        assert t.value == "New Label"

    def test_any_value_type(self) -> None:
        t = Tweaks(node_id="n2", field="params", value={"key": "val"})
        assert isinstance(t.value, dict)


# ===========================================================================
# NodeData
# ===========================================================================


class TestNodeData:
    def test_minimal_creation(self) -> None:
        node = NodeData(id="n1", type="start", label="Start")
        assert node.id == "n1"
        assert node.type == "start"
        assert node.label == "Start"

    def test_description_default(self) -> None:
        assert NodeData(id="n1", type="start", label="S").description == ""

    def test_tool_is_none_by_default(self) -> None:
        assert NodeData(id="n1", type="start", label="S").tool is None

    def test_params_default_empty(self) -> None:
        assert NodeData(id="n1", type="start", label="S").params == {}

    def test_inputs_default_empty(self) -> None:
        assert NodeData(id="n1", type="start", label="S").inputs == []

    def test_outputs_default_empty(self) -> None:
        assert NodeData(id="n1", type="start", label="S").outputs == []

    def test_position_default(self) -> None:
        pos = NodeData(id="n1", type="start", label="S").position
        assert isinstance(pos, dict)
        assert "x" in pos and "y" in pos

    def test_config_default_empty(self) -> None:
        assert NodeData(id="n1", type="start", label="S").config == {}

    def test_next_node_is_none(self) -> None:
        assert NodeData(id="n1", type="start", label="S").next_node is None

    def test_on_error_is_none(self) -> None:
        assert NodeData(id="n1", type="start", label="S").on_error is None

    def test_with_tool_and_params(self) -> None:
        node = NodeData(
            id="pdf",
            type="tool_call",
            label="Read PDF",
            tool="pdf_reader",
            params={"file_path": "${input.path}"},
        )
        assert node.tool == "pdf_reader"
        assert node.params["file_path"] == "${input.path}"

    def test_with_inputs_and_outputs(self) -> None:
        node = NodeData(
            id="llm",
            type="llm_call",
            label="Generate",
            inputs=[InputValue(name="text", type="string", required=True)],
            outputs=["response", "tokens_used"],
        )
        assert len(node.inputs) == 1
        assert node.inputs[0].name == "text"
        assert "response" in node.outputs

    def test_next_node_and_on_error(self) -> None:
        node = NodeData(
            id="validate",
            type="tool_call",
            label="Validate",
            next_node="approve",
            on_error="error_handler",
        )
        assert node.next_node == "approve"
        assert node.on_error == "error_handler"

    def test_custom_position(self) -> None:
        node = NodeData(
            id="n1",
            type="start",
            label="S",
            position={"x": 100.0, "y": 250.5},
        )
        assert node.position["x"] == 100.0
        assert node.position["y"] == 250.5

    def test_serialization(self) -> None:
        node = NodeData(id="n1", type="end", label="End")
        d = node.model_dump()
        assert d["id"] == "n1"
        assert d["type"] == "end"


# ===========================================================================
# EdgeData
# ===========================================================================


class TestEdgeData:
    def test_minimal_creation(self) -> None:
        edge = EdgeData(id="e1", source="n1", target="n2")
        assert edge.id == "e1"
        assert edge.source == "n1"
        assert edge.target == "n2"

    def test_source_handle_default(self) -> None:
        assert EdgeData(id="e1", source="n1", target="n2").source_handle is None

    def test_target_handle_default(self) -> None:
        assert EdgeData(id="e1", source="n1", target="n2").target_handle is None

    def test_label_default_empty(self) -> None:
        assert EdgeData(id="e1", source="n1", target="n2").label == ""

    def test_condition_default_none(self) -> None:
        assert EdgeData(id="e1", source="n1", target="n2").condition is None

    def test_animated_default_false(self) -> None:
        assert EdgeData(id="e1", source="n1", target="n2").animated is False

    def test_with_condition(self) -> None:
        edge = EdgeData(
            id="e-cond",
            source="decision",
            target="approved",
            label="Approved",
            condition="amount <= 500",
        )
        assert edge.condition == "amount <= 500"
        assert edge.label == "Approved"

    def test_with_handles(self) -> None:
        edge = EdgeData(
            id="e2",
            source="n1",
            target="n2",
            source_handle="output_0",
            target_handle="input_0",
        )
        assert edge.source_handle == "output_0"
        assert edge.target_handle == "input_0"

    def test_animated_edge(self) -> None:
        edge = EdgeData(id="e3", source="a", target="b", animated=True)
        assert edge.animated is True


# ===========================================================================
# FlowData
# ===========================================================================


class TestFlowData:
    def _nodes(self) -> list[NodeData]:
        return [
            NodeData(id="start", type="start", label="Start"),
            NodeData(
                id="process",
                type="tool_call",
                label="Process",
                tool="pdf_reader",
            ),
            NodeData(id="end", type="end", label="End"),
        ]

    def _edges(self) -> list[EdgeData]:
        return [
            EdgeData(id="e1", source="start", target="process"),
            EdgeData(id="e2", source="process", target="end"),
        ]

    def test_minimal_creation(self) -> None:
        flow = FlowData(flow_id="f1", name="test_flow")
        assert flow.flow_id == "f1"
        assert flow.name == "test_flow"

    def test_description_default(self) -> None:
        assert FlowData(flow_id="f1", name="test").description == ""

    def test_version_default(self) -> None:
        assert FlowData(flow_id="f1", name="test").version == "1.0"

    def test_nodes_and_edges(self) -> None:
        flow = FlowData(
            flow_id="f1",
            name="Invoice",
            nodes=self._nodes(),
            edges=self._edges(),
        )
        assert len(flow.nodes) == 3
        assert len(flow.edges) == 2

    def test_tweaks(self) -> None:
        tweaks = [Tweaks(node_id="start", field="label", value="Begin")]
        flow = FlowData(flow_id="f1", name="test", tweaks=tweaks)
        assert len(flow.tweaks) == 1
        assert flow.tweaks[0].value == "Begin"

    def test_metadata(self) -> None:
        flow = FlowData(
            flow_id="f1",
            name="test",
            metadata={"tags": ["finance"], "icon": "💰"},
        )
        assert flow.metadata["tags"] == ["finance"]
        assert flow.metadata["icon"] == "💰"

    def test_serialization_roundtrip(self) -> None:
        flow = FlowData(
            flow_id="f1",
            name="test",
            nodes=self._nodes(),
            edges=self._edges(),
            metadata={"env": "test"},
        )
        d = flow.model_dump()
        restored = FlowData(**d)
        assert restored.flow_id == "f1"
        assert len(restored.nodes) == 3

    def test_empty_nodes_and_edges(self) -> None:
        flow = FlowData(flow_id="f1", name="empty")
        assert flow.nodes == []
        assert flow.edges == []
        assert flow.tweaks == []
        assert flow.metadata == {}
