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

concept (Transform) ─▶ Art.ImageGen ─▶ Art.QualityCritic ─▶ QualityGateNode
                                          │ pass ─▶ approved ─▶ Art.Mesh3D ──┐
                                          │                  ├▶ Art.VideoGen ┤
                                          │                  └▶ Art.VFXGen ──┤
                                          └ fail ─▶ IterativeRefineNode ─(feedback back-edge)─▶ Art.ImageGen
                                                            AssetExportNode (engine-ready .zip) ◀┘
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
- **Standardized request contract.** `GenerationRequest`
  ([`generation/base.py`](../../leagent/llm/generation/base.py)) is the typed
  envelope (`kind`, `prompt`, `provider`, `model`, conditioning `image` /
  `controlnet` / `camera`, plus `params`) with `validate()` / `from_params()` /
  `as_params()`, so local pipelines, HTTP services, and SDK providers share one
  shape. Generation kinds: `image` / `video` / `model3d` / **`vfx`**.
- Backends: `ImageProviderBackend` (OpenAI / DashScope image-gen),
  `LocalDiffusionBackend` (in-process diffusers; passes img2img / ControlNet /
  camera conditioning through to the pipeline), `HttpUpscaleBackend` (dedicated
  super-resolution, e.g. Real-ESRGAN), `HttpVideoBackend`, `HttpMesh3DBackend`,
  `HttpVfxBackend` (real providers, env-gated by `LEAGENT_*_URL`), and an
  always-registered **`OfflineGenerationBackend`** that emits minimal-valid
  `png` / `mp4` / `glb` / sprite-sheet bytes deterministically (offline img2img
  blends the reference colour and records `controlnet` / `camera` in meta so
  conditioning is observable credential-free).
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
| `Art.ImageGen` | `IMAGE` | Text-to-image concept / sprite / texture (img2img + camera/ControlNet conditioning) |
| `Art.Upscale` | `IMAGE` | Dedicated super-resolution of a source image (`scale` → `http_upscale`/Real-ESRGAN; offline re-renders at target res) |
| `Art.VideoGen` | `VIDEO` | Text/image-to-video (turntable, idle loop) |
| `Art.Mesh3D` | `MESH3D` | Image/text-to-3D mesh (engine-ready GLB/GLTF/OBJ) |
| `Art.VFXGen` | `IMAGE` | Text-to-VFX flipbook / sprite-sheet (particles, explosion, glow) with animation metadata (frames, grid, fps) |

`provider` / `model` are exposed as `IO.Combo` widgets. The `vfx` kind rides the
`IMAGE` socket (a sprite-sheet *is* an image) so it composes with image
consumers (export, preview, conditioning).

> The legacy `Model.image_gen.*` factory nodes are **deprecated** for the art
> path (audio TTS/ASR still flows through the factory to avoid regressions).

## 4. Control / evaluation nodes (engine-side self-correction)

In [`workflow/nodes/art/`](../../leagent/workflow/nodes/art/) and
[`workflow/nodes/builtin/`](../../leagent/workflow/nodes/builtin/):

- **`Art.QualityCritic`** scores a `MediaRef` perceptually via the multimodal
  LLM (criteria-driven), with a deterministic iteration-heuristic offline
  fallback; it feeds `QualityGateNode.score` and records the score into the
  provider-performance store.
- **`QualityGateNode`** (`control_flow=True`) gates an upstream `MediaRef`,
  writes `state.quality_score`, and routes `pass`/`fail` against a `threshold`.
- **`IterativeRefineNode`** (`control_flow=True`, registered in
  `_LOOP_SAFE_TYPES`) provides a bounded `generate → evaluate → regenerate`
  back-edge: it writes `state.refine_feedback` (folded into the regeneration
  prompt by `BaseGenerationNode`), counts iterations (`max_iterations`), and
  routes to `exhausted_node` once spent, so the validator's cycle DFS does not
  false-fire.
- **`Art.Preview`** is a professional, ComfyUI `PreviewImage`-style artifact
  preview node ([`preview.py`](../../leagent/workflow/nodes/builtin/preview.py)).
  It accepts **any** media artifact (`IMAGE` / `VIDEO` / `MESH3D` / `AUDIO`) by
  reference, emits a `NodeOutput.ui.gen_ui` preview plus structured metadata
  (filename, dimensions, MIME, file size, download URL), and **passes the asset
  straight through** on a wildcard output so it can sit *between* a
  generator/processor and a downstream consumer (e.g. `AssetExportNode`) without
  breaking the chain. The frontend renders it as a rich artifact card
  (`NodeArtifactPreview`, large variant) with an authenticated download button;
  the same card (compact variant) now enriches the inline preview on the
  generation / image-processing nodes themselves.
- **`AssetExportNode`** packages IMAGE/VIDEO/MESH3D/VFX into a **real
  downloadable `.zip` bundle** via the file layer (returned by reference), laid
  out for the chosen engine profile (`generic` / `unity` / `unreal` / `godot`)
  with per-asset import-metadata sidecars (Unity `.meta`, Unreal import JSON,
  Godot `.import`) and 3D format-conversion hints — see
  [`export_profiles.py`](../../leagent/workflow/nodes/builtin/export_profiles.py).
  It also writes a manifest to state and emits a GenUI gallery.

## 5. GenUI rendering

The art nodes are real producers of `NodeOutput.ui.gen_ui`. The GenUI schema
([`services/gen_ui/schema.py`](../../leagent/services/gen_ui/schema.py)) adds
`Video` and `Model3D` (GLB viewer) component kinds, rendered by the frontend
registry (`GenUiVideo`, `GenUiModel3D`). On the canvas, finished generation
nodes render an inline ComfyUI-style media thumbnail (`NodeMediaPreview`) plus
**quality / refine badges** (score, pass/fail, refine iteration, provider,
engine) surfaced from the node's `executed` metadata, and the run panel groups
all emitted assets into a dedicated **Assets** gallery. In chat, generated 3D
meshes render inline via `ChatInlineModel3D` (no download-card fallback).

## 6. Agent self-correction loop

- **`workflow_save`** ([`tools/workflow/workflow_save.py`](../../leagent/tools/workflow/workflow_save.py))
  validates an agent-authored graph against the canonical document (engine
  schema) and persists it as a runnable `Flow`, returning `flow_id` + a stable
  digest. Combined with `chat_workflow_embed_emit` (canvas preview) and
  `workflow_run` / `workflow_status`, this closes the
  **idea → design → run → evaluate → re-run** loop.
- `workflow_run` now returns `success=False` when a run finishes below the
  quality bar (reading `quality_passed` / `quality_score` / `quality_threshold`
  from the gate), so the agent can revise + re-run **within the same turn**
  (bounded), not just on the next turn.
- The `ArtifactErrorTracker`
  ([`context/artifact_error_tracker.py`](../../leagent/context/artifact_error_tracker.py))
  is workflow-run aware: a run that fails *or* finishes below the quality bar
  (`quality_passed` false, or `quality_score < threshold`) is marked dirty,
  injecting a high-priority regeneration directive into the next turn's system
  prompt so the agent revises the graph and re-runs until the bar is met.

## 6b. Engine scheduling, self-optimization & planning

- **Scheduling** ([`workflow/engine/`](../../leagent/workflow/engine/)): the
  executor stages *batches* of ready nodes and runs independent branches
  concurrently under a `max_parallelism` semaphore (branch routing applied
  serially to keep `ExecutionList` mutations safe); `ParallelNode` fans out via
  `WorkflowExecutor.execute_single_node_async` on forked state and merges back.
  `NodeRunner` enforces a centralized transient-error retry/backoff policy
  (`control.max_retries` / `retry_delay_sec`), runtime `Input.validate()`, and
  the executor enforces `control.timeout_sec`.
- **Metrics → memory → provider bias** (Phase 5): the executor emits the
  workflow Prometheus counters plus `workflow_quality_score` /
  `workflow_refine_iterations` histograms; completed art runs persist
  `quality_score` / graph digest / refine count into **procedure memory**; the
  `ProviderStatsStore` ([`llm/capabilities/provider_stats.py`](../../leagent/llm/capabilities/provider_stats.py))
  records success-rate / latency / quality per provider and biases
  `CapabilityRouter` ranking *within each cost tier* (a simple bandit).
- **Art planning playbook** (Phase 7): the
  [`prompts/art_playbook.py`](../../leagent/prompts/art_playbook.py) layer
  surfaces the art ontology, a *graph-aware* node catalog (introspected from the
  live registry), the `TPL-ART-01` pattern, and the required tool sequence via
  the `art_playbook` context source (auto-gated by request heuristics).
  `plan_art_tasks()` decomposes a brief into an ordered `todo_write` step list.

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
  (incl. the `Art.VFXGen` cases) and the media-socket cases in
  [`tests/workflow/test_object_info_contract.py`](../../../backend/tests/workflow/test_object_info_contract.py).
- Engine hardening: [`tests/workflow/test_engine_parallel.py`](../../../backend/tests/workflow/test_engine_parallel.py)
  (parallel branches, retry/backoff, timeout, `ParallelNode` fan-out/merge).
- Self-correction: [`tests/workflow/test_self_correction.py`](../../../backend/tests/workflow/test_self_correction.py)
  (quality critic, feedback-conditioned refine, below-bar `success=False`).
- Multimodal depth: [`tests/llm/test_generation_multimodal.py`](../../../backend/tests/llm/test_generation_multimodal.py)
  (VFX modality, `GenerationRequest` contract, img2img/ControlNet, upscale hooks).
- Export bundles: [`tests/workflow/test_asset_export.py`](../../../backend/tests/workflow/test_asset_export.py)
  (engine-profile `.zip` bundles + import metadata + conversion hints).
- Provider self-optimization: [`tests/llm/test_provider_stats.py`](../../../backend/tests/llm/test_provider_stats.py).
- Art planning: [`tests/eval/test_art_playbook.py`](../../../backend/tests/eval/test_art_playbook.py).
