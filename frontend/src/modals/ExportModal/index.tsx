import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

type ExportFormat = 'json' | 'yaml';

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  flowName: string;
  flowData: unknown;
  onExport?: (format: ExportFormat) => void;
}

const jsonToYaml = (obj: unknown, indent = 0): string => {
  const spaces = '  '.repeat(indent);

  if (obj === null || obj === undefined) {
    return 'null';
  }

  if (typeof obj === 'string') {
    if (obj.includes('\n') || obj.includes(':') || obj.includes('#')) {
      return `|\n${obj
        .split('\n')
        .map((line) => `${spaces}  ${line}`)
        .join('\n')}`;
    }
    return obj;
  }

  if (typeof obj === 'number' || typeof obj === 'boolean') {
    return String(obj);
  }

  if (Array.isArray(obj)) {
    if (obj.length === 0) return '[]';
    return obj.map((item) => `\n${spaces}- ${jsonToYaml(item, indent + 1)}`).join('');
  }

  if (typeof obj === 'object') {
    const entries = Object.entries(obj);
    if (entries.length === 0) return '{}';
    return entries
      .map(([key, value]) => {
        const valueStr = jsonToYaml(value, indent + 1);
        if (typeof value === 'object' && value !== null) {
          return `\n${spaces}${key}:${valueStr}`;
        }
        return `\n${spaces}${key}: ${valueStr}`;
      })
      .join('');
  }

  return String(obj);
};

export const ExportModal = ({
  isOpen,
  onClose,
  flowName,
  flowData,
  onExport,
}: ExportModalProps) => {
  const { t } = useTranslation();
  const [format, setFormat] = useState<ExportFormat>('json');
  const [copied, setCopied] = useState(false);

  const getExportContent = (): string => {
    if (format === 'json') {
      return JSON.stringify(flowData, null, 2);
    }
    return jsonToYaml(flowData).trim();
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(getExportContent());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error(t('errors.copyFailed'), err);
    }
  };

  const handleDownload = () => {
    const content = getExportContent();
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${flowName.replace(/\s+/g, '-').toLowerCase()}.${format}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    onExport?.(format);
    onClose();
  };

  const formatOptions: { value: ExportFormat; label: string; icon: string }[] = [
    { value: 'json', label: 'JSON', icon: '{}' },
    { value: 'yaml', label: 'YAML', icon: '---' },
  ];

  const footer = (
    <>
      <Button variant="outline" onClick={onClose}>
        {t('common.cancel')}
      </Button>
      <Button
        variant="secondary"
        onClick={handleCopy}
        leftIcon={
          copied ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
          )
        }
      >
        {copied ? t('common.copied') : t('common.copy')}
      </Button>
      <Button
        onClick={handleDownload}
        leftIcon={
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
            />
          </svg>
        }
      >
        {t('modals.export.download')}
      </Button>
    </>
  );

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={t('modals.export.title')}
      size="lg"
      footer={footer}
    >
      <div className="space-y-4">
        <div>
          <label className="text-sm font-medium text-foreground mb-3 block">
            {t('modals.export.selectFormat')}
          </label>
          <div className="flex gap-3">
            {formatOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => setFormat(option.value)}
                className={cn(
                  'flex-1 p-4 rounded-lg border-2 transition-[color,background-color,border-color,box-shadow,opacity]',
                  format === option.value
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                    : 'border-border hover:border-muted-foreground'
                )}
              >
                <div className="text-2xl font-mono mb-2 text-muted-foreground">
                  {option.icon}
                </div>
                <div className="font-medium text-foreground">
                  {option.label}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-sm font-medium text-foreground mb-2 block">
            {t('modals.export.preview')}
          </label>
          <pre
            className={cn(
              'p-4 rounded-lg bg-gray-900 text-gray-100 text-sm overflow-auto',
              'max-h-80 font-mono'
            )}
          >
            <code>{getExportContent()}</code>
          </pre>
        </div>

        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>
            {t('modals.export.filename')}: {flowName.replace(/\s+/g, '-').toLowerCase()}.{format}
          </span>
        </div>
      </div>
    </BaseModal>
  );
};

export default ExportModal;
