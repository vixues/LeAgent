# Custom Models & Custom Nodes

LeAgent's workflow system follows the ComfyUI onboarding model: registering a
**domain-model adapter** automatically produces a typed `Model.<task>.<provider>`
node in the workflow palette, and registering a **workflow node** class adds it
to `/object_info` with no frontend changes. This guide covers both paths plus
the self-hosted model setup (diffusers, local Whisper/TTS).

中文版: [`custom-models_zh.md`](./custom-models_zh.md)

## 1. Domain-model adapters

A *domain model* is any task-specific capability that isn't chat: image
generation, TTS, ASR, future video/upscaling. Adapters implement the
`DomainModelAdapter` protocol from `leagent.llm.domain_registry`:

```python
from leagent.llm.domain_registry import (
    DomainModelResult,
    DomainModelSpec,
    DomainParam,
)


class MyUpscaleAdapter:
    """Template: a custom domain-model adapter."""

    spec = DomainModelSpec(
        task="upscale",            # logical task id
        provider="myvendor",       # provider id -> node is Model.upscale.myvendor
        model="upscaler-v2",
        display_name="Image Upscale (MyVendor)",
        description="4x upscale via the MyVendor API.",
        params=(
            # Every param becomes a typed node input automatically.
            DomainParam(id="image_b64", io_type="STRING", required=True,
                        tooltip="Base64 input image"),
            DomainParam(id="scale", io_type="COMBO", choices=("2", "4"),
                        default="4", tooltip="Upscale factor"),
            DomainParam(id="denoise", io_type="FLOAT", default=0.5,
                        min=0.0, max=1.0),
        ),
        output="image",            # primary output modality: text/audio/image
        supports_progress=False,   # True -> receive a `_progress(step, total)` kwarg
    )

    async def invoke(self, **params) -> DomainModelResult:
        ...
        return DomainModelResult(
            b64_data=result_png_b64,
            mime="image/png",
            model=self.spec.model,
            provider=self.spec.provider,
            metadata={"scale": params.get("scale")},
        )
```

`DomainParam.io_type` maps onto workflow socket types: `STRING` (set
`multiline=True` for a textarea), `INT`/`FLOAT` (with `min`/`max` slider
bounds), `BOOLEAN`, `COMBO` (with `choices`), `FILE`, `OBJECT`.

Every adapter's node returns the uniform 5-slot envelope:
`(text, data_b64, mime, result, success)`.

### Registering

**Programmatic** (built into your app/bootstrap):

```python
from leagent.llm.domain_registry import get_domain_registry

get_domain_registry().register(MyUpscaleAdapter())
```

**Entry point** (third-party package — auto-discovered at workflow bootstrap):

```toml
# pyproject.toml of your plugin distribution
[project.entry-points."leagent.domain_models"]
my_upscale = "my_pkg.adapters:MyUpscaleAdapter"
```

The target may be an adapter instance, a zero-arg adapter class, or a zero-arg
factory returning one. Once registered, the node appears in the editor palette
under `models/<task>` with colour-coded sockets and inline widgets — no node
or frontend code required.

### Invoking outside workflows

```python
from leagent.llm.domain_registry import get_domain_registry

result = await get_domain_registry().invoke_task("tts", provider="local", text="hi")
```

## 2. Self-hosted diffusion (SD / SDXL + LoRA)

In-process image generation through HuggingFace `diffusers`, exposed as the
`Model.image_gen.local` node with per-step progress on the canvas.

**Install** the optional dependency group (heavy: torch + diffusers):

```bash
cd backend
uv sync --extra diffusion
```

**Directory layout** (created by you; scanned at registration):

```
~/.leagent/models/
├── diffusion/          # checkpoints: *.safetensors / *.ckpt (subdirs ok)
│   ├── dreamshaperXL.safetensors
│   └── sd15/anything-v5.ckpt
└── lora/               # LoRA adapters: *.safetensors
    └── detail-tweaker.safetensors
```

Checkpoints containing `xl`/`sdxl` in the name route to
`StableDiffusionXLPipeline`; everything else uses `StableDiffusionPipeline`.
HuggingFace hub ids also work (e.g. `stabilityai/stable-diffusion-xl-base-1.0`).

**Environment variables:**

| Variable | Default | Purpose |
|---|---|---|
| `LEAGENT_DIFFUSION_ENABLED` | `1` | Set `0` to skip registration even when installed |
| `LEAGENT_DIFFUSION_MODELS_DIR` | `~/.leagent/models/diffusion` | Checkpoint scan dir |
| `LEAGENT_DIFFUSION_LORA_DIR` | `~/.leagent/models/lora` | LoRA scan dir |
| `LEAGENT_DIFFUSION_DEFAULT_MODEL` | `stabilityai/stable-diffusion-xl-base-1.0` | Fallback hub id |
| `LEAGENT_DIFFUSION_DEVICE` | auto (cuda → mps → cpu) | Force a device |

Node parameters: `prompt`, `model` (COMBO from discovery), `negative_prompt`,
`width`/`height`, `steps`, `cfg_scale`, `seed` (−1 = random), `scheduler`
(`euler_a`, `euler`, `dpmpp_2m`, `dpmpp_2m_karras`, `ddim`, `unipc`), `lora`
(COMBO from the LoRA dir + `none`), `lora_scale`.

The pipeline manager keeps one model resident, frees VRAM on switches, and
serialises generations behind a lock. Example workflow:
[`config/demo-workflows/demo-local-sdxl-txt2img.yaml`](../../config/demo-workflows/demo-local-sdxl-txt2img.yaml).

## 3. Self-hosted audio (Whisper ASR + local TTS)

Both adapters speak the OpenAI-compatible audio API, so any conforming local
server works:

| Node | Servers | Env |
|---|---|---|
| `Model.asr.local` | faster-whisper-server, whisper.cpp, Speaches | `LEAGENT_LOCAL_ASR_URL` (+ `LEAGENT_LOCAL_ASR_MODEL`) |
| `Model.tts.local` | openedai-speech, Kokoro-FastAPI | `LEAGENT_LOCAL_TTS_URL` (+ `LEAGENT_LOCAL_TTS_MODEL`) |

Optional shared `LEAGENT_LOCAL_AUDIO_API_KEY` if your server requires a token.
URLs may be the server root or include `/v1`. Setting the URL is what
registers the node — unset means the node simply doesn't appear.

Example workflows:
[`demo-local-tts.yaml`](../../config/demo-workflows/demo-local-tts.yaml),
[`demo-asr-agent-summary.yaml`](../../config/demo-workflows/demo-asr-agent-summary.yaml).

## 4. Custom workflow nodes

For logic that doesn't fit the domain-model envelope, implement a
`WorkflowNode` directly:

```python
from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode


class WordCountNode(WorkflowNode):
    """Template: a custom workflow node."""

    NODE_ID = "WordCountNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="WordCountNode",
            display_name="Word Count",
            category="custom/text",
            description="Count words in a text input.",
            inputs=[
                IO.String.Input(id="text", multiline=True),
                IO.Boolean.Input(id="unique_only", optional=True, default=False),
            ],
            outputs=[
                IO.Int.Output(id="count"),
                IO.String.Output(id="summary"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs) -> NodeOutput:
        words = str(inputs.get("text") or "").split()
        if inputs.get("unique_only"):
            words = list(dict.fromkeys(words))
        return NodeOutput(values=(len(words), f"{len(words)} words"))
```

Register it from a module the node loader imports (built-ins live in
`leagent/workflow/nodes/builtin/`), or ship it via the
`leagent.workflow.nodes` entry-point group. The schema is served through
`/object_info`, so the editor renders typed sockets, colours, and widgets
automatically.

Long-running nodes can stream progress with
`hidden.progress.update(value=..., max=..., node_id=hidden.unique_id)` and
should honour `hidden.abort_event` for cancellation.

## 5. Agent pause / resume in workflows

Agent-backed nodes (`ScriptAgentNode`, `CodingAgentNode`, generated
`Agent.<name>` nodes) pause the run when the agent asks the user a question
(`awaiting_user_input`): a kernel checkpoint is saved, the canvas shows the
Resume panel, and `POST /api/v1/workflow/prompts/{prompt_id}/resume` continues
the same agent turn from the checkpoint. See
[`demo-agent-pause-resume.yaml`](../../config/demo-workflows/demo-agent-pause-resume.yaml)
and [agent_sdk.md](agent_sdk.md) for the checkpoint store details.
