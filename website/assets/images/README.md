# 图片资源

可将 WebP/PNG 放入本目录，在 React 页面中用：

```tsx
<img src="/your-file.webp" alt="..." loading="lazy" decoding="async" />
```

Vite 会将 `public/` 下文件映射到站点根路径；放在 `public/` 亦可。

推荐命名参见此前约定：`hero-overview.webp`、`agent-demo.webp` 等。
