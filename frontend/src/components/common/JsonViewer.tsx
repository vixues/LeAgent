import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { ChevronRight, ChevronDown, Copy, Check } from 'lucide-react';

interface JsonViewerProps {
  data: unknown;
  className?: string;
  defaultExpanded?: boolean;
  maxHeight?: string;
  label?: string;
}

function JsonNode({
  value,
  depth = 0,
  defaultExpanded = true,
}: {
  value: unknown;
  depth?: number;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded || depth < 2);

  if (value === null) return <span className="text-gray-400">null</span>;
  if (value === undefined) return <span className="text-gray-400">undefined</span>;
  if (typeof value === 'boolean') {
    return <span className="text-blue-600 dark:text-blue-400">{String(value)}</span>;
  }
  if (typeof value === 'number') {
    return <span className="text-blue-600 dark:text-blue-400">{value}</span>;
  }
  if (typeof value === 'string') {
    return <span className="text-green-600 dark:text-green-400">"{value}"</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-gray-500">[]</span>;
    return (
      <span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="inline-flex items-center text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
        >
          {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          <span className="ml-0.5 text-gray-500">[{value.length}]</span>
        </button>
        {expanded && (
          <span className="block ml-4">
            {value.map((item, i) => (
              <span key={i} className="block">
                <span className="text-gray-400 mr-2">{i}:</span>
                <JsonNode value={item} depth={depth + 1} defaultExpanded={defaultExpanded} />
                {i < value.length - 1 && <span className="text-gray-400">,</span>}
              </span>
            ))}
          </span>
        )}
      </span>
    );
  }
  if (typeof value === 'object') {
    const keys = Object.keys(value as Record<string, unknown>);
    if (keys.length === 0) return <span className="text-gray-500">{'{}'}</span>;
    return (
      <span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="inline-flex items-center text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
        >
          {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          <span className="ml-0.5 text-gray-500">{'{'}…{'}'}</span>
        </button>
        {expanded && (
          <span className="block ml-4">
            {keys.map((key, i) => (
              <span key={key} className="block">
                <span className="text-orange-600 dark:text-orange-400">"{key}"</span>
                <span className="text-gray-500 mx-1">:</span>
                <JsonNode
                  value={(value as Record<string, unknown>)[key]}
                  depth={depth + 1}
                  defaultExpanded={defaultExpanded}
                />
                {i < keys.length - 1 && <span className="text-gray-400">,</span>}
              </span>
            ))}
          </span>
        )}
      </span>
    );
  }
  return <span className="text-gray-600 dark:text-gray-400">{String(value)}</span>;
}

function JsonViewer({ data, className, defaultExpanded = true, maxHeight, label }: JsonViewerProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div
      className={cn(
        'rounded-lg border border-gray-200 dark:border-gray-700',
        'bg-gray-50 dark:bg-surface',
        className
      )}
    >
      {label && (
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700">
          <span className="text-xs font-medium text-gray-600 dark:text-gray-400">{label}</span>
          <button
            onClick={handleCopy}
            className="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            title={t('common.copyJson')}
          >
            {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      )}
      <div
        className="p-3 overflow-auto font-mono text-xs leading-5"
        style={maxHeight ? { maxHeight } : undefined}
      >
        {data === null || data === undefined ? (
          <span className="text-gray-400">{t('common.jsonViewerNoData')}</span>
        ) : (
          <JsonNode value={data} defaultExpanded={defaultExpanded} />
        )}
      </div>
    </div>
  );
}
JsonViewer.displayName = 'JsonViewer';

export { JsonViewer };
