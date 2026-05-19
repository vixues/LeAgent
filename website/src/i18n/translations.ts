import {
  INSTALL_PS1_URL,
  INSTALL_SH_URL,
  REPO_URL,
} from "@/lib/content";

export type Lang = "zh-CN" | "en-US";

interface Principle {
  icon: string;
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
    meetDeveloper: string;
    startBuilding: string;
  };
  home: {
    kicker: string;
    heroLine1: string;
    heroLine2: string;
    heroLine3: string;
    heroSub: string;
    heroMeta: string;
    introEyebrow: string;
    introTitle: string;
    introP1: string;
    introP2: string;
    introCode: string;
    principlesEyebrow: string;
    principlesTitle: string;
    businessEyebrow: string;
    businessTitle: string;
    businessSub: string;
    downloadTitle: string;
    downloadSub: string;
    companyEyebrow: string;
    companyTitle: string;
    companySub: string;
  };
  about: {
    eyebrow: string;
    title: string;
    p1: string;
    p2: string;
    quote: string;
    quoteSub: string;
    principlesEyebrow: string;
    principlesTitle: string;
    installEyebrow: string;
    installTitle: string;
    installFooter: string;
    readmeLink: string;
  };
  business: {
    eyebrow: string;
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
    eyebrow: string;
    title: string;
    sub: string;
    windowsButton: string;
    macosButton: string;
    requirementsEyebrow: string;
    requirementsFooter: string;
  };
  company: {
    eyebrow: string;
    role: string;
    tao: string;
    taoSub: string;
    contactLabels: {
      email: string;
      github: string;
      twitter: string;
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
    downloadAll: string;
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
      business: "商业",
      download: "下载",
      pets: "宠物",
      company: "联系",
    },
    footer: {
      tagline: "一个自托管的 AI 工作台。\n不要账户，不做追踪，全部开源。",
      pages: "页面",
      resources: "资源",
      legal: "法律",
      documentation: "文档",
      releases: "版本发布",
      license: "Apache-2.0 许可证",
      security: "安全",
      copyright: `© ${new Date().getFullYear()} LeAgent 贡献者`,
      tao: "道法自然",
      taoSub: "大道至简",
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
      exploreUseCases: "探索应用场景",
      meetDeveloper: "关于开发者",
      startBuilding: "立即开始",
    },
    home: {
      kicker: "大道 \u00B7 the way",
      heroLine1: "强大的技术",
      heroLine2: "极致的简约",
      heroLine3: "完全的自由",
      heroSub: "一个完全跑在你电脑上的 AI 工作台。对话、工作流、80+ 工具，凑成一个你能读、能信的应用。不要账户，不做追踪，全部开源。",
      heroMeta: "Apache-2.0 \u00B7 Python + React \u00B7 默认 SQLite",
      introEyebrow: "介绍",
      introTitle: "对话、工作流、工具 — 装在一个进程里",
      introP1: "LeAgent 把对话式智能体、可视化工作流编辑器，加上 80+ 现成工具，全部塞进一个自托管的进程里跑。会话状态、文件缓存、Token 预算都在一个循环里管 — 状态转换显式可见，代码沙箱执行，Prompt 分层组织。",
      introP2: "不用在几个产品之间来回拼接，也不依赖云。就一份代码 — 你可以打开它、读懂它、按自己的需要改它。",
      introCode: `# 三条命令即可开始
git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      principlesEyebrow: "核心理念",
      principlesTitle: "几件我们不愿让步的事",
      businessEyebrow: "应用场景",
      businessTitle: "为开发者、小团队和默默做事的人而生",
      businessSub: "不管你是一个人在折腾，还是给小团队部署 — LeAgent 都尽量不挡你的路。没有企业版的繁琐流程，也不必走 IT 审批。",
      downloadTitle: "随时可以跑起来",
      downloadSub: "Linux、macOS、Windows 都支持。一个脚本装好，一行命令启动。",
      companyEyebrow: "用心做的东西",
      companyTitle: "一个人在做，做在明处",
      companySub: "LeAgent 是一个人独立开发的项目。代价就是诚实 — 不增长黑客、不埋点、没有藏起来的盘算。",
    },
    about: {
      eyebrow: "关于",
      title: "软件即工艺，\n而非服务",
      p1: "LeAgent 是一位独立开发者一个人做的项目。没有投资人要交代，没有增长曲线要好看，也没有想留住你的暗黑模式。每一个选择只为两件事 — 让代码清晰，让你保有主动权。",
      p2: "代码就是产品，文档就是营销。透明不是写出来的政策 — 它就是这套软件本来的样子。",
      quote: "\u201C道可道，非常道。\u201D",
      quoteSub: "好的软件不用解释 — 它靠开放赢得信任。",
      principlesEyebrow: "核心理念",
      principlesTitle: "几件我们不愿让步的事",
      installEyebrow: "快速开始",
      installTitle: "安装与运行",
      installFooter: "需要 Python 3.11+、Node.js 20+ 以及约 4 GB 内存。详见",
      readmeLink: "README",
    },
    business: {
      eyebrow: "商业",
      title: "为开发者、小团队\n与默默做事的人而生",
      sub: "这不是传统意义上的企业软件，更像是一件工坊里的工具 — 给那些宁愿自己拥有、也不愿租用的人。一个人用也好，几个人的小团队用也好，形状都是一样的。",
      useCasesEyebrow: "应用场景",
      useCasesTitle: "同一套工具，不同的规模",
      capabilitiesEyebrow: "底层能力",
      capabilitiesTitle: "盒子里实际有什么",
      ctaTitle: "现在就开始动手",
      ctaSub: "不打销售电话，也没有试用期。把仓库 clone 下来，配好 API Key，跑一下启动脚本就行。",
    },
    downloadPage: {
      eyebrow: "下载",
      title: "获取 LeAgent",
      sub: "选你的平台。一个脚本装好，一行命令启动。",
      windowsButton: "下载 Windows 版",
      macosButton: "下载 macOS 版",
      requirementsEyebrow: "系统要求",
      requirementsFooter: "默认数据库是 SQLite — 零配置开箱即用。需要时再换成 PostgreSQL + Milvus，启用向量化的智能体记忆。",
    },
    company: {
      eyebrow: "开发者",
      role: "由一个人开发，由一个人维护",
      tao: "道法自然",
      taoSub: "大道至简，万物归一",
      contactLabels: {
        email: "邮箱",
        github: "GitHub",
        twitter: "X / Twitter",
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
      wallpapersSub: "为 LeAgent 桌面挑的几张极简壁纸，4K 和 5K 两个分辨率。点一下就能下载。",
      wallpapers: [
        { title: "玄空", tag: "深空 · 4K", swatch: "linear-gradient(135deg, #0a1428 0%, #1c2440 50%, #322048 100%)" },
        { title: "青山", tag: "山水 · 5K", swatch: "linear-gradient(160deg, #1a3a3a 0%, #3a6868 50%, #6a9a9a 100%)" },
        { title: "朱砂", tag: "霁色 · 4K", swatch: "linear-gradient(140deg, #2a1818 0%, #6a3024 50%, #c25a3a 100%)" },
        { title: "素纸", tag: "白昼 · 5K", swatch: "linear-gradient(150deg, #f5f0e6 0%, #e6dcc8 50%, #c8b89a 100%)" },
        { title: "墨韵", tag: "夜色 · 4K", swatch: "linear-gradient(135deg, #0a0a0d 0%, #1a1a22 50%, #2a2a36 100%)" },
        { title: "苍穹", tag: "天青 · 5K", swatch: "linear-gradient(160deg, #1a3a5c 0%, #2a6a96 50%, #5ca8d6 100%)" },
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
      downloadAll: "打包下载全部",
      placeholderNote: "下载链接指向 GitHub Releases — 正式资源跟随公开版本一起发布。",
    },
    principles: [
      {
        icon: "⊘",
        title: "无账户体系",
        short: "下载、运行、开用。没有注册流程，也没有用户表要维护。",
        long: "LeAgent 跑在你的电脑或自己的服务器上，不用任何注册流程。没有云账户，没有订阅墙，也不必管理用户列表。整套系统就是你自己的。",
      },
      {
        icon: "◇",
        title: "无追踪",
        short: "不埋点，不收集，不上报。你的数据始终留在你的机器上。",
        long: "没有埋点，没有崩溃回传，也没有第三方脚本。所有外发请求都只去你指定的地方 — 通常就是你自己选的 LLM 接口。",
      },
      {
        icon: "◈",
        title: "完全开源",
        short: "Apache-2.0。每一行代码都能读。欢迎 Fork、欢迎扩展、欢迎贡献。",
        long: "后端、前端、工具、工作流 — 全部以 Apache-2.0 协议开源。每一次提交都是公开的。可审计性不是宣传口号，而是仓库本身的样子。",
      },
      {
        icon: "⬡",
        title: "开发者优先",
        short: "CLI 优先，工具可拼可拆，本身就是为折腾而设计的。",
        long: "15 个分类下的 80+ 工具，含 23 个命令组的 CLI，YAML 工作流，声明式规则，还有可以随手编辑、热加载的 Prompt 模板。为喜欢看源码的人而准备。",
      },
      {
        icon: "◉",
        title: "隐私优先",
        short: "默认就是自己托管。你的数据，你的环境，按你的规矩来。",
        long: "默认存储是本地 SQLite — 不依赖任何外部服务。需要规模化时再换上 PostgreSQL 和 Milvus。文件路径有沙箱，附件走签名 URL。整套架构默认网络环境并不友好。",
      },
    ],
    useCases: [
      {
        title: "个人 Copilot",
        description: "一个住在你笔记本里的私人助手。帮你起草文稿、看表格、跑重复的活 — 而且它还记得你上次聊到哪里。",
      },
      {
        title: "小团队工作流",
        description: "把每周都要跑的事画成流程图：报表生成、数据核对、消息分发。自托管、有版本、随时可查。",
      },
      {
        title: "基础设施自动化",
        description: "沙箱化的代码执行、80+ 可组合工具、Webhook 触发、Cron 调度。把 LLM 接进你现有的系统，不被任何一家云锁死。",
      },
    ],
    capabilities: [
      { title: "QueryEngine 编排", description: "会话级状态、流式输出、显式的 Terminal/Continue 转换，加上可注入的 LLM 依赖。核心循环是那种你真的能读懂、能测试的代码。" },
      { title: "80+ 领域工具", description: "文档解析、网页自动化、代码执行、数据库查询、图表、生成式 UI — 都从同一个工具执行器跑，路径全程沙箱化。" },
      { title: "可视化工作流构建器", description: "基于 ReactFlow 的拖拽流程，背后是干净的 YAML。Cron、Webhook，以及新工具加入时自动生成的类型化节点。" },
      { title: "认知记忆", description: "三个存储协同工作 — 情景（过往轮次）、语义（提取出的事实）、程序（工具结果）。混合检索，按时间加权重排。" },
      { title: "分层 Prompt 系统", description: "八层 Prompt 构建器，自带 Token 预算、SHA-256 指纹、按提供商渲染，正在编辑的模板还能热加载。" },
      { title: "多提供商 LLM", description: "DeepSeek、OpenAI、Anthropic、DashScope、Azure、Ollama、vLLM。按层路由、模型别名自动适配，Key 你自己带。" },
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
        steps: `# 克隆并启动
curl -fsSL ${INSTALL_SH_URL} | bash
cd ~/leagent-desktop
./start.sh`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      },
      macos: {
        label: "macOS",
        steps: `# 克隆并启动
curl -fsSL ${INSTALL_SH_URL} | bash
cd ~/leagent-desktop
./start.sh`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      },
      windows: {
        label: "Windows",
        steps: `# PowerShell（如需要请以管理员身份运行）
iwr -useb ${INSTALL_PS1_URL} | iex
cd $HOME\\leagent-desktop
.\\start.ps1`,
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
      business: "Business",
      download: "Download",
      pets: "Pets",
      company: "Company",
    },
    footer: {
      tagline: "A self-hosted AI workspace.\nNo accounts. No tracking. Fully open-source.",
      pages: "Pages",
      resources: "Resources",
      legal: "Legal",
      documentation: "Documentation",
      releases: "Releases",
      license: "Apache-2.0 License",
      security: "Security",
      copyright: `\u00A9 ${new Date().getFullYear()} LeAgent contributors`,
      tao: "\u9053\u6CD5\u81EA\u7136",
      taoSub: "The way follows what is natural",
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
      exploreUseCases: "Explore use cases",
      meetDeveloper: "Meet the developer",
      startBuilding: "Start building today",
    },
    home: {
      kicker: "the way \u00B7 \u9053",
      heroLine1: "Powerful technology.",
      heroLine2: "Absolute simplicity.",
      heroLine3: "Complete freedom.",
      heroSub: "A self-hosted AI workspace that runs entirely on your machine. Chat, workflows, and a deep toolkit \u2014 all in one app you can read and trust. No accounts, no tracking, fully open-source.",
      heroMeta: "Apache-2.0 \u00B7 Python + React \u00B7 SQLite by default",
      introEyebrow: "introduction",
      introTitle: "Chat, workflows, and tools \u2014 all in one place",
      introP1: "LeAgent brings together a chat-style agent, a visual workflow builder, and 80+ ready-made tools \u2014 all running together as a single self-hosted process. Session state, file caching, and token budgets are handled in one loop: explicit transitions, sandboxed execution, layered prompts.",
      introP2: "Nothing to wire up between vendors. Nothing in the cloud. Just one codebase you can open, read, and shape to your own needs.",
      introCode: `# Get started in three commands
git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      principlesEyebrow: "core principles",
      principlesTitle: "A few things we won\u2019t bend on",
      businessEyebrow: "use cases",
      businessTitle: "For builders, small teams, and quiet operators",
      businessSub: "Whether you\u2019re tinkering on your own or rolling it out for a small team, LeAgent tries to stay out of your way \u2014 no enterprise overhead, no IT runaround.",
      downloadTitle: "Ready to run",
      downloadSub: "Linux, macOS, and Windows. One script to install, one command to start.",
      companyEyebrow: "made with care",
      companyTitle: "Built by one person, in the open",
      companySub: "LeAgent is a one-person project. The trade-off is honesty \u2014 no growth hacks, no telemetry, no hidden agenda.",
    },
    about: {
      eyebrow: "about",
      title: "Software as craft,\nnot as service",
      p1: "LeAgent is a one-person project. No investors to please, no growth chart to game, no dark patterns to keep you hooked. Every choice gets made for one reason \u2014 keeping the code clear and keeping you in control.",
      p2: "The code is the product. The docs are the marketing. Transparency isn\u2019t a policy here \u2014 it\u2019s just how the thing is built.",
      quote: "\u201CThe Tao that can be told is not the eternal Tao.\u201D",
      quoteSub: "Good software doesn\u2019t need to explain itself; openness earns the trust.",
      principlesEyebrow: "core principles",
      principlesTitle: "A few things we won\u2019t bend on",
      installEyebrow: "get started",
      installTitle: "Install & Run",
      installFooter: "Requires Python 3.11+, Node.js 20+, and ~4 GB RAM. See the",
      readmeLink: "README",
    },
    business: {
      eyebrow: "business",
      title: "For builders, small teams,\nand quiet operators",
      sub: "This isn\u2019t enterprise software in the usual sense \u2014 it\u2019s more like a workshop tool, for people who\u2019d rather own their stack than rent it. Solo or small team, the shape stays the same.",
      useCasesEyebrow: "use cases",
      useCasesTitle: "Same tool, different scale",
      capabilitiesEyebrow: "under the hood",
      capabilitiesTitle: "What\u2019s actually in the box",
      ctaTitle: "Start building today",
      ctaSub: "No sales calls, no trials. Clone the repo, set your API key, run the start script.",
    },
    downloadPage: {
      eyebrow: "download",
      title: "Get LeAgent",
      sub: "Pick your platform. One script gets it installed, one command gets it running.",
      windowsButton: "Download for Windows",
      macosButton: "Download for macOS",
      requirementsEyebrow: "system requirements",
      requirementsFooter: "SQLite is the default \u2014 nothing to set up. If you outgrow it, swap in PostgreSQL + Milvus when you\u2019re ready.",
    },
    company: {
      eyebrow: "the maker",
      role: "Built and maintained by one person",
      tao: "\u9053\u6CD5\u81EA\u7136",
      taoSub: "The way follows what is natural",
      contactLabels: {
        email: "Email",
        github: "GitHub",
        twitter: "X / Twitter",
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
      wallpapersSub: "A small set of minimal wallpapers, tuned to feel at home behind LeAgent. 4K and 5K. Click one to download.",
      wallpapers: [
        { title: "Xuan", tag: "Deep space · 4K", swatch: "linear-gradient(135deg, #0a1428 0%, #1c2440 50%, #322048 100%)" },
        { title: "Qing Shan", tag: "Jade mountain · 5K", swatch: "linear-gradient(160deg, #1a3a3a 0%, #3a6868 50%, #6a9a9a 100%)" },
        { title: "Vermillion", tag: "Sunset · 4K", swatch: "linear-gradient(140deg, #2a1818 0%, #6a3024 50%, #c25a3a 100%)" },
        { title: "Raw Silk", tag: "Daylight · 5K", swatch: "linear-gradient(150deg, #f5f0e6 0%, #e6dcc8 50%, #c8b89a 100%)" },
        { title: "Ink Mood", tag: "Night · 4K", swatch: "linear-gradient(135deg, #0a0a0d 0%, #1a1a22 50%, #2a2a36 100%)" },
        { title: "Cang", tag: "Heaven cyan · 5K", swatch: "linear-gradient(160deg, #1a3a5c 0%, #2a6a96 50%, #5ca8d6 100%)" },
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
      downloadAll: "Download all as ZIP",
      placeholderNote: "Downloads point to GitHub Releases — the real assets land with the public release.",
    },
    principles: [
      {
        icon: "⊘",
        title: "No Account System",
        short: "Just download it and start using it. No sign-up walls, no user table to babysit.",
        long: "LeAgent runs on your laptop or your own server. Nothing to sign up for, nothing to renew, no users to manage. The whole thing is yours.",
      },
      {
        icon: "◇",
        title: "No Tracking",
        short: "No telemetry, no analytics, no pings home. Your data stays on your machine.",
        long: "Nothing dials home. No analytics beacons, no crash reporters, no third-party scripts. Outbound calls go where you tell them \u2014 usually just your chosen LLM.",
      },
      {
        icon: "◈",
        title: "Fully Open-Source",
        short: "Apache-2.0. Read every line. Fork it, extend it, send a PR.",
        long: "Backend, frontend, tools, workflows \u2014 all of it, Apache-2.0. Every commit is out in the open. Auditability isn\u2019t a slogan here; it\u2019s just how the repo works.",
      },
      {
        icon: "⬡",
        title: "Developer-Focused",
        short: "CLI-first, composable tools, hackable on purpose.",
        long: "80+ tools across 15 categories, a CLI with 23 command groups, YAML workflows, declarative rules, and prompts you can edit and reload on the fly. Made for people who like to look under the hood.",
      },
      {
        icon: "◉",
        title: "Privacy-First",
        short: "Self-hosted by default \u2014 your data, your infrastructure, your call.",
        long: "Default storage is local SQLite \u2014 no external services needed. Need to scale? Plug in PostgreSQL and Milvus. Files stay sandboxed, attachments use signed URLs, and the whole thing assumes the network around it isn\u2019t friendly.",
      },
    ],
    useCases: [
      {
        title: "Personal copilot",
        description: "A private assistant that lives on your laptop. Draft documents, dig through spreadsheets, knock out the boring stuff \u2014 and it remembers what you were working on last time.",
      },
      {
        title: "Small team workflows",
        description: "Drag-and-drop pipelines for the work you run every week: reports, data checks, alerts. Self-hosted, version-controlled, and easy to audit.",
      },
      {
        title: "Infrastructure automation",
        description: "Sandboxed code execution, 80+ composable tools, webhooks, and cron. Wire an LLM into the systems you already run \u2014 without getting locked into anyone\u2019s cloud.",
      },
    ],
    capabilities: [
      { title: "QueryEngine orchestration", description: "Session-scoped state, streaming output, explicit Terminal/Continue transitions, and injectable LLM dependencies. The core loop is something you can actually read and test." },
      { title: "80+ domain tools", description: "Document parsing, web automation, code execution, database queries, charts, generative UI \u2014 all served through one executor with proper path sandboxing." },
      { title: "Visual workflow builder", description: "Drag-and-drop pipelines (ReactFlow) backed by plain YAML. Cron, webhooks, and typed nodes that get auto-generated as you add new tools." },
      { title: "Cognitive memory", description: "Three stores working together \u2014 episodic (past turns), semantic (extracted facts), and procedural (tool outcomes). Hybrid search with recency-weighted reranking." },
      { title: "Layered prompt system", description: "Eight-layer prompt builder with token budgets, SHA-256 fingerprints, per-provider rendering, and hot-reload for the templates you\u2019re editing." },
      { title: "Multi-provider LLM", description: "DeepSeek, OpenAI, Anthropic, DashScope, Azure, Ollama, vLLM. Tiered routing, automatic model aliases \u2014 bring your own keys." },
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
        steps: `# Clone and start
curl -fsSL ${INSTALL_SH_URL} | bash
cd ~/leagent-desktop
./start.sh`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      },
      macos: {
        label: "macOS",
        steps: `# Clone and start
curl -fsSL ${INSTALL_SH_URL} | bash
cd ~/leagent-desktop
./start.sh`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
./start.sh`,
      },
      windows: {
        label: "Windows",
        steps: `# PowerShell (run as Administrator if needed)
iwr -useb ${INSTALL_PS1_URL} | iex
cd $HOME\\leagent-desktop
.\\start.ps1`,
        fromSource: `git clone ${REPO_URL}.git
cd LeAgent
.\\start.ps1`,
      },
    },
  },
};
