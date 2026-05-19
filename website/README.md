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
```

## Customization

- **Contact details**: edit `src/lib/content.ts` -> `CONTACT` object.
- **Repo URL**: edit `src/i18n/translations.ts` -> `REPO_URL` constant.
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
