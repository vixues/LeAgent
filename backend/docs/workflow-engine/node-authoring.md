# Node authoring

Custom nodes live either in `leagent/workflow/nodes/builtin/` (shipped
with the backend) or in a user-specified directory configured via
`LEAGENT_WORKFLOW__CUSTOM_NODES_DIR` (hot-reloaded at runtime).

## Minimal node

```python
from leagent.workflow.io import IO, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode


class UppercaseNode(WorkflowNode):
    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="UppercaseNode",
            display_name="Uppercase",
            category="strings",
            inputs=[IO.String.Input(id="text", default="")],
            outputs=[IO.String.Output(id="result")],
        )

    async def execute(self, *, text: str = "", **_: object) -> NodeOutput:
        return NodeOutput.from_result({"result": text.upper()})
```

Register it by placing the file in the custom-nodes directory; the
registry picks it up on startup and via the `POST /workflow/admin/reload-nodes`
admin endpoint.

## Contract hooks

Override `fingerprint_inputs` to make cache keys content-aware, or return
`NOT_CACHEABLE` to force re-execution:

```python
from leagent.workflow.io.contract import NOT_CACHEABLE

class RandomNode(WorkflowNode):
    def fingerprint_inputs(self, **_):
        return NOT_CACHEABLE
```

Override `check_lazy_status` to defer inputs (useful when a node can decide
which branch it needs based on the values it already has):

```python
class ChooseNode(WorkflowNode):
    def check_lazy_status(self, *, selector=None, **inputs):
        if selector == "a":
            return ["input_a"]
        return ["input_b"]
```

## Deprecations

Use `NodeReplaceRegistry` to steer stored workflows off deprecated nodes at
load time without rewriting every row:

```python
from leagent.workflow.nodes.replacement import NodeReplacement, get_replace_registry

get_replace_registry().register(
    NodeReplacement(old_class="LegacyFoo", new_class="Foo", reason="renamed"),
)
```

The server exposes CRUD for replacements at
`/api/v1/workflow/admin/replacements`.
