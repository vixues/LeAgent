/**
 * Generate SEO / agent-discovery files into public/ before Vite build.
 * Output is copied to dist/ automatically (Vite public/ root).
 */
import { writeFileSync, mkdirSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(new URL("..", import.meta.url)));
const PUBLIC = join(ROOT, "public");
const REPO_DOCS = join(ROOT, "..", "docs");

const ORIGIN = (
  process.env.VITE_SITE_ORIGIN ?? "https://vixues.com.cn"
).replace(/\/$/, "");

const REPO = (
  process.env.VITE_REPO_URL ?? "https://github.com/vixues/LeAgent"
).replace(/\/$/, "");

const LASTMOD = new Date().toISOString().slice(0, 10);

function write(name, body) {
  const dest = join(PUBLIC, name);
  mkdirSync(dirname(dest), { recursive: true });
  writeFileSync(dest, body.endsWith("\n") ? body : `${body}\n`, "utf8");
  console.log(`generate-seo: wrote ${name}`);
}

function listMdSlugs(dir, { stripZh = false, skipReadme = true } = {}) {
  try {
    return readdirSync(dir)
      .filter((f) => f.endsWith(".md"))
      .filter((f) => !(skipReadme && /^readme\.md$/i.test(f)))
      .map((f) => f.replace(/\.md$/i, ""))
      .map((s) => (stripZh ? s.replace(/_zh$/i, "") : s))
      .filter((s, i, arr) => arr.indexOf(s) === i)
      .sort();
  } catch {
    return [];
  }
}

const interviewSlugs = listMdSlugs(join(REPO_DOCS, "interview"));
const agentSlugs = listMdSlugs(join(REPO_DOCS, "guides", "agent"));
const technicalSlugs = listMdSlugs(join(REPO_DOCS, "technical"), {
  stripZh: true,
  skipReadme: true,
});

/** @type {{ path: string, title: string, priority: string }[]} */
const ROUTES = [
  { path: "/", title: "Home", priority: "1.0" },
  { path: "/about", title: "Features", priority: "0.9" },
  { path: "/workflows", title: "Workflows", priority: "0.9" },
  { path: "/download", title: "Download", priority: "0.85" },
  { path: "/tutorials", title: "Tutorials", priority: "0.95" },
  { path: "/tutorials/intro", title: "System Overview", priority: "0.9" },
  { path: "/tutorials/interview", title: "Interview Prep", priority: "0.88" },
  { path: "/tutorials/agent", title: "Agent Guides", priority: "0.88" },
  {
    path: "/tutorials/technical",
    title: "Technical Docs",
    priority: "0.88",
  },
  { path: "/business", title: "Custom development", priority: "0.7" },
  { path: "/pets", title: "Desktop pets", priority: "0.6" },
  { path: "/company", title: "Contact", priority: "0.6" },
];

for (const slug of interviewSlugs) {
  ROUTES.push({
    path: `/tutorials/interview/${slug}`,
    title: `Interview: ${slug}`,
    priority: "0.75",
  });
}
for (const slug of agentSlugs) {
  ROUTES.push({
    path: `/tutorials/agent/${slug}`,
    title: `Agent guide: ${slug}`,
    priority: "0.75",
  });
}
for (const slug of technicalSlugs) {
  ROUTES.push({
    path: `/tutorials/technical/${slug}`,
    title: `Technical: ${slug}`,
    priority: "0.8",
  });
}

// ── robots.txt ───────────────────────────────────────────────────────────────
write(
  "robots.txt",
  `# LeAgent product site
# ${ORIGIN}

User-agent: *
Allow: /
Allow: /robots.txt
Allow: /agents.txt
Allow: /agents.json
Allow: /llms.txt
Allow: /sitemap.xml
Allow: /tutorials

User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

User-agent: GPTBot
Allow: /
Allow: /agents.txt
Allow: /llms.txt
Allow: /tutorials

User-agent: ChatGPT-User
Allow: /

User-agent: Claude-Web
Allow: /
Allow: /agents.txt
Allow: /llms.txt
Allow: /tutorials

User-agent: anthropic-ai
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Bytespider
Allow: /

User-agent: CCBot
Allow: /

Sitemap: ${ORIGIN}/sitemap.xml
`,
);

// ── agents.txt (agents-txt.com v1.0 discovery) ───────────────────────────────
write(
  "agents.txt",
  `# agents.txt
# Standard: https://agents-txt.com
# JSON: ${ORIGIN}/agents.json

Identity: LeAgent

# Open-source desktop AI agent that gets work done.
# Plans, calls tools, and self-corrects in one agent loop; agentic visual
# workflows; Generative UI; 100+ built-in tools; multi-model routing.
# Self-hostable · Apache-2.0 · ${REPO}

Site: ${ORIGIN}
Repository: ${REPO}
Documentation: ${ORIGIN}/tutorials
Tutorials: ${ORIGIN}/tutorials
Interview: ${ORIGIN}/tutorials/interview
AgentGuides: ${ORIGIN}/tutorials/agent
Technical: ${ORIGIN}/tutorials/technical
Releases: ${REPO}/releases
License: ${REPO}/blob/main/LICENSE

Skills: ${REPO}/blob/main/AGENTS.md
`,
);

// ── agents.json (structured companion) ───────────────────────────────────────
const agentsJson = {
  spec: "https://agents-txt.com",
  version: "1.0",
  generated: LASTMOD,
  identity: {
    name: "LeAgent",
    tagline: "The open-source desktop AI agent that gets work done.",
    url: ORIGIN,
    repository: REPO,
    license: "Apache-2.0",
    languages: ["zh-CN", "en-US"],
  },
  product: {
    category: "desktop-ai-agent",
    deployment: ["self-hosted", "docker", "desktop", "local-dev"],
    highlights: [
      "Agent runtime with plan-tool-self-correct loop",
      "100+ built-in tools across 13 categories",
      "Agentic visual workflows (ReactFlow DAG)",
      "Generative UI streaming to chat",
      "Research Paper Mode",
      "Multi-model routing with failover",
      "Agent Skills v1.0 and MCP",
    ],
  },
  links: {
    home: `${ORIGIN}/`,
    features: `${ORIGIN}/about`,
    workflows: `${ORIGIN}/workflows`,
    download: `${ORIGIN}/download`,
    documentation: `${ORIGIN}/tutorials`,
    tutorials: `${ORIGIN}/tutorials`,
    interview: `${ORIGIN}/tutorials/interview`,
    agent_guides: `${ORIGIN}/tutorials/agent`,
    technical: `${ORIGIN}/tutorials/technical`,
    intro: `${ORIGIN}/tutorials/intro`,
    readme: `${REPO}/blob/main/README.md`,
    readme_zh: `${REPO}/blob/main/README_zh.md`,
    agents_md: `${REPO}/blob/main/AGENTS.md`,
    releases: `${REPO}/releases`,
    install: `${ORIGIN}/install.sh`,
  },
  skills: [
    { url: `${REPO}/blob/main/AGENTS.md`, name: "LeAgent contributor guide" },
  ],
};

write("agents.json", JSON.stringify(agentsJson, null, 2));

// ── llms.txt (LLM-oriented site map) ─────────────────────────────────────────
const interviewLinks = interviewSlugs
  .slice(0, 8)
  .map((s) => `- [${s}](${ORIGIN}/tutorials/interview/${s})`)
  .join("\n");
const agentLinks = agentSlugs
  .slice(0, 12)
  .map((s) => `- [${s}](${ORIGIN}/tutorials/agent/${s})`)
  .join("\n");
const techLinks = technicalSlugs
  .map((s) => `- [${s}](${ORIGIN}/tutorials/technical/${s})`)
  .join("\n");

write(
  "llms.txt",
  `# LeAgent

> Open-source desktop AI agent that gets work done — plans, calls tools, and
> self-corrects; agentic visual workflows; Generative UI; 100+ built-in tools;
> multi-model routing. Self-hostable. Apache-2.0.

LeAgent is a complete agent platform (not a chat wrapper): QueryEngine session
orchestration, 100+ offline tools, ReactFlow workflow engine, Generative UI,
Research Paper Mode, and multi-provider LLM support (DeepSeek, Qwen, OpenAI,
Anthropic, Ollama, vLLM).

## Product pages

- [Home](${ORIGIN}/): Overview, capabilities, and download entry
- [Features](${ORIGIN}/about): Chat, GenUI, code, documents, paper mode, multi-model
- [Workflows](${ORIGIN}/workflows): Visual DAG editor, art-asset pipeline, one engine
- [Download](${ORIGIN}/download): Install scripts and desktop releases
- [Custom development](${ORIGIN}/business): Enterprise delivery and integration
- [Contact](${ORIGIN}/company): Maintainer and community links

## Tutorials & documentation

- [Tutorials hub](${ORIGIN}/tutorials): Interview prep, system overview, technical docs, Agent guides
- [System overview](${ORIGIN}/tutorials/intro): README-based product and architecture intro
- [Interview prep](${ORIGIN}/tutorials/interview): Agent interview Q&A
- [Agent guides](${ORIGIN}/tutorials/agent): 48 progressive engineering tutorials
- [Technical docs](${ORIGIN}/tutorials/technical): Execution topology, SDK, runtime, security

### Interview (sample)

${interviewLinks}

### Agent guides (sample)

${agentLinks}

### Technical references

${techLinks}

## Source

- [GitHub repository](${REPO})
- [README (English)](${REPO}/blob/main/README.md)
- [README (中文)](${REPO}/blob/main/README_zh.md)
- [Contributor guide / AGENTS.md](${REPO}/blob/main/AGENTS.md)
- [Releases](${REPO}/releases)

## Agent discovery

- [agents.txt](${ORIGIN}/agents.txt)
- [agents.json](${ORIGIN}/agents.json)
`,
);

// ── sitemap.xml ──────────────────────────────────────────────────────────────
const urlEntries = ROUTES.map(
  (r) => `  <url>
    <loc>${ORIGIN}${r.path === "/" ? "/" : r.path}</loc>
    <lastmod>${LASTMOD}</lastmod>
    <changefreq>${r.priority >= "0.9" ? "weekly" : "monthly"}</changefreq>
    <priority>${r.priority}</priority>
  </url>`,
).join("\n");

write(
  "sitemap.xml",
  `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urlEntries}
</urlset>
`,
);

console.log(
  `generate-seo: origin=${ORIGIN} routes=${ROUTES.length} (interview=${interviewSlugs.length} agent=${agentSlugs.length} tech=${technicalSlugs.length})`,
);
