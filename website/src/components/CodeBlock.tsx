import { useState, useCallback } from "react";
import { cn } from "@/lib/cn";

interface CodeBlockProps {
  code: string;
  lang?: string;
  title?: string;
  className?: string;
}

export function CodeBlock({ code, lang, title, className }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [code]);

  return (
    <div className={cn("code-panel", className)}>
      <div className="code-panel__header">
        <div>
          {title && <p className="code-panel__title">{title}</p>}
          {lang && <p className="code-panel__lang">{lang}</p>}
        </div>
        <button type="button" onClick={copy} className="code-panel__copy">
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre className="code-panel__body">
        <code>{code}</code>
      </pre>
    </div>
  );
}
