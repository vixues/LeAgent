import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Code2, RefreshCw, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Artifact } from '@/types/artifact';
import { srcDocIframeSandbox } from '@/lib/canvasPreviewJs';

interface SandboxedPreviewProps {
  artifact: Artifact;
  className?: string;
}

const CDN_REACT = 'https://unpkg.com/react@19/umd/react.production.min.js';
const CDN_REACT_DOM =
  'https://unpkg.com/react-dom@19/umd/react-dom.production.min.js';
const CDN_BABEL =
  'https://unpkg.com/@babel/standalone@7/babel.min.js';

const PROFESSIONAL_HEAD = `
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
  <script src="https://cdn.tailwindcss.com"><\/script>
  <script>
  tailwind.config = {
    theme: {
      extend: {
        fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'] },
        colors: {
          primary: {50:'#f0f9ff',100:'#e0f2fe',200:'#bae6fd',300:'#7dd3fc',400:'#38bdf8',500:'#0ea5e9',600:'#0284c7',700:'#0369a1',800:'#075985',900:'#0c4a6e'},
          surface: { DEFAULT:'#ffffff', elevated:'#ffffff', sunken:'#f1f5f9' },
        },
      },
    },
    darkMode: 'media',
  }
  <\/script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
    body { font-family: 'Inter', system-ui, -apple-system, sans-serif; color: #1a1a2e; background: #ffffff; line-height: 1.6; padding: 24px; min-height: 100vh; }
    body::-webkit-scrollbar { width: 0; height: 0; }
    body { scrollbar-width: none; }
    @media (prefers-color-scheme: dark) { body { background: #0f0f1a; color: #f8fafc; } }
    img { max-width: 100%; height: auto; }
    a { color: #0284c7; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .wa-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
    .wa-gradient { background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%); color: #fff; }
    .wa-gradient-warm { background: linear-gradient(135deg, #f97316 0%, #ec4899 100%); color: #fff; }
    .wa-gradient-fresh { background: linear-gradient(135deg, #10b981 0%, #0ea5e9 100%); color: #fff; }
    @media (prefers-color-scheme: dark) { .wa-card { background: #1a1a2e; border-color: #334155; } }
  </style>`;

function buildHtmlDocument(source: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
${PROFESSIONAL_HEAD}
</head>
<body>
${source}
</body>
</html>`;
}

function buildReactDocument(source: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
${PROFESSIONAL_HEAD}
  <style>#root { min-height: 100vh; }</style>
  <script src="${CDN_REACT}"><\/script>
  <script src="${CDN_REACT_DOM}"><\/script>
  <script src="${CDN_BABEL}"><\/script>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel" data-type="module">
${source}

// Auto-mount: look for a default export or an App component
const _exports = typeof App !== 'undefined' ? App : null;
if (_exports) {
  const root = ReactDOM.createRoot(document.getElementById('root'));
  root.render(React.createElement(_exports));
}
  <\/script>
</body>
</html>`;
}

export default function SandboxedPreview({
  artifact,
  className,
}: SandboxedPreviewProps) {
  const { t } = useTranslation();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [key, setKey] = useState(0);
  const [jsEnabled, setJsEnabled] = useState(true);

  const srcDoc = useMemo(() => {
    if (artifact.type === 'react') {
      return buildReactDocument(artifact.content);
    }
    return buildHtmlDocument(artifact.content);
  }, [artifact.content, artifact.type]);

  const handleRefresh = () => setKey((k) => k + 1);

  const handleOpenExternal = () => {
    const blob = new Blob([srcDoc], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };

  return (
    <div className={cn('flex min-h-0 min-w-0 flex-1 basis-0 flex-col', className)}>
      {/* Toolbar */}
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border-subtle flex-shrink-0">
        <span className="text-[11px] font-medium text-muted-foreground-tertiary uppercase tracking-wider flex-1">
          {artifact.type === 'react' ? 'React Preview' : 'HTML Preview'}
        </span>
        <button
          type="button"
          onClick={() => {
            setJsEnabled((v) => !v);
            setKey((k) => k + 1);
          }}
          className={cn(
            'px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide transition-colors',
            jsEnabled
              ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-200'
              : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken',
          )}
          aria-label={jsEnabled ? t('chat.canvas.jsOn') : t('chat.canvas.jsOff')}
          title={jsEnabled ? t('chat.canvas.jsOn') : t('chat.canvas.jsOff')}
        >
          <span className="inline-flex items-center gap-0.5">
            <Code2 className="w-3 h-3" aria-hidden />
            {jsEnabled ? t('chat.canvas.jsOnShort') : t('chat.canvas.jsOffShort')}
          </span>
        </button>
        <button
          type="button"
          onClick={handleRefresh}
          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
          aria-label="Refresh preview"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={handleOpenExternal}
          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
          aria-label="Open in new window"
        >
          <ExternalLink className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Sandboxed iframe — flex-1 basis-0 so preview fills artifact panel */}
      <div className="flex min-h-0 min-w-0 flex-1 basis-0 flex-col bg-white dark:bg-zinc-950">
        <iframe
          ref={iframeRef}
          key={`${key}-${jsEnabled ? 'js' : 'nojs'}`}
          srcDoc={srcDoc}
          sandbox={srcDocIframeSandbox(jsEnabled) || undefined}
          className="min-h-0 min-w-0 w-full flex-1 border-0"
          title={artifact.title}
        />
      </div>
    </div>
  );
}
