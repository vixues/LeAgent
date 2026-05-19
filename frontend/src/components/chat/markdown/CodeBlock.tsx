import { useState, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Check, Download } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CodeBlockProps {
  children: ReactNode;
  language?: string;
  className?: string;
}

export function CodeBlock({ children, language, className }: CodeBlockProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  const handleCopy = async () => {
    const code = preRef.current?.textContent || '';
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const code = preRef.current?.textContent || '';
    const ext = language ? `.${language}` : '.txt';
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `code${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const label = language ? language : t('common.codeBlockPlainLabel');

  return (
    <div className={cn('chat-code-panel my-3', className)}>
      <div className="chat-code-panel__toolbar" aria-hidden={false}>
        <span className="chat-code-panel__lang">{label}</span>
        <div className="chat-code-panel__actions">
          <button
            type="button"
            onClick={handleDownload}
            className="chat-code-panel__action"
            aria-label={t('common.codeBlockDownload')}
          >
            <Download className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="chat-code-panel__action"
            aria-label={t('common.copyCode', { defaultValue: 'Copy code' })}
          >
            {copied ? (
              <Check className="size-3.5 text-emerald-500 dark:text-emerald-400" />
            ) : (
              <Copy className="size-3.5" />
            )}
          </button>
        </div>
      </div>
      <pre ref={preRef} className="chat-code-panel__pre">
        {children}
      </pre>
    </div>
  );
}
