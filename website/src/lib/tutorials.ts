export type TutorialSectionId =
  | "intro"
  | "interview"
  | "agent"
  | "technical";

export interface LocalizedText {
  "zh-CN": string;
  "en-US": string;
}

export interface TutorialArticleMeta {
  slug: string;
  title: LocalizedText;
  /** When true, en-US still shows zh body with a notice. */
  zhOnly?: boolean;
}

export interface TutorialSectionMeta {
  id: TutorialSectionId;
  path: string;
  title: LocalizedText;
  description: LocalizedText;
  articles: TutorialArticleMeta[];
}

const interviewArticles: TutorialArticleMeta[] = [
  {
    slug: "index",
    title: {
      "zh-CN": "目录概览",
      "en-US": "Overview",
    },
    zhOnly: true,
  },
  {
    slug: "01-agent-basics",
    title: {
      "zh-CN": "Agent 基础概念",
      "en-US": "Agent Basics",
    },
    zhOnly: true,
  },
  {
    slug: "02-prompt-engineering",
    title: {
      "zh-CN": "Prompt Engineering",
      "en-US": "Prompt Engineering",
    },
    zhOnly: true,
  },
  {
    slug: "03-tool-calling",
    title: {
      "zh-CN": "Tool Calling",
      "en-US": "Tool Calling",
    },
    zhOnly: true,
  },
  {
    slug: "04-rag",
    title: { "zh-CN": "RAG", "en-US": "RAG" },
    zhOnly: true,
  },
  {
    slug: "05-memory",
    title: { "zh-CN": "Memory", "en-US": "Memory" },
    zhOnly: true,
  },
  {
    slug: "06-planning",
    title: { "zh-CN": "Planning", "en-US": "Planning" },
    zhOnly: true,
  },
  {
    slug: "07-multi-agent",
    title: { "zh-CN": "Multi-Agent", "en-US": "Multi-Agent" },
    zhOnly: true,
  },
  {
    slug: "08-agent-frameworks",
    title: {
      "zh-CN": "Agent Frameworks",
      "en-US": "Agent Frameworks",
    },
    zhOnly: true,
  },
  {
    slug: "09-system-design",
    title: {
      "zh-CN": "Agent 系统设计",
      "en-US": "Agent System Design",
    },
    zhOnly: true,
  },
  {
    slug: "10-evaluation",
    title: {
      "zh-CN": "Agent Evaluation",
      "en-US": "Agent Evaluation",
    },
    zhOnly: true,
  },
  {
    slug: "11-production",
    title: {
      "zh-CN": "Agent Production",
      "en-US": "Agent Production",
    },
    zhOnly: true,
  },
  {
    slug: "12-security",
    title: { "zh-CN": "安全", "en-US": "Security" },
    zhOnly: true,
  },
  {
    slug: "13-models",
    title: { "zh-CN": "模型层面", "en-US": "Models" },
    zhOnly: true,
  },
  {
    slug: "14-coding",
    title: {
      "zh-CN": "Coding 高频题",
      "en-US": "Coding Interview",
    },
    zhOnly: true,
  },
  {
    slug: "15-deep-dive",
    title: {
      "zh-CN": "大厂高频深挖题",
      "en-US": "Deep Dive Questions",
    },
    zhOnly: true,
  },
];

const agentArticles: TutorialArticleMeta[] = [
  {
    slug: "index",
    title: {
      "zh-CN": "目录概览",
      "en-US": "Overview",
    },
    zhOnly: true,
  },
  {
    slug: "01-agent-vs-chatbot",
    title: {
      "zh-CN": "Agent 与 Chatbot",
      "en-US": "Agent vs Chatbot",
    },
    zhOnly: true,
  },
  {
    slug: "02-think-act-loop",
    title: {
      "zh-CN": "Think–Act Loop",
      "en-US": "Think–Act Loop",
    },
    zhOnly: true,
  },
  {
    slug: "03-one-kernel-many-ingresses",
    title: {
      "zh-CN": "一套 Kernel，多个入口",
      "en-US": "One Kernel, Many Ingresses",
    },
    zhOnly: true,
  },
  {
    slug: "04-agent-event-stream",
    title: {
      "zh-CN": "AgentEvent 流式协议",
      "en-US": "AgentEvent Stream",
    },
    zhOnly: true,
  },
  {
    slug: "05-state-ownership",
    title: {
      "zh-CN": "状态所有权",
      "en-US": "State Ownership",
    },
    zhOnly: true,
  },
  {
    slug: "06-framework-architecture-comparison",
    title: {
      "zh-CN": "框架架构对照",
      "en-US": "Framework Comparison",
    },
    zhOnly: true,
  },
  {
    slug: "07-minimal-python-agent",
    title: {
      "zh-CN": "最小 Python Agent",
      "en-US": "Minimal Python Agent",
    },
    zhOnly: true,
  },
  {
    slug: "08-model-and-streaming",
    title: {
      "zh-CN": "模型与流式输出",
      "en-US": "Model & Streaming",
    },
    zhOnly: true,
  },
  {
    slug: "09-agent-builder",
    title: {
      "zh-CN": "AgentBuilder",
      "en-US": "AgentBuilder",
    },
    zhOnly: true,
  },
  {
    slug: "10-domain-agent-definition",
    title: {
      "zh-CN": "领域 Agent 设计",
      "en-US": "Domain Agent Definition",
    },
    zhOnly: true,
  },
  {
    slug: "11-yaml-agent-registration",
    title: {
      "zh-CN": "YAML 注册 Agent",
      "en-US": "YAML Agent Registration",
    },
    zhOnly: true,
  },
  {
    slug: "12-production-ready-agent",
    title: {
      "zh-CN": "工程化 Agent",
      "en-US": "Production-Ready Agent",
    },
    zhOnly: true,
  },
  {
    slug: "13-layered-prompts",
    title: {
      "zh-CN": "分层提示词",
      "en-US": "Layered Prompts",
    },
    zhOnly: true,
  },
  {
    slug: "14-persona-and-context-recipe",
    title: {
      "zh-CN": "Persona 与 Recipe",
      "en-US": "Persona & Recipe",
    },
    zhOnly: true,
  },
  {
    slug: "15-context-source",
    title: {
      "zh-CN": "Context Source",
      "en-US": "Context Source",
    },
    zhOnly: true,
  },
  {
    slug: "16-context-budget-and-compaction",
    title: {
      "zh-CN": "上下文预算与压缩",
      "en-US": "Context Budget",
    },
    zhOnly: true,
  },
  {
    slug: "17-relevance-gated-prompts",
    title: {
      "zh-CN": "门控提示词",
      "en-US": "Relevance-Gated Prompts",
    },
    zhOnly: true,
  },
  {
    slug: "18-prompt-cache-and-context-hygiene",
    title: {
      "zh-CN": "Prompt Cache 与卫生",
      "en-US": "Prompt Cache",
    },
    zhOnly: true,
  },
  {
    slug: "19-tool-schema-design",
    title: {
      "zh-CN": "工具 Schema 设计",
      "en-US": "Tool Schema Design",
    },
    zhOnly: true,
  },
  {
    slug: "20-build-a-base-tool",
    title: {
      "zh-CN": "实现 BaseTool",
      "en-US": "Build a BaseTool",
    },
    zhOnly: true,
  },
  {
    slug: "21-tool-registry-and-executor",
    title: {
      "zh-CN": "Registry 与 Executor",
      "en-US": "Registry & Executor",
    },
    zhOnly: true,
  },
  {
    slug: "22-tool-concurrency-rate-limit",
    title: {
      "zh-CN": "工具并发与限流",
      "en-US": "Tool Concurrency",
    },
    zhOnly: true,
  },
  {
    slug: "23-files-artifacts-and-sandbox",
    title: {
      "zh-CN": "文件、产物与沙箱",
      "en-US": "Files & Sandbox",
    },
    zhOnly: true,
  },
  {
    slug: "24-mcp-and-tool-poisoning",
    title: {
      "zh-CN": "MCP 与工具投毒",
      "en-US": "MCP & Tool Poisoning",
    },
    zhOnly: true,
  },
  {
    slug: "25-session-identity",
    title: {
      "zh-CN": "Session Identity",
      "en-US": "Session Identity",
    },
    zhOnly: true,
  },
  {
    slug: "26-tiered-session-store",
    title: {
      "zh-CN": "TieredSessionStore",
      "en-US": "Tiered Session Store",
    },
    zhOnly: true,
  },
  {
    slug: "27-message-lifecycle",
    title: {
      "zh-CN": "消息生命周期",
      "en-US": "Message Lifecycle",
    },
    zhOnly: true,
  },
  {
    slug: "28-history-compaction",
    title: {
      "zh-CN": "历史压缩",
      "en-US": "History Compaction",
    },
    zhOnly: true,
  },
  {
    slug: "29-cross-session-conversation-history",
    title: {
      "zh-CN": "跨会话历史",
      "en-US": "Cross-Session History",
    },
    zhOnly: true,
  },
  {
    slug: "30-checkpoint-pause-resume",
    title: {
      "zh-CN": "Checkpoint 暂停恢复",
      "en-US": "Checkpoint Pause/Resume",
    },
    zhOnly: true,
  },
  {
    slug: "31-memory-boundaries",
    title: {
      "zh-CN": "记忆边界",
      "en-US": "Memory Boundaries",
    },
    zhOnly: true,
  },
  {
    slug: "32-three-store-memory",
    title: {
      "zh-CN": "三类记忆",
      "en-US": "Three-Store Memory",
    },
    zhOnly: true,
  },
  {
    slug: "33-memory-formation",
    title: {
      "zh-CN": "Memory Formation",
      "en-US": "Memory Formation",
    },
    zhOnly: true,
  },
  {
    slug: "34-hybrid-recall-reranking",
    title: {
      "zh-CN": "混合召回与重排",
      "en-US": "Hybrid Recall",
    },
    zhOnly: true,
  },
  {
    slug: "35-recall-prefetch-degradation",
    title: {
      "zh-CN": "预取与降级",
      "en-US": "Recall Prefetch",
    },
    zhOnly: true,
  },
  {
    slug: "36-memory-privacy-retention",
    title: {
      "zh-CN": "记忆隐私与保留",
      "en-US": "Memory Privacy",
    },
    zhOnly: true,
  },
  {
    slug: "37-when-to-use-subagents",
    title: {
      "zh-CN": "何时使用子 Agent",
      "en-US": "When to Use Subagents",
    },
    zhOnly: true,
  },
  {
    slug: "38-delegation-context-isolation",
    title: {
      "zh-CN": "委托与上下文隔离",
      "en-US": "Delegation Isolation",
    },
    zhOnly: true,
  },
  {
    slug: "39-scoped-tools-and-handoffs",
    title: {
      "zh-CN": "Scoped Tools 与 Handoff",
      "en-US": "Scoped Tools & Handoffs",
    },
    zhOnly: true,
  },
  {
    slug: "40-supervisor-orchestration",
    title: {
      "zh-CN": "Supervisor 编排",
      "en-US": "Supervisor Orchestration",
    },
    zhOnly: true,
  },
  {
    slug: "41-agent-nodes-and-dag",
    title: {
      "zh-CN": "Agent 节点与 DAG",
      "en-US": "Agent Nodes & DAG",
    },
    zhOnly: true,
  },
  {
    slug: "42-human-in-the-loop-workflows",
    title: {
      "zh-CN": "Human-in-the-loop",
      "en-US": "Human-in-the-Loop",
    },
    zhOnly: true,
  },
  {
    slug: "43-hooks-and-guardrails",
    title: {
      "zh-CN": "Hooks 与 Guardrails",
      "en-US": "Hooks & Guardrails",
    },
    zhOnly: true,
  },
  {
    slug: "44-error-recovery-self-correction",
    title: {
      "zh-CN": "错误恢复与自校正",
      "en-US": "Error Recovery",
    },
    zhOnly: true,
  },
  {
    slug: "45-tracing-and-otel",
    title: {
      "zh-CN": "Trace 与 OpenTelemetry",
      "en-US": "Tracing & OTel",
    },
    zhOnly: true,
  },
  {
    slug: "46-trajectory-evaluation",
    title: {
      "zh-CN": "轨迹评测",
      "en-US": "Trajectory Evaluation",
    },
    zhOnly: true,
  },
  {
    slug: "47-agent-security-control-plane",
    title: {
      "zh-CN": "安全控制面",
      "en-US": "Security Control Plane",
    },
    zhOnly: true,
  },
  {
    slug: "48-production-cost-latency-scaling",
    title: {
      "zh-CN": "成本、延迟与扩展",
      "en-US": "Cost, Latency & Scaling",
    },
    zhOnly: true,
  },
];

const technicalArticles: TutorialArticleMeta[] = [
  {
    slug: "execution-topology",
    title: {
      "zh-CN": "执行拓扑",
      "en-US": "Execution Topology",
    },
  },
  {
    slug: "agent-runtime",
    title: {
      "zh-CN": "Agent Runtime",
      "en-US": "Agent Runtime",
    },
  },
  {
    slug: "agent_sdk",
    title: {
      "zh-CN": "Agent SDK",
      "en-US": "Agent SDK",
    },
  },
  {
    slug: "agent-trace",
    title: {
      "zh-CN": "Agent Trace",
      "en-US": "Agent Trace",
    },
  },
  {
    slug: "security-control-plane",
    title: {
      "zh-CN": "安全控制平面",
      "en-US": "Security Control Plane",
    },
  },
  {
    slug: "tool-parameters",
    title: {
      "zh-CN": "工具参数约定",
      "en-US": "Tool Parameters",
    },
  },
  {
    slug: "custom-models",
    title: {
      "zh-CN": "自定义模型与节点",
      "en-US": "Custom Models & Nodes",
    },
  },
  {
    slug: "agent-systems-survey",
    title: {
      "zh-CN": "Agent 系统调研",
      "en-US": "Agent Systems Survey",
    },
  },
];

export const TUTORIAL_SECTIONS: TutorialSectionMeta[] = [
  {
    id: "intro",
    path: "/tutorials/intro",
    title: {
      "zh-CN": "系统介绍",
      "en-US": "System Overview",
    },
    description: {
      "zh-CN": "从 README 了解 LeAgent 产品能力、架构与快速开始。",
      "en-US":
        "Learn LeAgent capabilities, architecture, and quick start from the README.",
    },
    articles: [
      {
        slug: "overview",
        title: {
          "zh-CN": "LeAgent 系统介绍",
          "en-US": "LeAgent Overview",
        },
      },
    ],
  },
  {
    id: "interview",
    path: "/tutorials/interview",
    title: {
      "zh-CN": "面试教程",
      "en-US": "Interview Prep",
    },
    description: {
      "zh-CN": "以 LeAgent 真实架构为主线的 Agent 面试题库。",
      "en-US":
        "Agent interview Q&A grounded in LeAgent’s real architecture.",
    },
    articles: interviewArticles,
  },
  {
    id: "agent",
    path: "/tutorials/agent",
    title: {
      "zh-CN": "Agent 教程",
      "en-US": "Agent Guides",
    },
    description: {
      "zh-CN": "从架构基础到生产落地的 48 篇 Agent 工程教程。",
      "en-US":
        "48 progressive Agent engineering guides, from basics to production.",
    },
    articles: agentArticles,
  },
  {
    id: "technical",
    path: "/tutorials/technical",
    title: {
      "zh-CN": "技术资料",
      "en-US": "Technical Docs",
    },
    description: {
      "zh-CN": "执行拓扑、SDK、运行时、追踪、安全与工具契约。",
      "en-US":
        "Execution topology, SDK, runtime, tracing, security, and tool contracts.",
    },
    articles: technicalArticles,
  },
];

const interviewRaw = import.meta.glob("../../../docs/interview/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const agentRaw = import.meta.glob("../../../docs/guides/agent/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const technicalRaw = import.meta.glob("../../../docs/technical/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const readmeRaw = import.meta.glob("../../../README*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function fileBasename(path: string): string {
  const parts = path.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] ?? path;
}

function lookupRaw(
  map: Record<string, string>,
  filename: string,
): string | null {
  for (const [path, content] of Object.entries(map)) {
    if (fileBasename(path) === filename) return content;
  }
  return null;
}

export function getSection(
  id: TutorialSectionId,
): TutorialSectionMeta | undefined {
  return TUTORIAL_SECTIONS.find((s) => s.id === id);
}

export function getArticle(
  sectionId: TutorialSectionId,
  slug: string,
): TutorialArticleMeta | undefined {
  return getSection(sectionId)?.articles.find((a) => a.slug === slug);
}

export function articlePath(
  sectionId: TutorialSectionId,
  slug: string,
): string {
  if (sectionId === "intro") return "/tutorials/intro";
  if (slug === "index") return `/tutorials/${sectionId}`;
  return `/tutorials/${sectionId}/${slug}`;
}

export function resolveTutorialMarkdown(
  sectionId: TutorialSectionId,
  slug: string,
  lang: "zh-CN" | "en-US",
): { markdown: string; zhOnlyShown: boolean } | null {
  if (sectionId === "intro") {
    const preferZh = lang === "zh-CN";
    const md =
      lookupRaw(readmeRaw, preferZh ? "README_zh.md" : "README.md") ??
      lookupRaw(readmeRaw, "README_zh.md") ??
      lookupRaw(readmeRaw, "README.md");
    if (!md) return null;
    return { markdown: md, zhOnlyShown: false };
  }

  if (sectionId === "interview" || sectionId === "agent") {
    const map = sectionId === "interview" ? interviewRaw : agentRaw;
    const filename = slug === "index" ? "README.md" : `${slug}.md`;
    const md = lookupRaw(map, filename);
    if (!md) return null;
    return { markdown: md, zhOnlyShown: lang === "en-US" };
  }

  if (sectionId === "technical") {
    const preferZh = lang === "zh-CN";
    const primary = preferZh ? `${slug}_zh.md` : `${slug}.md`;
    const fallback = preferZh ? `${slug}.md` : `${slug}_zh.md`;
    const md =
      lookupRaw(technicalRaw, primary) ?? lookupRaw(technicalRaw, fallback);
    if (!md) return null;
    const zhOnlyShown =
      lang === "en-US" &&
      !lookupRaw(technicalRaw, `${slug}.md`) &&
      Boolean(lookupRaw(technicalRaw, `${slug}_zh.md`));
    return { markdown: md, zhOnlyShown };
  }

  return null;
}

export function getNeighbors(
  sectionId: TutorialSectionId,
  slug: string,
): {
  prev: TutorialArticleMeta | null;
  next: TutorialArticleMeta | null;
} {
  const section = getSection(sectionId);
  if (!section) return { prev: null, next: null };
  const idx = section.articles.findIndex((a) => a.slug === slug);
  if (idx < 0) return { prev: null, next: null };
  return {
    prev: idx > 0 ? section.articles[idx - 1]! : null,
    next:
      idx < section.articles.length - 1
        ? section.articles[idx + 1]!
        : null,
  };
}

/** Flat list of sitemap-friendly tutorial paths. */
export function allTutorialPaths(): string[] {
  const paths = ["/tutorials", "/tutorials/intro"];
  for (const section of TUTORIAL_SECTIONS) {
    if (section.id === "intro") continue;
    paths.push(section.path);
    for (const article of section.articles) {
      if (article.slug === "index") continue;
      paths.push(articlePath(section.id, article.slug));
    }
  }
  return paths;
}
