# 六、Planning

## 6.1 Agent 为什么需要 Planning？

复杂任务包含多个目标、依赖和约束，直接逐步反应容易遗漏步骤、重复执行或过早采取不可逆操作。Planning 将目标拆成可检查的中间状态，显式安排依赖、工具和完成条件，并为失败后的调整提供基线。

LeAgent 的主路径是 `run_loop → QueryEngine` 的统一 think-act 循环，模型可用 `todo_write` 把会话计划持久化为 todo；独立 `TaskPlanner`/Plan-Execute 路径仍保留，但已标记 deprecated，新代码应走 Agent SDK 的统一 runtime。

## 6.2 Task Decomposition 是什么？

Task Decomposition 是把高层目标拆成可执行、可验证、边界清晰的子任务。好的分解要标明输入、输出、依赖、所需工具和完成标准；子任务应足够原子，但不能细到管理成本超过执行收益。

LeAgent 的旧 `TaskPlanner` 可生成最多 10 个带 `id`、`description`、`tool`、`params`、`depends_on` 的步骤，并用拓扑调度找出可并行组。当前主循环更常通过 `todo_write` 维护 `pending/in_progress/completed/cancelled` 状态，其中最多一个 todo 为 `in_progress`。

## 6.3 Plan-and-Execute 是什么？

Plan-and-Execute 先由 Planner 生成完整或阶段性计划，再由 Executor 按依赖执行；执行结果可触发 replan。它适合依赖明确、步骤多、需要审计的任务，但初始规划增加一次模型调用，且计划可能在环境变化后迅速过时。

LeAgent 的兼容 `TaskPlanner` 能产出 `ExecutionPlan`、调度 ready steps，并在步骤失败时仅生成“剩余调整步骤”再合并，避免重复已完成步骤；该路径不是当前推荐的 canonical runtime。

## 6.4 ReAct 和 Plan-and-Execute 的区别？

ReAct 交替进行 Reasoning 与 Action：每拿到一个观察结果就决定下一步，适应性强，但全局一致性较弱。Plan-and-Execute 先形成计划再执行，全局结构和可审计性更好，但前置成本高、容易受错误初始假设影响。

LeAgent 当前 `QueryEngine` 更接近受限 ReAct/think-act：模型在多轮工具调用中依据新观察继续行动，并受最大轮数和每轮工具调用数约束。`todo_write` 可为这条动态循环补充显式全局进度，因此实际系统常采用两者混合。

## 6.5 Tree of Thoughts 是什么？

Tree of Thoughts（ToT）让模型在每个阶段提出多个候选思路，评估后进行搜索、回溯或剪枝，而不是沿单一路径生成。它可配合 BFS、DFS 或 beam search，适合组合搜索和答案可评价的问题，但调用成本高，评价器偏差也会系统性误导搜索。

LeAgent 当前没有通用 ToT 搜索器；工作流 DAG、并行工具调用或多个 sub-agent 也不自动等于 ToT，因为它们没有统一实现“候选 thought 生成—评分—回溯”的搜索协议。

## 6.6 为什么 Planning 会失败？

常见原因包括：目标或约束理解错误；工具能力、参数或权限建模不准；依赖缺失、循环或粒度失衡；忽略外部状态变化；中间结果未验证；失败后仍机械执行旧计划；计划文本正确但无法落到真实动作。

LeAgent 的旧 Planner 会过滤 disabled tool、记录未知工具和无效依赖，并支持失败后 replan，但 `_validate_plan` 对坏依赖主要是日志告警，不会自动修复。主 `QueryEngine` 还需依靠工具结果、自纠错和步数上限避免无限循环。

## 6.7 如何评估 Plan 质量？

离线可评估目标覆盖率、步骤可执行率、依赖正确率、工具/参数有效率、冗余度和关键风险前置率；在线则看任务成功率、重规划次数、失败恢复率、总工具调用、延迟与成本。不能只让 LLM 给计划“打分”，应执行计划并比较结果。

对 LeAgent 还应检查：todo 状态是否与真实执行一致、是否调用禁用工具、是否超过 QueryEngine 预算、独立步骤是否安全并发，以及 procedural recall 是否确实提高后续成功率。

## 6.8 Planner 和 Executor 是否分离？

逻辑上应分离职责：Planner 负责目标分解和依赖，Executor 负责权限校验、参数验证、重试、超时和状态更新。物理上不一定是两个服务；紧耦合的 think-act 循环响应更快，而显式分层更易审计和替换。关键是 Executor 不能无条件信任 Planner。

LeAgent 当前 canonical 路径由同一 `QueryEngine` think-act 循环完成动态决策与工具执行编排，工具层仍独立执行校验和安全控制。旧 `TaskPlanner` 与执行控制器是显式分离的 Plan-Execute 设计，但已弃用；因此不能笼统说 LeAgent 当前采用独立 Planner 服务。

## 6.9 动态规划如何实现？

Agent 面试语境中的“动态规划”通常指动态重规划（dynamic replanning），不是算法课里的动态规划（Dynamic Programming，DP）。前者根据新观察更新剩余计划；后者要求可复用的重叠子问题和最优子结构，通过状态转移求全局最优，两者概念不同。

动态重规划可维护“目标、已完成步骤、当前状态、失败原因、剩余依赖”，在每次关键观察后判断继续、重试、跳过或生成替代步骤；必须保留已完成副作用，避免重复执行。LeAgent 旧 `TaskPlanner.replan` 只要求模型返回剩余工作，过滤已完成 ID，再由 `merge_replan` 保留完成项、跳过被替代项并加入新步骤。当前 `QueryEngine` 则在每次工具观察后自然决定下一动作，`todo_write` 可同步更新外显计划。

## 6.10 Reflection 如何优化 Plan？

Reflection 在阶段完成或失败后，将“预期—实际—差异—原因—改进”结构化，再据此调整步骤、工具参数、验证点或停止条件。有效 Reflection 必须引用执行证据，并由后续结果验证；无证据的自我批评可能只增加 token，甚至固化错误归因。

LeAgent 可把成功工具链及其结果写入 Procedural Memory，召回时按成功率和运行次数重排，旧 `TaskPlanner` 也能把相关 Memory 放入规划提示；艺术流程还记录质量与 refine 结果。这为经验驱动的改进提供基础，但仓库尚无通用的“自动反思生成 → 验证 → 重写计划”完整组件。
