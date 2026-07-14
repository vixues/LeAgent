# 自定义模型与自定义节点

LeAgent 的工作流系统遵循 ComfyUI 的上手模式：注册一个**领域模型适配器**会自动在工作流面板中生成类型化的 `Model.<task>.<provider>` 节点；注册一个**工作流节点**类会将其加入 `/object_info`，无需改前端。本指南涵盖上述两条路径，以及自托管模型（diffusers、本地 Whisper/TTS）的配置。

英文版：[custom-models.md](./custom-models.md)

## 1. 领域模型适配器

*领域模型*指任何非聊天的任务专用能力：图像生成、TTS、ASR，以及未来的 video/upscaling。适配器实现 `leagent.llm.domain_registry` 中的 `DomainModelAdapter` 协议：

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

`DomainParam.io_type` 映射到工作流 socket 类型：`STRING`（设 `multiline=True` 为 textarea）、`INT`/`FLOAT`（带 `min`/`max` 滑块范围）、`BOOLEAN`、`COMBO`（带 `choices`）、`FILE`、`OBJECT`。

每个适配器节点的返回值均为统一的 5 槽 envelope：`(text, data_b64, mime, result, success)`。

### 注册

**编程式**（内置于你的 app/bootstrap）：

```python
from leagent.llm.domain_registry import get_domain_registry

get_domain_registry().register(MyUpscaleAdapter())
```

**Entry point**（第三方包——在工作流 bootstrap 时自动发现）：

```toml
# pyproject.toml of your plugin distribution
[project.entry-points."leagent.domain_models"]
my_upscale = "my_pkg.adapters:MyUpscaleAdapter"
```

目标可以是适配器实例、无参适配器类，或无参工厂返回的实例。注册后，节点会出现在编辑器面板的 `models/<task>` 下，带颜色编码的 socket 与内联 widget——无需编写节点或前端代码。

### 在工作流外调用

```python
from leagent.llm.domain_registry import get_domain_registry

result = await get_domain_registry().invoke_task("tts", provider="local", text="hi")
```

## 2. 自托管 diffusion（SD / SDXL + LoRA）

通过 HuggingFace `diffusers` 进行进程内图像生成，以 `Model.image_gen.local` 节点暴露，画布上显示逐步进度。

**安装**可选依赖组（较重：torch + diffusers）：

```bash
cd backend
uv sync --extra diffusion
```

**目录结构**（由你创建；注册时扫描）：

```
~/.leagent/models/
├── diffusion/          # checkpoints: *.safetensors / *.ckpt (subdirs ok)
│   ├── dreamshaperXL.safetensors
│   └── sd15/anything-v5.ckpt
└── lora/               # LoRA adapters: *.safetensors
    └── detail-tweaker.safetensors
```

名称含 `xl`/`sdxl` 的 checkpoint 路由到 `StableDiffusionXLPipeline`；其余使用 `StableDiffusionPipeline`。HuggingFace hub id 也可用（例如 `stabilityai/stable-diffusion-xl-base-1.0`）。

**环境变量：**

| 变量 | 默认值 | 用途 |
|---|---|---|
| `LEAGENT_DIFFUSION_ENABLED` | `1` | 设为 `0` 可在已安装时仍跳过注册 |
| `LEAGENT_DIFFUSION_MODELS_DIR` | `~/.leagent/models/diffusion` | Checkpoint 扫描目录 |
| `LEAGENT_DIFFUSION_LORA_DIR` | `~/.leagent/models/lora` | LoRA 扫描目录 |
| `LEAGENT_DIFFUSION_DEFAULT_MODEL` | `stabilityai/stable-diffusion-xl-base-1.0` | 回退 hub id |
| `LEAGENT_DIFFUSION_DEVICE` | auto (cuda → mps → cpu) | 强制指定设备 |

节点参数：`prompt`、`model`（COMBO，来自发现结果）、`negative_prompt`、`width`/`height`、`steps`、`cfg_scale`、`seed`（−1 = 随机）、`scheduler`（`euler_a`、`euler`、`dpmpp_2m`、`dpmpp_2m_karras`、`ddim`、`unipc`）、`lora`（COMBO，来自 LoRA 目录 + `none`）、`lora_scale`。

Pipeline 管理器保持单一模型驻留，切换时释放 VRAM，并在锁后串行化生成。示例工作流：[`config/demo-workflows/demo-local-sdxl-txt2img.yaml`](../../config/demo-workflows/demo-local-sdxl-txt2img.yaml)。

## 3. 自托管音频（Whisper ASR + 本地 TTS）

两个适配器均使用 OpenAI 兼容音频 API，因此任何符合规范的本地服务均可使用：

| 节点 | 服务 | 环境变量 |
|---|---|---|
| `Model.asr.local` | faster-whisper-server、whisper.cpp、Speaches | `LEAGENT_LOCAL_ASR_URL`（+ `LEAGENT_LOCAL_ASR_MODEL`） |
| `Model.tts.local` | openedai-speech、Kokoro-FastAPI | `LEAGENT_LOCAL_TTS_URL`（+ `LEAGENT_LOCAL_TTS_MODEL`） |

若服务需要 token，可设置共享的 `LEAGENT_LOCAL_AUDIO_API_KEY`。URL 可以是服务根路径或包含 `/v1`。设置 URL 即注册节点——未设置则节点不会出现。

示例工作流：[`demo-local-tts.yaml`](../../config/demo-workflows/demo-local-tts.yaml)、[`demo-asr-agent-summary.yaml`](../../config/demo-workflows/demo-asr-agent-summary.yaml)。

## 4. 自定义工作流节点

对于不适合领域模型 envelope 的逻辑，直接实现 `WorkflowNode`：

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

从 node loader 会导入的模块中注册（内置节点位于 `leagent/workflow/nodes/builtin/`），或通过 `leagent.workflow.nodes` entry-point 组发布。Schema 经 `/object_info` 提供，编辑器自动渲染类型化 socket、颜色与 widget。

长时间运行的节点可通过 `hidden.progress.update(value=..., max=..., node_id=hidden.unique_id)` 流式上报进度，并应尊重 `hidden.abort_event` 以支持取消。

## 5. 工作流中的 Agent 暂停 / 恢复

Agent 节点（`ScriptAgentNode`、`CodingAgentNode`、生成的 `Agent.<name>` 节点）在 Agent 向用户提问（`awaiting_user_input`）时会暂停运行：保存 kernel checkpoint，画布显示 Resume 面板，`POST /api/v1/workflow/prompts/{prompt_id}/resume` 从 checkpoint 继续同一 Agent 轮次。详见 [`demo-agent-pause-resume.yaml`](../../config/demo-workflows/demo-agent-pause-resume.yaml) 与 [agent_sdk_zh.md](agent_sdk_zh.md) 中的 checkpoint store 说明。
