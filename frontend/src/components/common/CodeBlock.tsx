import { forwardRef, useState, type HTMLAttributes, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-react';
import hljs from 'highlight.js';
import 'highlight.js/styles/github-dark.css';
import { useTranslation } from 'react-i18next';

interface CodeBlockProps extends HTMLAttributes<HTMLDivElement> {
  code: string;
  language?: string;
  showLineNumbers?: boolean;
  showCopyButton?: boolean;
  showLanguage?: boolean;
  maxHeight?: number | string;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  highlightLines?: number[];
}

const CodeBlock = forwardRef<HTMLDivElement, CodeBlockProps>(
  (
    {
      className,
      code,
      language = 'plaintext',
      showLineNumbers = true,
      showCopyButton = true,
      showLanguage = true,
      maxHeight,
      collapsible = false,
      defaultCollapsed = false,
      highlightLines = [],
      ...props
    },
    ref
  ) => {
    const { t } = useTranslation();
    const [copied, setCopied] = useState(false);
    const [collapsed, setCollapsed] = useState(defaultCollapsed);
    const [highlightedCode, setHighlightedCode] = useState('');

    useEffect(() => {
      try {
        const result = language && hljs.getLanguage(language)
          ? hljs.highlight(code, { language })
          : hljs.highlightAuto(code);
        setHighlightedCode(result.value);
      } catch {
        setHighlightedCode(code);
      }
    }, [code, language]);

    const handleCopy = async () => {
      try {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error('Failed to copy:', err);
      }
    };

    const lines = code.split('\n');
    const displayLanguage = language === 'plaintext' ? 'text' : language;

    return (
      <div
        ref={ref}
        className={cn(
          'rounded-lg overflow-hidden',
          'border border-gray-200 dark:border-gray-700',
          'bg-gray-50 dark:bg-surface',
          className
        )}
        {...props}
      >
        {(showLanguage || showCopyButton || collapsible) && (
          <div
            className={cn(
              'flex items-center justify-between px-4 py-2',
              'bg-gray-100 dark:bg-surface',
              'border-b border-gray-200 dark:border-gray-700'
            )}
          >
            <div className="flex items-center gap-2">
              {showLanguage && (
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  {displayLanguage}
                </span>
              )}
              {collapsible && (
                <button
                  type="button"
                  onClick={() => setCollapsed(!collapsed)}
                  className={cn(
                    'p-1 rounded-md',
                    'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
                    'hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors'
                  )}
                >
                  {collapsed ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronUp className="w-4 h-4" />
                  )}
                </button>
              )}
            </div>
            {showCopyButton && (
              <button
                type="button"
                onClick={handleCopy}
                className={cn(
                  'flex items-center gap-1 px-2 py-1 rounded-md text-xs',
                  'text-gray-500 dark:text-gray-400',
                  'hover:text-gray-700 dark:hover:text-gray-200',
                  'hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors'
                )}
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    {t('common.copied')}
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    {t('common.copy')}
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {!collapsed && (
          <div
            className="overflow-auto"
            style={maxHeight ? { maxHeight } : undefined}
          >
            <pre className="p-4 m-0 text-sm leading-relaxed">
              <code className={cn('hljs', `language-${language}`)}>
                {showLineNumbers ? (
                  <table className="border-collapse w-full">
                    <tbody>
                      {lines.map((line, index) => {
                        const lineNumber = index + 1;
                        const isHighlighted = highlightLines.includes(lineNumber);
                        return (
                          <tr
                            key={index}
                            className={cn(
                              isHighlighted && 'bg-yellow-100/50 dark:bg-yellow-900/20'
                            )}
                          >
                            <td
                              className={cn(
                                'select-none pr-4 text-right align-top',
                                'text-gray-400 dark:text-gray-600',
                                'border-r border-gray-200 dark:border-gray-700'
                              )}
                              style={{ minWidth: '2.5rem' }}
                            >
                              {lineNumber}
                            </td>
                            <td className="pl-4">
                              <span
                                dangerouslySetInnerHTML={{
                                  __html: hljs.highlight(line || ' ', { language }).value,
                                }}
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                ) : (
                  <span dangerouslySetInnerHTML={{ __html: highlightedCode }} />
                )}
              </code>
            </pre>
          </div>
        )}
      </div>
    );
  }
);

CodeBlock.displayName = 'CodeBlock';

interface InlineCodeProps extends HTMLAttributes<HTMLElement> {}

const InlineCode = forwardRef<HTMLElement, InlineCodeProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <code
        ref={ref}
        className={cn(
          'px-1.5 py-0.5 rounded-md text-sm font-mono',
          'bg-gray-100 dark:bg-surface',
          'text-gray-800 dark:text-gray-200',
          className
        )}
        {...props}
      >
        {children}
      </code>
    );
  }
);

InlineCode.displayName = 'InlineCode';

export { CodeBlock, InlineCode };
