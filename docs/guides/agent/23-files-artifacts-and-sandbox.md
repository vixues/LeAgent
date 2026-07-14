# 23. 文件、产物与沙箱边界

## 定位与先修

Agent 一旦能读写路径，安全模型就从“提示词礼貌”变成“路径证明”。本文区分三条常常被口头混称“沙箱”的机制：**文件系统 PathSandbox**、**代码执行 SubprocessSandbox**、**受管文件 FileService / FileRef**。先修：[20](20-build-a-base-tool.md)。请阅读 `backend/leagent/file/sandbox.py`、`file/primitives.py`、`code/sandbox.py`，以及 `BaseTool.path_params` / `_enforce_path_sandbox`。若你只记住一句话：模型给出的字符串永远不是可信路径，只有经过 `resolve_safe` 并落入允许根的绝对路径才是。

## 学习目标

说明相对名、附件别名如何变成绝对路径；`LEAGENT_TOOL_FILE_ROOTS` 与会话/附件/`authorized_roots` 如何共同组成允许集合；为何产物应走 `FileService.register`；理解代码沙箱“每次新进程 + 超时击杀”但**不承诺**与宿主同等隔离级别的容器安全；并知道工具作者应如何声明路径字段以免绕过 `run()` 执法。

## 心智模型：三道不同强度的墙

```text
1) PathSandbox.resolve_safe
   友好引用（裸文件名 / @file: / @knowledge: / 附件 ID）
     → 绝对路径
     → is_path_inside 证明落入：全局根 ∪ 会话根 ∪ 附件/项目/授权根

2) FileService.register
   字节 → FileRef / storage_key → 预览与下载
   （受管产物单一入口，避免散落临时文件）

3) SubprocessSandbox（code 层）
   每调用新 Python 子进程，超时 SIGKILL 进程组
   权限≈宿主（文档写明无 rlimit / 命名空间承诺）
```

第 1 道防穿越与误读系统文件；第 2 道防“工具私自落盘导致不可治理”；第 3 道防解释器状态泄漏与挂死。把三者当成同一“沙箱开关”，会在桌面模式默认根较宽时产生虚假安全感。

## 真实实现

`BaseTool.run()` 在 Schema 通过后调用 `_enforce_path_sandbox`：对 `path_params` 只读解析（`allow_create=False`），对 `output_path_params` 允许在沙箱内创建。解析成功会**原地改写** params，使 `execute` 直接打开绝对路径，避免工具内再次猜测 cwd。

`PathSandbox.resolve_safe` 先处理 `@file:` / `@knowledge:` 与附件查找表，再组装允许根：环境变量配置的根、上传目录、知识库目录、会话输出目录、`project_roots`、`authorized_roots`。根归属检查统一走 `leagent.file.primitives.is_path_inside`（仓库不变量），禁止各自用 `relative_to` 拼装造成旁路。

代码层 `SubprocessSandbox` 通过 `python -m leagent.code.runner` 与 JSON 信封通信。它适合“干净解释器 + 墙钟超时”，但**不是**完整安全沙箱；高风险能力仍依赖工具是否暴露、permission 审批、以及工作目录是否落在项目允许范围。桌面部署默认根可能更宽，但决策链仍是同一套 allow-list。

产出路径上，AGENTS.md 约定：受管 blob 经 `FileService.register` 或 `register_tool_artifact`；不要写临时文件再“碰巧被 UI 扫到”。

## 示例：声明路径并登记产物

```python
class ReadNotesTool(BaseTool):
    name = "read_notes"
    path_params = ("path",)
    is_read_only = True

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Note path or @file: name"},
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def execute(self, params, context):
        text = Path(params["path"]).read_text(encoding="utf-8")
        return {"text": text[:5000]}
```

```python
ref = await context.file_service.register(
    data_bytes,
    filename="report.md",
    scope=FileScope.OUTPUT,
    session_id=context.session_id,
)
return {"path": ref.storage_key}
```

对嵌套路径（如 `files[].path`）需覆盖 `_enforce_path_sandbox`，不要以为只声明顶层键就够。

## 验证命令

```bash
cd backend
uv run pytest tests/test_file/test_invariants.py -q
uv run pytest tests/test_file -q --maxfail=5
```

手工验证：带 `path_params` 的工具面对 `../../etc/passwd` 或越出根的绝对路径时，应得到权限错误风格失败，而不是文件内容。代码执行工具则验证超时杀进程，而不是假设其无法读环境变量。

## 常见误区

1. **以为 description 写“不要读系统文件”就够。** 必须靠 PathSandbox。
2. **代码沙箱 = 安全沙箱。** 当前是进程与超时边界，不是强隔离。
3. **工具自己 resolve 却不声明 path_params。** 会绕过 `run()` 统一执法。
4. **写临时文件指望前端发现。** 受管产物走 register。
5. **桌面根更宽等于无限制。** 仍是 allow-list，只是集合更大。
6. **用 `os.path.commonpath` 自制检查。** 应使用 `is_path_inside`，避免符号链接与边界错误。

## 业内对照

Codex / Claude Code 强调 workspace 根与审批；纯浏览器 Agent 常完全禁止本地 FS。LangChain 文件工具若未加根约束极易穿越。云端容器方案用 namespace/seccomp 提供更强隔离，但桌面本地 Agent 往往做不到同等深度。LeAgent 选择“可配置根 + 附件权威 + FileRef 产物 + 代码子进程超时”，在生产力与可控性之间取折中，并把更强隔离留给可选部署形态。

## 部署差异提醒

桌面模式与服务器模式共用同一套 `PathSandbox` 决策链，但默认允许根集合不同。未设置 `LEAGENT_TOOL_FILE_ROOTS` 时，本地部署往往会包含更宽的用户工作区相关根，方便打开附件与项目文件；多租户服务器则应显式收紧根、强化鉴权与审批。无论哪种部署，工具作者都不应假设“当前工作目录随便写”。会话输出目录、附件权威列表与项目根是临时放宽通道，不是永久特权。代码执行层即使每次新开解释器，也仍可能读到与宿主相同的环境变量与凭据：因此暴露给模型的代码执行工具，更要配合权限策略与人工确认。评审涉及文件与代码的变更时，请同时问路径如何证明、产物如何登记、执行如何超时，三问缺一都算未完成。

## 总结

文件安全三件套：路径证明、产物登记、代码进程边界。扩展工具时声明 `path_params`，产出走 `register`，并清醒认识 PathSandbox 与 SubprocessSandbox 强度不同。任何“模型说路径安全”的语句都不能替代 `resolve_safe` 的返回值。
