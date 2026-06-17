# Game-art asset nodes (first-class generation pipeline)

LeAgent ships a **first-class, composable** game-art generation system built
directly on the workflow engine — no adapter shims, no auto-generated
`Model.<task>.<provider>` node factory in the art path. The design follows
ComfyUI's node-extensibility model (hand-authored `WorkflowNode` subclasses,
typed sockets, a `NodeExtension` package) and carries generation capability
through professional design patterns rather than retrofitted spec-to-node
lifting.

The whole pipeline runs **end-to-end offline with zero credentials** via a
deterministic backend — ideal for demos, CI, and hermetic tests.

## At a glance

```
idea (chat) ──▶ Agent ReAct loop
                 ├─ chat_workflow_embed_emit ──▶ live workflow on the canvas
                 └─ workflow_save + workflow_run ──▶ WorkflowExecutor (DAG)

concept (Transform) ─▶ Art.ImageGen ─▶ QualityGateNode
                                          │ pass ─▶ approved ─▶ Art.Mesh3D ─┐
                                          │                  └▶ Art.VideoGen ┤
                                          └ fail ─▶ IterativeRefineNode ─(back-edge)─▶ Art.ImageGen
                                                                                       AssetExportNode ◀┘
```

## 1. Typed media sockets + `MediaRef`

Defined in [`workflow/io/types.py`](../../leagent/workflow/io/types.py) and
[`workflow/io/media.py`](../../leagent/workflow/io/media.py):

- First-class IO types `IO.Image` / `IO.Video` / `IO.Mesh3D` (io types
  `IMAGE` / `VIDEO` / `MESH3D`), each with a stable socket colour in
  `SOCKET_COLORS` and **link-only** rendering (no inline widget). This lets
  art nodes snap together on the canvas: `ImageGen → (IMAGE) → Mesh3D / VideoGen`.
- `MediaRef` is the **value object** that travels across these sockets. It is a
  storage-agnostic, *by-reference* handle (`file_id`, `preview_url`, `kind`,
  `mime`, `width/height`, `meta`) — assets never move as base64 through the
  graph. The canonical preview convention is `/api/v1/files/{id}/preview`.
- `KIND_TO_IO_TYPE` and `KIND_TO_GENUI` map a media kind to its socket type and
  its GenUI component (`Image` / `Video` / `Model3D`).

## 2. Generation backends — Strategy + Registry

[`leagent/llm/generation/`](../../leagent/llm/generation/) provides the unified
service the art nodes call. There is **no** adapter→node factory:

- `GenerationBackend` is a `Protocol` (`generate(kind, prompt, **params) ->
  GenerationOutput`). Backends register into the `GenerationService` facade
  (Strategy + Registry), which adds retry with exponential backoff and provider
  failover.
- Backends: `ImageProviderBackend` (reuses the existing OpenAI / DashScope
  image-gen providers), `LocalDiffusionBackend`, `HttpVideoBackend`,
  `HttpMesh3DBackend` (real providers, env-gated), and an always-registered
  **`OfflineGenerationBackend`** that emits minimal-valid `png` / `mp4` / `glb`
  bytes deterministically.
- The offline floor is forced globally with `LEAGENT_ART_OFFLINE=1`, or per node
  via `provider: offline`. With it set, every art workflow completes without any
  API key.

## 3. Art node pack — `BaseGenerationNode` (Template Method)

[`leagent/workflow/nodes/art/`](../../leagent/workflow/nodes/art/) exports
`ArtNodeExtension(NodeExtension)`. `BaseGenerationNode` owns the shared
execution skeleton; subclasses declare only their *kind*, output socket, and
node-specific params:

1. resolve the prompt template against workflow state,
2. collect node params + any upstream `MediaRef` conditioning,
3. call `GenerationService` (retries + failover),
4. register produced bytes as a managed artifact (`FileRef`) — via
   `register_tool_artifact`, honouring INV-1,
5. wrap it in a `MediaRef`, write it to state, and
6. emit a `NodeOutput.ui.gen_ui` asset preview for the canvas.

| Node id | Output | Purpose |
|---|---|---|
| `Art.ImageGen` | `IMAGE` | Text-to-image concept / sprite / texture |
| `Art.Upscale` | `IMAGE` | Image-to-image upscale / refine (composable post-process) |
| `Art.VideoGen` | `VIDEO` | Text/image-to-video (turntable, idle loop) |
| `Art.Mesh3D` | `MESH3D` | Image/text-to-3D mesh (engine-ready GLB) |

`provider` / `model` are exposed as `IO.Combo` widgets.

> The legacy `Model.image_gen.*` factory nodes are **deprecated** for the art
> path (audio TTS/ASR still flows through the factory to avoid regressions).

## 4. Control / evaluation nodes (engine-side self-correction)

In [`workflow/nodes/builtin/`](../../leagent/workflow/nodes/builtin/):

- **`QualityGateNode`** (`control_flow=True`) scores an upstream `MediaRef`,
  writes `state.quality_score`, and routes `pass`/`fail` against a `threshold`.
- **`IterativeRefineNode`** (`control_flow=True`, registered in
  `_LOOP_SAFE_TYPES`) provides a bounded `generate → evaluate → regenerate`
  back-edge: it counts iterations (`max_iterations`) and routes to
  `exhausted_node` once spent, so the validator's cycle DFS does not false-fire.
- **`AssetExportNode`** collates IMAGE/VIDEO/MESH3D into named assets + an
  engine-import manifest and returns `produced_files`, plus a GenUI gallery.

## 5. GenUI rendering

The art nodes are real producers of `NodeOutput.ui.gen_ui`. The GenUI schema
([`services/gen_ui/schema.py`](../../leagent/services/gen_ui/schema.py)) adds
`Video` and `Model3D` (GLB viewer) component kinds, rendered by the frontend
registry (`GenUiVideo`, `GenUiModel3D`). On the canvas, finished generation
nodes render an inline ComfyUI-style media thumbnail (`NodeMediaPreview`), and
the run panel groups all emitted assets into a dedicated **Assets** gallery.

## 6. Agent self-correction loop

- **`workflow_save`** ([`tools/workflow/workflow_save.py`](../../leagent/tools/workflow/workflow_save.py))
  validates an agent-authored graph against the canonical document (engine
  schema) and persists it as a runnable `Flow`, returning `flow_id` + a stable
  digest. Combined with `chat_workflow_embed_emit` (canvas preview) and
  `workflow_run` / `workflow_status`, this closes the
  **idea → design → run → evaluate → re-run** loop.
- The `ArtifactErrorTracker`
  ([`context/artifact_error_tracker.py`](../../leagent/context/artifact_error_tracker.py))
  is workflow-run aware: a run that fails *or* finishes below the quality bar
  (`quality_score < threshold`) is marked dirty, injecting a high-priority
  regeneration directive into the next turn's system prompt so the agent
  revises the graph and re-runs until the bar is met.

## 7. Flagship workflow + demos

- [`config/workflows/templates/TPL-ART-01.yaml`](../../../config/workflows/templates/TPL-ART-01.yaml)
  — "Game Art Asset Pipeline": concept expansion → concept image → quality gate
  → bounded self-correction → 3D mesh + turntable clip → asset export.
- [`config/demo-workflows/demo-art-pipeline.yaml`](../../../config/demo-workflows/demo-art-pipeline.yaml)
  — a compact demo of the self-correction back-edge.

Both pin generation nodes to `provider: offline` and complete `COMPLETED`
without credentials.

## 8. Tests

- Engine-side harness eval (scenario-based):
  [`tests/eval/test_workflow_generation_harness.py`](../../../backend/tests/eval/test_workflow_generation_harness.py)
  — asserts first-class node presence, a stable save/embed digest, offline
  end-to-end completion, that the self-correction loop actually fires, and an
  engine-ready manifest.
- Agent-side trace (scripted LLM + `EngineTrace`):
  [`tests/eval/test_workflow_agent_trace.py`](../../../backend/tests/eval/test_workflow_agent_trace.py)
  — the agent emits a valid canvas workflow that re-validates with a stable
  digest.
- Contract tests:
  [`tests/workflow/test_art_nodes_contract.py`](../../../backend/tests/workflow/test_art_nodes_contract.py)
  and the media-socket cases in
  [`tests/workflow/test_object_info_contract.py`](../../../backend/tests/workflow/test_object_info_contract.py).
