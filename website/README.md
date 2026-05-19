# LeAgent Website

Static marketing site built with React 19 + Vite + TypeScript + Tailwind CSS 4.

## Development

```bash
cd website
npm install
npm run dev        # http://localhost:8080
npm run build      # production build -> dist/
npm run preview    # preview production build
npm run typecheck  # type-check without emitting
npm run check:links  # verify external URLs in source
```

`npm run build` runs `prebuild` first, copying `../scripts/install.{sh,ps1,bat}` into `public/` so they are published at the site root (e.g. `https://vixues.com.cn/install.sh`).

## Production deployment

1. Build locally:

```bash
cd website
npm run build
```

2. Upload the entire `dist/` directory to your web server root (Nginx, 宝塔, etc.).

3. Configure Nginx so install scripts are served as plain files **before** the SPA fallback. Otherwise `try_files` may return `index.html` for `/install.sh`, and `curl | bash` will fail:

```nginx
# Install scripts: serve files directly (no SPA fallback)
location ~ ^/install\.(sh|ps1|bat)$ {
    root /path/to/dist;
    default_type text/plain;
    add_header Cache-Control "public, max-age=300";
}

location / {
    root /path/to/dist;
    try_files $uri $uri/ /index.html;
}
```

4. Verify after deploy:

```bash
curl -fsSI https://vixues.com.cn/install.sh | grep -E 'HTTP|content-type'
curl -fsSL https://vixues.com.cn/install.sh | head -5
```

Quick install (shown on the site):

```bash
curl -fsSL https://vixues.com.cn/install.sh | bash
```

## Customization

- **Contact details**: edit `src/lib/content.ts` -> `CONTACT` object.
- **Site / repo URLs**: copy `.env.example` to `.env` and set `VITE_SITE_ORIGIN`, `VITE_REPO_URL`.
- **Favicon**: replace `public/favicon.svg`.
- **Images**: drop screenshots into `public/images/`.

## i18n

- Bilingual: zh-CN (default) and en-US.
- All copy lives in `src/i18n/translations.ts`.
- Language toggle persists to `localStorage` key `leagent-site-language`.

## Themes

- Dark (default) and Light themes.
- Toggle persists to `localStorage` key `leagent-site-theme`.
- CSS tokens in `src/styles/index.css` under `html[data-theme="dark"|"light"]`.
- Pre-hydration script in `index.html` prevents flash on reload.

## External link check

`npm run check:links` scans `src/` and `index.html` for `https://` URLs and probes each with HEAD/GET. GitHub links may fail until the repository is public; placeholder contact URLs in `content.ts` will fail until updated.
