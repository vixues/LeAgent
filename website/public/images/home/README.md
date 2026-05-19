# 首页产品界面图（替换说明）

营销站首页 Hero 下方大图从此目录加载。**文件名保持不变**，直接替换文件即可（建议同名覆盖）。

| 文件 | 用途 |
|------|------|
| `leagent-ui-hero.png` | 浅色主题下展示的界面截图（占位已内置） |
| `leagent-ui-hero-dark.png` | 深色主题下展示的界面截图（占位已内置） |
| `leagent-ui-hero-placeholder.png` | 与浅色占位同源备份，可删或忽略 |

当前内置文件为**简易宽幅示意**（浅色底 / 深色底不同文件），非真实产品截图；替换时同名覆盖即可。

## 推荐规格

- **比例**：约 **21:9**（或 16:9）宽幅浏览器窗口截图，与 `.hero-showcase` 一致。
- **宽度**：导出 **1600–2400px** 宽 WebP 或 PNG；可选再提供 `@2x` 时在代码里扩展 `srcSet`。
- **内容**：真实 LeAgent Web 客户端（聊天 / 工作流画布 / 设置任一代表性视图）；避免敏感数据。
- **格式**：优先 **WebP**（体积小）；保留 PNG 作为 fallback 时需同步改 `Home.tsx` 内路径。

替换后若改文件名或增加 `srcSet`，请编辑 `website/src/pages/Home.tsx` 中 `<section className="hero-showcase">` 内的 `<img>`。
