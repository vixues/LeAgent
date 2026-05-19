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

interface Translation {
  nav: {
    about: string;
    intro: string;
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
    heroMeta: string;
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
    screenshots: FeatureScreenshot[];
  };
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
      business: "定制开发",
      download: "下载",
      pets: "宠物",
      company: "联系",
    },
    footer: {
      tagline: "本地优先的 AI 办公自动化平台。\n可自托管部署，开源可审计，无账户与追踪。",
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
      heroLine1: "本地优先的",
      heroLine2: "AI 办公自动化平台",
      heroSub:
        "LeAgent 将对话、工具与工作流整合于同一可自托管系统。支持本地部署、开放源码与多模型接入，适用于个人效率、团队流程与企业内部自动化场景。",
      heroMeta: "Apache-2.0 \u00B7 Python + React \u00B7 默认 SQLite",
      overviewEyebrow: "产品概述",
      overviewTitle: "统一架构，面向可审计的自动化",
      overviewLede:
        "平台以 QueryEngine 为会话编排核心，提供 80+ 领域工具、可视化工作流与分层 Prompt 管理。数据默认保存在本地，可按需扩展至 PostgreSQL 与向量记忆存储。",
      principlesEyebrow: "设计原则",
      principlesTitle: "面向长期部署的基础能力",
      continueTitle: "进一步了解",
    },
    intro: {
      title: "核心功能与典型场景",
      sub: "以下能力均可在本地或私有化环境中运行，截图展示界面与交付形态，便于评估是否满足你的业务需求。",
      placeholderNote: "截图占位，请将图片放入 public/images/features/",
      screenshots: [
        {
          id: "chat",
          label: "对话",
          title: "多轮对话与工具调用",
          description:
            "支持流式输出、会话状态管理与工具链调用。适用于问答、文档处理与任务型协作。",
        },
        {
          id: "genuiWeather",
          label: "GenUI",
          title: "结构化数据生成交互界面",
          description:
            "根据模型输出渲染天气卡片等 Generative UI 组件，将文本结果转化为可操作的界面元素。",
        },
        {
          id: "codeGeneration",
          label: "代码",
          title: "代码生成、解释与执行",
          description:
            "在沙箱环境中生成、审阅与运行代码，支持项目级辅助与开发流程集成。",
        },
        {
          id: "wordGeneration",
          label: "文档",
          title: "Office 文档生成与处理",
          description:
            "生成与编辑 Word 等办公文档，衔接报告撰写、模板填充与格式规范化流程。",
        },
        {
          id: "webpageGeneration",
          label: "网页",
          title: "网页与组件草稿生成",
          description:
            "输出页面结构、样式与静态资源草案，用于原型验证与内容发布前的快速迭代。",
        },
        {
          id: "workflow",
          label: "工作流",
          title: "可视化流程编排",
          description:
            "基于节点的工作流设计，支持工具节点组合，用于重复性任务自动化。",
        },
      ],
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
      wallpapersSub: "为 LeAgent 桌面挑的几张极简壁纸。点一下就能下载。",
      wallpapers: [
        { title: "玄空", tag: "深空", swatch: "linear-gradient(135deg, #0a1428 0%, #1c2440 50%, #322048 100%)" },
        { title: "青山", tag: "山水", swatch: "linear-gradient(160deg, #1a3a3a 0%, #3a6868 50%, #6a9a9a 100%)" },
        { title: "朱砂", tag: "霁色", swatch: "linear-gradient(140deg, #2a1818 0%, #6a3024 50%, #c25a3a 100%)" },
        { title: "素纸", tag: "白昼", swatch: "linear-gradient(150deg, #f5f0e6 0%, #e6dcc8 50%, #c8b89a 100%)" },
        { title: "墨韵", tag: "夜色", swatch: "linear-gradient(135deg, #0a0a0d 0%, #1a1a22 50%, #2a2a36 100%)" },
        { title: "苍穹", tag: "天青", swatch: "linear-gradient(160deg, #1a3a5c 0%, #2a6a96 50%, #5ca8d6 100%)" },
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
        icon: "noAccount",
        title: "无账户体系",
        short: "本地或私有化部署即可使用，无需注册与云端账户。",
        long: "LeAgent 运行于自有环境，不依赖厂商账户体系，便于在内网或隔离网络中交付。",
      },
      {
        icon: "noTracking",
        title: "无追踪",
        short: "默认不采集使用数据，不向第三方上报行为信息。",
        long: "外连请求由配置决定，通常仅指向所选的 LLM 服务接口，便于满足合规与审计要求。",
      },
      {
        icon: "openSource",
        title: "开放源码",
        short: "Apache-2.0 许可，代码、工具与工作流均可审查与二次开发。",
        long: "后端、前端与工具实现均以开源形式发布，支持 Fork、扩展与社区贡献。",
      },
      {
        icon: "extensible",
        title: "可扩展架构",
        short: "CLI、YAML 工作流与工具注册机制，便于集成现有系统。",
        long: "提供 80+ 工具、声明式规则与可热加载的 Prompt 模板，适合作为自动化平台底座。",
      },
      {
        icon: "localData",
        title: "数据本地化",
        short: "默认 SQLite 本地存储，可按规模升级数据库与向量检索。",
        long: "文件访问沙箱化，支持 PostgreSQL 与 Milvus，适配从单机到团队部署的演进路径。",
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
      business: "Custom",
      download: "Download",
      pets: "Pets",
      company: "Company",
    },
    footer: {
      tagline:
        "Local-first AI office automation.\nSelf-hosted, open-source, no accounts or tracking.",
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
      heroLine1: "Local-first",
      heroLine2: "AI office automation",
      heroSub:
        "LeAgent unifies chat, tools, and workflow automation in one self-hosted system. It supports local deployment, open-source inspection, and multi-provider models for personal productivity, team operations, and internal automation.",
      heroMeta: "Apache-2.0 \u00B7 Python + React \u00B7 SQLite by default",
      overviewEyebrow: "Overview",
      overviewTitle: "One stack for auditable automation",
      overviewLede:
        "Built around QueryEngine session orchestration, 80+ domain tools, visual workflows, and layered prompts. Data stays on your infrastructure by default, with optional PostgreSQL and vector memory.",
      principlesEyebrow: "Principles",
      principlesTitle: "Foundation for long-running deployments",
      continueTitle: "Continue",
    },
    intro: {
      title: "Core capabilities and scenarios",
      sub: "Representative UI flows below run on local or private deployments. Screenshots illustrate interface and deliverables for evaluation.",
      placeholderNote: "Screenshot placeholder — add images under public/images/features/",
      screenshots: [
        {
          id: "chat",
          label: "Chat",
          title: "Multi-turn dialogue and tool use",
          description:
            "Streaming responses, session state, and tool orchestration for Q&A, documents, and task workflows.",
        },
        {
          id: "genuiWeather",
          label: "GenUI",
          title: "Interactive UI from structured output",
          description:
            "Renders weather cards and other Generative UI components from model output for actionable interfaces.",
        },
        {
          id: "codeGeneration",
          label: "Code",
          title: "Generation, review, and execution",
          description:
            "Sandboxed code assistance for generation, explanation, and project-level development workflows.",
        },
        {
          id: "wordGeneration",
          label: "Documents",
          title: "Office document generation",
          description:
            "Produces and edits Word documents for reports, templates, and standardized formatting pipelines.",
        },
        {
          id: "webpageGeneration",
          label: "Web",
          title: "Web page and component drafts",
          description:
            "Drafts page structure, styles, and static assets for prototyping and pre-publish iteration.",
        },
        {
          id: "workflow",
          label: "Workflow",
          title: "Visual process orchestration",
          description:
            "Node-based flows with Cron, Webhooks, and tool nodes for recurring automation tasks.",
        },
      ],
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
      wallpapersSub: "A small set of minimal wallpapers, tuned to feel at home behind LeAgent. Click one to download.",
      wallpapers: [
        { title: "Xuan", tag: "Deep space", swatch: "linear-gradient(135deg, #0a1428 0%, #1c2440 50%, #322048 100%)" },
        { title: "Qing Shan", tag: "Jade mountain", swatch: "linear-gradient(160deg, #1a3a3a 0%, #3a6868 50%, #6a9a9a 100%)" },
        { title: "Vermillion", tag: "Sunset", swatch: "linear-gradient(140deg, #2a1818 0%, #6a3024 50%, #c25a3a 100%)" },
        { title: "Raw Silk", tag: "Daylight", swatch: "linear-gradient(150deg, #f5f0e6 0%, #e6dcc8 50%, #c8b89a 100%)" },
        { title: "Ink Mood", tag: "Night", swatch: "linear-gradient(135deg, #0a0a0d 0%, #1a1a22 50%, #2a2a36 100%)" },
        { title: "Cang", tag: "Heaven cyan", swatch: "linear-gradient(160deg, #1a3a5c 0%, #2a6a96 50%, #5ca8d6 100%)" },
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
        icon: "noAccount",
        title: "No account system",
        short: "Deploy locally or privately without vendor accounts or sign-up flows.",
        long: "LeAgent runs in your environment, suitable for intranet and air-gapped delivery.",
      },
      {
        icon: "noTracking",
        title: "No tracking",
        short: "No usage telemetry or third-party analytics by default.",
        long: "Outbound traffic is configuration-driven, typically limited to chosen LLM endpoints.",
      },
      {
        icon: "openSource",
        title: "Open source",
        short: "Apache-2.0 — auditable code, tools, and workflows.",
        long: "Backend, frontend, and tools are published for inspection, fork, and extension.",
      },
      {
        icon: "extensible",
        title: "Extensible stack",
        short: "CLI, YAML workflows, and a tool registry for system integration.",
        long: "80+ tools, declarative rules, and hot-reloadable prompts as an automation platform base.",
      },
      {
        icon: "localData",
        title: "Local data",
        short: "SQLite by default; scale with PostgreSQL and vector search when needed.",
        long: "Sandboxed file access and optional Milvus for team-scale deployments.",
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
