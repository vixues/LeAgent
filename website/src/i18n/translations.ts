import type { IconName } from "@/components/Icon";
import {
  INSTALL_PS1_URL,
  INSTALL_SH_URL,
  REPO_URL,
} from "@/lib/content";

export type Lang = "zh-CN" | "en-US";

interface Principle {
  icon: IconName;
  title: string;
  short: string;
  long: string;
}

interface UseCase {
  title: string;
  description: string;
}

interface Capability {
  title: string;
  description: string;
}

interface InstallSnippet {
  label: string;
  steps: string;
  fromSource: string;
}

interface PetFeature {
  title: string;
  description: string;
}

interface Wallpaper {
  title: string;
  tag: string;
  swatch: string;
}

interface PetGif {
  name: string;
  mood: string;
}

interface FeatureScreenshot {
  id: string;
  title: string;
  description: string;
  label: string;
}

interface ProviderInfo {
  name: string;
  note: string;
}

interface MultiModelBlock {
  eyebrow: string;
  title: string;
  sub: string;
  providers: ProviderInfo[];
}

interface WorkflowShape {
  tag: string;
  title: string;
  description: string;
}

interface WorkflowsPage {
  heroEyebrow: string;
  heroTitle: string;
  heroSub: string;
  heroMeta: string;
  featuresEyebrow: string;
  featuresTitle: string;
  featuresSub: string;
  screenshots: FeatureScreenshot[];
  shapesEyebrow: string;
  shapesTitle: string;
  shapesSub: string;
  shapes: WorkflowShape[];
  claimsEyebrow: string;
  claimsTitle: string;
  claims: Capability[];
  ctaTitle: string;
  ctaSub: string;
}

interface Translation {
  nav: {
    about: string;
    intro: string;
    workflows: string;
    business: string;
    download: string;
    pets: string;
    company: string;
  };
  footer: {
    tagline: string;
    pages: string;
    resources: string;
    legal: string;
    documentation: string;
    releases: string;
    license: string;
    security: string;
    copyright: string;
    tao: string;
    taoSub: string;
  };
  common: {
    download: string;
    viewOnGithub: string;
    learnMore: string;
    viewSource: string;
    githubReleases: string;
    fullInstallGuide: string;
    quickInstall: string;
    fromSource: string;
    exploreUseCases: string;
    viewFeatures: string;
    contactCustom: string;
    meetDeveloper: string;
    startBuilding: string;
  };
  home: {
    heroLine1: string;
    heroLine2: string;
    heroSub: string;
    overviewEyebrow: string;
    overviewTitle: string;
    overviewLede: string;
    principlesEyebrow: string;
    principlesTitle: string;
    continueTitle: string;
  };
  intro: {
    title: string;
    sub: string;
    placeholderNote: string;
    featuresEyebrow: string;
    screenshots: FeatureScreenshot[];
    multiModel: MultiModelBlock;
  };
  workflows: WorkflowsPage;
  business: {
    title: string;
    sub: string;
    useCasesEyebrow: string;
    useCasesTitle: string;
    capabilitiesEyebrow: string;
    capabilitiesTitle: string;
    ctaTitle: string;
    ctaSub: string;
  };
  downloadPage: {
    title: string;
    sub: string;
    windowsButton: string;
    macosButton: string;
    requirementsEyebrow: string;
    requirementsFooter: string;
    installEyebrow: string;
    installTitle: string;
    installFooter: string;
    readmeLink: string;
  };
  company: {
    eyebrow: string;
    tao: string;
    taoSub: string;
    contactLabels: {
      email: string;
      github: string;
      xiaohongshu: string;
      website: string;
    };
  };
  pets: {
    title: string;
    sub: string;
    introTitle: string;
    introP1: string;
    introP2: string;
    featuresTitle: string;
    features: PetFeature[];
    wallpapersTitle: string;
    wallpapersSub: string;
    wallpapers: Wallpaper[];
    gifsTitle: string;
    gifsSub: string;
    gifs: PetGif[];
    downloadLabel: string;
    placeholderNote: string;
  };
  principles: Principle[];
  useCases: UseCase[];
  capabilities: Capability[];
  requirements: string[];
  install: {
    linux: InstallSnippet;
    macos: InstallSnippet;
    windows: InstallSnippet;
  };
}

export const translations: Record<Lang, Translation> = {
  "zh-CN": {
    nav: {
      about: "关于",
      intro: "介绍",
      workflows: "工作流",
      business: "定制开发",
      download: "下载",
      pets: "宠物",
      company: "联系",
    },
    footer: {
      tagline: "真正完成工作的开源桌面 AI 智能体。\n规划、工具、工作流与 Generative UI，集于一栈。",
      pages: "页面",
      resources: "资源",
      legal: "法律",
      documentation: "文档",
      releases: "版本发布",
      license: "Apache-2.0 许可证",
      security: "安全",
      copyright: `© ${new Date().getFullYear()} LeAgent 贡献者`,
      tao: "易简",
      taoSub: "少则得",
    },
    common: {
      download: "下载",
      viewOnGithub: "在 GitHub 上查看",
      learnMore: "了解更多",
      viewSource: "查看源码",
      githubReleases: "GitHub 版本",
      fullInstallGuide: "完整安装指南",
      quickInstall: "快速安装",
      fromSource: "从源码构建",
      exploreUseCases: "定制开发",
      viewFeatures: "功能介绍",
      contactCustom: "联系定制开发",
      meetDeveloper: "联系开发者",
      startBuilding: "查看部署方式",
    },
    home: {
      heroLine1: "真正完成工作的",
      heroLine2: "开源桌面 AI 智能体",
      heroSub:
        "LeAgent 不止于对话。它在统一的智能体循环中自主规划、调用工具并自我纠错，亲手设计并运行可视化工作流，把可交互界面实时流式渲染进聊天——内置 100+ 工具，开源、可自托管。",
      overviewEyebrow: "产品概述",
      overviewTitle: "一套技术栈，完整的智能体能力",
      overviewLede:
        "以 QueryEngine 会话编排为核心，融合 13 大类、100+ 内置工具、可视化工作流、Generative UI 与多供应商模型路由。开箱即用、相互打通，既可自带云端密钥，也可完全本地运行。",
      principlesEyebrow: "核心能力",
      principlesTitle: "把强大的能力交到你手里",
      continueTitle: "进一步了解",
    },
    intro: {
      title: "核心功能与典型场景",
      sub: "从多轮对话、文档生产到论文研读与代码执行——下列能力开箱即用、相互打通。截图展示真实界面与交付形态。",
      placeholderNote: "截图占位，请将图片放入 public/images/features/",
      featuresEyebrow: "能力总览",
      screenshots: [
        {
          id: "chat",
          label: "对话",
          title: "多轮对话与工具调用",
          description:
            "流式输出、会话状态管理与工具链编排。在一次回合内自主规划、调用工具并自我纠错。",
        },
        {
          id: "genuiWeather",
          label: "Generative UI",
          title: "流式渲染可交互界面",
          description:
            "智能体流式输出声明式 UI 树——KPI 看板、幻灯片、画廊、步骤条，在聊天中内联渲染，并可导出为 PDF / PPTX。",
        },
        {
          id: "codeGeneration",
          label: "代码",
          title: "代码生成、解释与执行",
          description:
            "在隔离沙箱中生成、审阅与运行代码，支持项目级脚手架、跨文件编辑与实时开发服务器。",
        },
        {
          id: "wordGeneration",
          label: "文档",
          title: "Office 文档生成与处理",
          description:
            "读写 Word / Excel / PPTX / PDF，配合 OCR、分类与模板填充，一次回合产出排版精良的成稿。",
        },
        {
          id: "webpageGeneration",
          label: "网页",
          title: "网页与组件草稿生成",
          description:
            "输出页面结构、样式与静态资源草案，用于原型验证与内容发布前的快速迭代。",
        },
        {
          id: "paperMode",
          label: "论文模式",
          title: "以引用为依据的研究分析",
          description:
            "打开 PDF，智能体即化身研究分析师：结构与大纲提取、忠实的章节 / 全文摘要、参考文献与 LaTeX 公式抽取、区域翻译——文本抽取完全离线。",
        },
      ],
      multiModel: {
        eyebrow: "多模型支持",
        title: "一个接口，多家模型随心切换",
        sub: "支持 DeepSeek、通义千问、OpenAI、Anthropic、Azure OpenAI、Ollama、vLLM 等主流供应商。自带云端密钥或本地推理均可，会话内随时切换模型。",
        providers: [
          { name: "DeepSeek", note: "推荐默认 · V4 Pro + V4 Flash" },
          { name: "通义千问 · DashScope", note: "支持思考与搜索模式" },
          { name: "OpenAI", note: "云端前沿模型" },
          { name: "Anthropic", note: "Claude 系列模型" },
          { name: "Azure OpenAI", note: "企业级托管部署" },
          { name: "Ollama", note: "完全本地推理" },
          { name: "vLLM", note: "自托管 OpenAI 兼容推理" },
        ],
      },
    },
    workflows: {
      heroEyebrow: "可视化工作流",
      heroTitle: "把每一项能力\n编排成可运行的流程",
      heroSub:
        "基于 ReactFlow 的可视化编辑器：每个工具都会自动成为带类型的节点，无需任何胶水代码即可拖拽编排。同一引擎驱动已保存流程、聊天步骤卡与智能体亲手编写的图。",
      heroMeta: "ReactFlow 编辑器 · 工具即节点 · YAML 导出",
      featuresEyebrow: "工作流能力",
      featuresTitle: "从拖拽编排到自纠错生产",
      featuresSub: "节点编辑与媒体资产流水线，覆盖从设计到产出的完整闭环。",
      screenshots: [
        {
          id: "workflowEditor",
          label: "节点编辑器",
          title: "拖拽式 DAG 编辑器",
          description:
            "100+ 工具自动暴露为带类型的 `Tool.<name>` 节点，配合类型化媒体插槽，连线即用。支持 YAML 导出与可复用模板。",
        },
        {
          id: "workflowArt",
          label: "美术资产流水线",
          title: "游戏美术资产生成与自纠错",
          description:
            "图像 / 视频 / 3D 网格 / VFX 的可组合生成节点，配备质量门控与有界自纠错循环，并导出可直接接入引擎（Unity / Unreal / Godot）的资产包。",
        },
      ],
      shapesEyebrow: "统一引擎",
      shapesTitle: "三种形态，同一执行器",
      shapesSub: "无论从何处发起，工作流都汇聚到同一个 WorkflowExecutor 运行——一致的调度、重试与状态归属。",
      shapes: [
        { tag: "已保存流程", title: "DAG 工作流", description: "在编辑器中设计、保存并复用的有向无环图，可由 Cron 或智能体触发运行。" },
        { tag: "聊天步骤卡", title: "Playbook 步骤", description: "聊天回合内的步骤卡会编译为线性流程，与编辑器流程共用同一执行器。" },
        { tag: "聊天内嵌入", title: "图预览嵌入", description: "经校验的 Flow JSON 可在聊天中内联预览，无缝衔接设计与运行。" },
      ],
      claimsEyebrow: "为什么强大",
      claimsTitle: "可视化之下的工程保证",
      claims: [
        { title: "工具即节点", description: "每个已注册工具都会自动提升为带类型节点——新能力以可视化方式即时可用，无需胶水代码。" },
        { title: "并发与可靠性", description: "按就绪批次并发执行独立分支、集中式重试 / 退避、逐节点超时与可持久化暂停 / 恢复。" },
        { title: "自纠错闭环", description: "质量门控配合有界自纠错循环，让美术资产等输出在不达标时自动重生成。" },
        { title: "可移植与可复用", description: "YAML 导出、Cron / Webhook 触发与模板库，便于版本管理与跨环境复用。" },
      ],
      ctaTitle: "把你的流程搬进 LeAgent",
      ctaSub: "下载即可在本地搭建第一条工作流，或查看源码了解引擎实现。",
    },
    business: {
      title: "定制开发\n与私有化交付",
      sub: "面向企业或团队的 LeAgent 定制实施：在开源核心之上扩展业务流程、专用工具与系统集成，并提供部署与维护支持。",
      useCasesEyebrow: "服务范围",
      useCasesTitle: "可交付的定制方向",
      capabilitiesEyebrow: "实施能力",
      capabilitiesTitle: "技术与交付保障",
      ctaTitle: "讨论你的定制需求",
      ctaSub: "可通过联系页沟通场景、合规要求与交付周期；标准版亦可自行下载部署。",
    },
    downloadPage: {
      title: "获取 LeAgent",
      sub: "选择平台后按脚本安装，或使用源码构建。",
      windowsButton: "下载 Windows 版",
      macosButton: "下载 macOS 版",
      requirementsEyebrow: "系统要求",
      requirementsFooter:
        "默认数据库为 SQLite。规模化部署可配置 PostgreSQL 与 Milvus 向量存储。",
      installEyebrow: "快速开始",
      installTitle: "安装与运行",
      installFooter: "需要 Python 3.11+、Node.js 20+ 以及约 4 GB 内存。详见",
      readmeLink: "README",
    },
    company: {
      eyebrow: "开发者",
      tao: "易简，则理得矣",
      taoSub: "少则得，多则惑",
      contactLabels: {
        email: "邮箱",
        github: "GitHub",
        xiaohongshu: "小红书",
        website: "个人网站",
      },
    },
    pets: {
      title: "桌面宠物 · 知音",
      sub: "一只住在桌面上的小伙伴。会动、可换、能下载 — 给屏幕添点氛围。",
      introTitle: "这位小家伙是谁",
      introP1: "LeAgent 自带一个轻量的桌面伙伴：常驻在屏幕一角，安静陪着你。消息来了、任务结束了、出错了 — 它会换个神态告诉你。像古时候候在桌旁的童子，知意而不打扰。",
      introP2: "全程本地运行 — 没有云资源，也没有遥测。所有动画和壁纸都是离线静态文件，你想换随时可以换。",
      featuresTitle: "它是怎么陪你的",
      features: [
        { title: "情绪状态机", description: "12 种神态：在想、开心、迷糊、专注、歇着 — 跟着任务事件和你的节奏自动切换。" },
        { title: "可对话浮窗", description: "点一下就开个对话框，跟智能体共用同一段上下文。不用切窗口，问完就有答。" },
        { title: "通知化身", description: "代理回复、工具结果、定时任务都用神态来告诉你 — 不抢你眼睛的位置。" },
        { title: "可换皮肤", description: "GIF / APNG / Lottie 都支持。社区皮肤包就是一个 zip，丢进去就用。" },
        { title: "桌面背景同步", description: "它会偷偷瞄一眼你的壁纸，把投影和轮廓调成相配的色调，跟桌面融在一起。" },
        { title: "省电模式", description: "60 秒没动作就化成一帧水墨静画，CPU 占用接近于零。" },
      ],
      wallpapersTitle: "壁纸合集",
      wallpapersSub: "六张手绘风景壁纸，从黄昏小镇到浮空幻境，给 LeAgent 桌面换换心情。点一下就能下载。",
      wallpapers: [
        { title: "小镇黄昏", tag: "暖暮", swatch: "linear-gradient(135deg, #3a2418 0%, #8a5030 50%, #d4a060 100%)" },
        { title: "浮空幻境", tag: "云海", swatch: "linear-gradient(160deg, #1a2848 0%, #4a68a8 50%, #a8c8f0 100%)" },
        { title: "海滨沙滩", tag: "海岸", swatch: "linear-gradient(150deg, #1a4868 0%, #3a98b8 50%, #e8d8b0 100%)" },
        { title: "田园乡野", tag: "乡野", swatch: "linear-gradient(140deg, #2a4820 0%, #6a9848 50%, #d8c878 100%)" },
        { title: "雪山地平线", tag: "雪峰", swatch: "linear-gradient(160deg, #486888 0%, #98b8d8 50%, #f0f4f8 100%)" },
        { title: "魔法森林", tag: "密林", swatch: "linear-gradient(135deg, #0a2818 0%, #1a5838 50%, #3a8868 100%)" },
      ],
      gifsTitle: "宠物动图",
      gifsSub: "可以直接拖进去用的动画包。GIF 和 APNG 两种格式，看心情挑。",
      gifs: [
        { name: "云童", mood: "云中嬉戏" },
        { name: "墨鲤", mood: "水间游弋" },
        { name: "纸鹤", mood: "悠然栖息" },
        { name: "山鬼", mood: "翩翩起舞" },
        { name: "灯笼", mood: "晚风摇曳" },
        { name: "茶童", mood: "煮茶论道" },
        { name: "竹影", mood: "随风轻摆" },
        { name: "夜灯", mood: "静夜呼吸" },
      ],
      downloadLabel: "下载",
      placeholderNote: "下载链接指向 GitHub Releases — 正式资源跟随公开版本一起发布。",
    },
    principles: [
      {
        icon: "sparkle",
        title: "会自我纠错的 Agent 运行时",
        short: "在统一「思考-行动」循环中规划、调用工具并自我纠错。",
        long: "多轮流式会话、按任务绑定模型、可持久化检查点，以及情景 / 语义 / 程序性三存储认知记忆。",
      },
      {
        icon: "extensible",
        title: "100+ 内置工具",
        short: "13 大类、100+ 离线工具，每个都能直接编排进工作流。",
        long: "覆盖文档、网页、数据、代码、数据库、媒体与游戏美术生成，统一经由单一执行器分发。",
      },
      {
        icon: "workflow",
        title: "智能化可视工作流",
        short: "基于 ReactFlow 的编辑器，每个工具自动成为带类型的节点。",
        long: "同一引擎驱动已保存流程、聊天步骤卡与智能体亲手编写的图，支持并发执行与可持久化暂停 / 恢复。",
      },
      {
        icon: "chat",
        title: "Generative UI",
        short: "把可交互界面实时流式渲染进聊天，并可导出 PDF / PPTX。",
        long: "声明式 UI 树通过 SSE 实时流式输出与增量更新——KPI 看板、幻灯片、画廊、步骤条，皆内联呈现。",
      },
      {
        icon: "model",
        title: "多模型支持",
        short: "DeepSeek、通义、OpenAI、Anthropic、Ollama、vLLM — 统一接入，随时切换。",
        long: "按任务绑定 provider / model，支持多家供应商与本地推理，会话内可自由切换。",
      },
      {
        icon: "openSource",
        title: "开源 · 可自托管",
        short: "Apache-2.0，代码、工具与工作流均可审查与二次开发，可完全离线运行。",
        long: "后端、前端与工具实现均以开源形式发布；默认零外部依赖（SQLite、单进程）即可在本地运行。",
      },
    ],
    useCases: [
      {
        title: "私有化部署",
        description: "在内网或专属服务器部署 LeAgent，对接企业身份、网络策略与数据留存要求。",
      },
      {
        title: "业务流程定制",
        description: "按行业场景设计工作流、工具链与 Prompt 体系，嵌入审批、报表与运营流程。",
      },
      {
        title: "系统集成",
        description: "通过 API、Webhook 与现有 OA、IM、数据平台对接，形成统一的智能自动化入口。",
      },
    ],
    capabilities: [
      { title: "需求分析与方案设计", description: "梳理业务目标、数据边界与模型选型，输出可落地的架构与里程碑计划。" },
      { title: "专用工具开发", description: "在 LeAgent 工具框架内实现领域解析、接口调用与结果校验逻辑。" },
      { title: "模型与供应商适配", description: "配置 DeepSeek、OpenAI、通义、Ollama、vLLM 等提供商及路由策略。" },
      { title: "工作流与规则编排", description: "设计可视化流程、Cron/Webhook 触发与声明式规则，覆盖重复性任务。" },
      { title: "部署与运维支持", description: "提供安装脚本、容器化与升级路径，协助监控、备份与版本迁移。" },
      { title: "培训与文档交付", description: "交付运维手册、接口说明与使用培训，支持团队自主维护与扩展。" },
    ],
    requirements: [
      "Python 3.11+",
      "Node.js 20+",
      "4 GB 内存（建议 8 GB）",
      "2 GB 磁盘空间",
    ],
    install: {
      linux: {
        label: "Linux",
        steps: `curl -fsSL ${INSTALL_SH_URL} | bash
leagent init
leagent app`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      },
      macos: {
        label: "macOS",
        steps: `curl -fsSL ${INSTALL_SH_URL} | bash
leagent init
leagent app`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      },
      windows: {
        label: "Windows",
        steps: `# PowerShell（如需要请以管理员身份运行）
iwr -useb ${INSTALL_PS1_URL} | iex
leagent init
leagent app`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
.\\start.ps1`,
      },
    },
  },

  "en-US": {
    nav: {
      about: "About",
      intro: "Intro",
      workflows: "Workflows",
      business: "Custom",
      download: "Download",
      pets: "Pets",
      company: "Company",
    },
    footer: {
      tagline:
        "The open-source desktop AI agent that gets work done.\nPlanning, tools, workflows, and Generative UI in one stack.",
      pages: "Pages",
      resources: "Resources",
      legal: "Legal",
      documentation: "Documentation",
      releases: "Releases",
      license: "Apache-2.0 License",
      security: "Security",
      copyright: `\u00A9 ${new Date().getFullYear()} LeAgent contributors`,
      tao: "Simplicity",
      taoSub: "Less is gain",
    },
    common: {
      download: "Download",
      viewOnGithub: "View on GitHub",
      learnMore: "Learn more",
      viewSource: "View source",
      githubReleases: "GitHub Releases",
      fullInstallGuide: "Full install guide",
      quickInstall: "Quick install",
      fromSource: "From source",
      exploreUseCases: "Custom development",
      viewFeatures: "Features",
      contactCustom: "Contact for custom work",
      meetDeveloper: "Contact",
      startBuilding: "View deployment",
    },
    home: {
      heroLine1: "The open-source desktop",
      heroLine2: "AI agent that gets work done",
      heroSub:
        "LeAgent doesn't just chat. It plans, calls tools, and self-corrects in one think-act loop, designs and runs visual workflows, and streams live interactive UI into the chat — with 100+ built-in tools, open-source and self-hostable.",
      overviewEyebrow: "Overview",
      overviewTitle: "One stack, a complete agent platform",
      overviewLede:
        "Built around QueryEngine session orchestration, 100+ tools across 13 categories, visual workflows, Generative UI, and multi-provider model routing. Wired together and ready out of the box — bring cloud keys or stay fully local.",
      principlesEyebrow: "Capabilities",
      principlesTitle: "Powerful building blocks, in your hands",
      continueTitle: "Continue",
    },
    intro: {
      title: "Core capabilities and scenarios",
      sub: "From multi-turn chat and document production to paper research and code execution — these capabilities are wired together and work out of the box. Screenshots show the real interface and deliverables.",
      placeholderNote: "Screenshot placeholder — add images under public/images/features/",
      featuresEyebrow: "Capability overview",
      screenshots: [
        {
          id: "chat",
          label: "Chat",
          title: "Multi-turn dialogue and tool use",
          description:
            "Streaming responses, session state, and tool orchestration. Plans, calls tools, and self-corrects within a single turn.",
        },
        {
          id: "genuiWeather",
          label: "Generative UI",
          title: "Live interactive UI, streamed",
          description:
            "Agents stream declarative UI trees — KPI boards, slide decks, galleries, steppers — that render inline in chat and export to PDF or PPTX.",
        },
        {
          id: "codeGeneration",
          label: "Code",
          title: "Generation, review, and execution",
          description:
            "Sandboxed code assistance: scaffold from templates, edit across the tree, and run a live dev server in isolation.",
        },
        {
          id: "wordGeneration",
          label: "Documents",
          title: "Office document generation",
          description:
            "Read and write Word / Excel / PPTX / PDF with OCR, classification, and template fill — a polished deliverable in one turn.",
        },
        {
          id: "webpageGeneration",
          label: "Web",
          title: "Web page and component drafts",
          description:
            "Drafts page structure, styles, and static assets for prototyping and pre-publish iteration.",
        },
        {
          id: "paperMode",
          label: "Paper Mode",
          title: "Citation-grounded research analysis",
          description:
            "Open a PDF and the agent becomes a research analyst: outline extraction, faithful section / whole-paper summaries, reference and LaTeX-formula extraction, and region translation — text extraction fully offline.",
        },
      ],
      multiModel: {
        eyebrow: "Multi-model support",
        title: "One interface, switch models anytime",
        sub: "DeepSeek, Qwen, OpenAI, Anthropic, Azure OpenAI, Ollama, and vLLM — bring cloud keys or run fully local, and change models per session.",
        providers: [
          { name: "DeepSeek", note: "Recommended default · V4 Pro + V4 Flash" },
          { name: "DashScope (Qwen)", note: "Thinking + search modes" },
          { name: "OpenAI", note: "Cloud frontier models" },
          { name: "Anthropic", note: "Claude model family" },
          { name: "Azure OpenAI", note: "Enterprise hosted deployment" },
          { name: "Ollama", note: "Fully local inference" },
          { name: "vLLM", note: "Self-hosted OpenAI-compatible inference" },
        ],
      },
    },
    workflows: {
      heroEyebrow: "Visual workflows",
      heroTitle: "Orchestrate every capability\ninto a runnable flow",
      heroSub:
        "A ReactFlow editor where every tool automatically becomes a typed node — drag and wire with zero glue code. One engine backs saved flows, chat step-cards, and agent-authored graphs.",
      heroMeta: "ReactFlow editor · Tools as nodes · YAML export",
      featuresEyebrow: "Workflow capabilities",
      featuresTitle: "From drag-and-drop to self-correcting production",
      featuresSub: "Node editing and media-asset pipelines cover the full loop from design to production.",
      screenshots: [
        {
          id: "workflowEditor",
          label: "Node editor",
          title: "Drag-and-drop DAG editor",
          description:
            "100+ tools are auto-exposed as typed `Tool.<name>` nodes with typed media sockets — wire and run. YAML export and reusable templates included.",
        },
        {
          id: "workflowArt",
          label: "Art asset pipeline",
          title: "Game-art generation with self-correction",
          description:
            "Composable image / video / 3D mesh / VFX nodes with a quality gate and a bounded self-correction loop, exporting an engine-ready (Unity / Unreal / Godot) bundle.",
        },
      ],
      shapesEyebrow: "One engine",
      shapesTitle: "Three shapes, one executor",
      shapesSub: "Wherever a flow starts, it converges on the same WorkflowExecutor — consistent scheduling, retries, and state ownership.",
      shapes: [
        { tag: "Saved flow", title: "DAG workflow", description: "Directed acyclic graphs designed, saved, and reused in the editor — triggered by Cron or the agent." },
        { tag: "Chat step-card", title: "Playbook steps", description: "Step-cards inside a chat turn compile to a linear flow and share the same executor as editor runs." },
        { tag: "In-chat embed", title: "Graph preview", description: "Validated Flow JSON previews inline in chat, bridging design and execution seamlessly." },
      ],
      claimsEyebrow: "Why it's powerful",
      claimsTitle: "Engineering guarantees beneath the canvas",
      claims: [
        { title: "Tools are nodes", description: "Every registered tool is lifted into a typed node — new capabilities are instantly available visually, with zero glue code." },
        { title: "Concurrent and reliable", description: "Batched concurrent execution of independent branches, centralized retry / backoff, per-node timeouts, and durable pause / resume." },
        { title: "Self-correcting loop", description: "A quality gate plus a bounded self-correction loop regenerates outputs like art assets automatically when they miss the bar." },
        { title: "Portable and reusable", description: "YAML export, Cron / Webhook triggers, and a template library for versioning and reuse across environments." },
      ],
      ctaTitle: "Bring your process into LeAgent",
      ctaSub: "Download to build your first workflow locally, or read the source to see how the engine works.",
    },
    business: {
      title: "Custom development\nand private delivery",
      sub: "Implementation services on top of the open-source core: business workflows, dedicated tools, system integration, deployment, and maintenance.",
      useCasesEyebrow: "Services",
      useCasesTitle: "Typical engagement areas",
      capabilitiesEyebrow: "Delivery",
      capabilitiesTitle: "Technical and operational support",
      ctaTitle: "Discuss your requirements",
      ctaSub: "Reach out via the contact page for scope, compliance, and timeline. The standard edition remains available for self-service download.",
    },
    downloadPage: {
      title: "Get LeAgent",
      sub: "Install via script for your platform, or build from source.",
      windowsButton: "Download for Windows",
      macosButton: "Download for macOS",
      requirementsEyebrow: "System requirements",
      requirementsFooter:
        "SQLite by default. For scale, configure PostgreSQL and Milvus vector storage.",
      installEyebrow: "Get started",
      installTitle: "Install & run",
      installFooter: "Requires Python 3.11+, Node.js 20+, and ~4 GB RAM. See the",
      readmeLink: "README",
    },
    company: {
      eyebrow: "the maker",
      tao: "Keep change simple; the pattern becomes clear.",
      taoSub: "In less, there is gain; in excess, confusion.",
      contactLabels: {
        email: "Email",
        github: "GitHub",
        xiaohongshu: "Xiaohongshu",
        website: "Website",
      },
    },
    pets: {
      title: "Desktop Pets · Quiet Companions",
      sub: "A tiny companion that lives on your desktop. Animated, swappable, easy to download — set the mood of your screen.",
      introTitle: "Who is this little thing",
      introP1: "LeAgent comes with a small desktop companion that quietly sits in a corner of your screen. When something happens — a message arrives, a task wraps up, something breaks — it changes mood to let you know. Think of it as a gentle witness to your work.",
      introP2: "Everything runs locally — no cloud, no telemetry. The animations and wallpapers are plain files on your disk. Swap any of them whenever you’d like.",
      featuresTitle: "How it shows up",
      features: [
        { title: "Twelve little moods", description: "Thinking, delighted, puzzled, focused, resting — it shifts on its own as tasks come and go." },
        { title: "Tap to talk", description: "Click the pet and a chat bubble opens, sharing the same agent context. No window-switching, just ask and answer." },
        { title: "Quiet notifications", description: "Agent replies, tool results, and scheduled jobs come through as small gestures — without yanking your focus." },
        { title: "Swappable skins", description: "Works with GIF, APNG, and Lottie. Community skin packs ship as a single zip — drag it in and you’re done." },
        { title: "Wallpaper-aware", description: "It glances at your wallpaper and tunes its shadow and edges to match, so it blends into your desktop." },
        { title: "Gentle on the battery", description: "Idles into a still ink-painting frame after 60 seconds. Near-zero CPU when it’s just sitting there." },
      ],
      wallpapersTitle: "Wallpaper collection",
      wallpapersSub: "Six hand-painted landscape wallpapers — from a dusk-lit town to a floating sky realm. Click one to download.",
      wallpapers: [
        { title: "Town Dusk", tag: "Warm dusk", swatch: "linear-gradient(135deg, #3a2418 0%, #8a5030 50%, #d4a060 100%)" },
        { title: "Floating Realm", tag: "Sky isles", swatch: "linear-gradient(160deg, #1a2848 0%, #4a68a8 50%, #a8c8f0 100%)" },
        { title: "Seaside Beach", tag: "Coastal", swatch: "linear-gradient(150deg, #1a4868 0%, #3a98b8 50%, #e8d8b0 100%)" },
        { title: "Pastoral Fields", tag: "Countryside", swatch: "linear-gradient(140deg, #2a4820 0%, #6a9848 50%, #d8c878 100%)" },
        { title: "Snowy Horizon", tag: "Alpine", swatch: "linear-gradient(160deg, #486888 0%, #98b8d8 50%, #f0f4f8 100%)" },
        { title: "Enchanted Forest", tag: "Woodland", swatch: "linear-gradient(135deg, #0a2818 0%, #1a5838 50%, #3a8868 100%)" },
      ],
      gifsTitle: "Animated pets",
      gifsSub: "Animation packs you can drop straight in. GIF + APNG — pick whichever works.",
      gifs: [
        { name: "Cloud Child", mood: "playing in mist" },
        { name: "Ink Carp", mood: "drifting in water" },
        { name: "Paper Crane", mood: "perched at ease" },
        { name: "Mountain Sprite", mood: "dancing lightly" },
        { name: "Lantern", mood: "swaying in evening" },
        { name: "Tea Boy", mood: "brewing in silence" },
        { name: "Bamboo Shadow", mood: "rustling softly" },
        { name: "Night Lamp", mood: "breathing in dark" },
      ],
      downloadLabel: "Download",
      placeholderNote: "Downloads point to GitHub Releases — the real assets land with the public release.",
    },
    principles: [
      {
        icon: "sparkle",
        title: "Self-correcting agent runtime",
        short: "Plans, calls tools, and self-corrects in one think-act loop.",
        long: "Multi-turn streaming sessions, task-based model bindings, durable checkpoints, and episodic / semantic / procedural memory.",
      },
      {
        icon: "extensible",
        title: "100+ built-in tools",
        short: "100+ offline tools across 13 categories — each one wires into a workflow.",
        long: "Documents, web, data, code, databases, media, and game-art generation, dispatched through one executor.",
      },
      {
        icon: "workflow",
        title: "Agentic visual workflows",
        short: "A ReactFlow editor where every tool is automatically a typed node.",
        long: "One engine backs saved flows, chat step-cards, and agent-authored graphs, with concurrent execution and durable pause / resume.",
      },
      {
        icon: "chat",
        title: "Generative UI",
        short: "Stream live interactive interfaces into chat; export to PDF / PPTX.",
        long: "Declarative UI trees stream and patch over SSE — KPI boards, slide decks, galleries, steppers — rendered inline.",
      },
      {
        icon: "model",
        title: "Multi-model support",
        short: "DeepSeek, Qwen, OpenAI, Anthropic, Ollama, vLLM — one interface, switch anytime.",
        long: "Task-based provider / model bindings across vendors and local inference — change models per session.",
      },
      {
        icon: "openSource",
        title: "Open source, self-hostable",
        short: "Apache-2.0 — auditable code, tools, and workflows; runs fully offline.",
        long: "Backend, frontend, and tools are published for inspection and extension; zero external dependencies by default (SQLite, single process).",
      },
    ],
    useCases: [
      {
        title: "Private deployment",
        description: "On-prem or dedicated servers with identity, network policy, and data retention aligned to your organization.",
      },
      {
        title: "Business workflow design",
        description: "Custom workflows, toolchains, and prompts for approvals, reporting, and operations.",
      },
      {
        title: "System integration",
        description: "APIs and webhooks to OA, IM, and data platforms as a unified automation entry point.",
      },
    ],
    capabilities: [
      { title: "Requirements and architecture", description: "Scope, data boundaries, model selection, and a phased delivery plan." },
      { title: "Custom tool development", description: "Domain parsers, API connectors, and validation within the LeAgent tool framework." },
      { title: "Model provider setup", description: "DeepSeek, OpenAI, Anthropic, DashScope, Ollama, vLLM routing and configuration." },
      { title: "Workflow and rules", description: "Visual flows, Cron/Webhook triggers, and declarative rules for recurring tasks." },
      { title: "Deployment and operations", description: "Install scripts, containers, upgrades, monitoring, and backup guidance." },
      { title: "Training and documentation", description: "Runbooks, API docs, and handover for in-house maintenance." },
    ],
    requirements: [
      "Python 3.11+",
      "Node.js 20+",
      "4 GB RAM (8 GB recommended)",
      "2 GB disk space",
    ],
    install: {
      linux: {
        label: "Linux",
        steps: `curl -fsSL ${INSTALL_SH_URL} | bash
leagent init
leagent app`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      },
      macos: {
        label: "macOS",
        steps: `curl -fsSL ${INSTALL_SH_URL} | bash
leagent init
leagent app`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      },
      windows: {
        label: "Windows",
        steps: `# PowerShell (run as Administrator if needed)
iwr -useb ${INSTALL_PS1_URL} | iex
leagent init
leagent app`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
.\\start.ps1`,
      },
    },
  },
};
