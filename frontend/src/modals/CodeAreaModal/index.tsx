import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { cn } from '@/lib/utils';

interface CodeAreaModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  initialCode?: string;
  initialLanguage?: string;
  onSave: (code: string, language: string) => void;
  readOnly?: boolean;
}

const languages = [
  { value: 'javascript', label: 'JavaScript' },
  { value: 'typescript', label: 'TypeScript' },
  { value: 'python', label: 'Python' },
  { value: 'json', label: 'JSON' },
  { value: 'yaml', label: 'YAML' },
  { value: 'html', label: 'HTML' },
  { value: 'css', label: 'CSS' },
  { value: 'sql', label: 'SQL' },
  { value: 'bash', label: 'Bash' },
  { value: 'markdown', label: 'Markdown' },
];

const syntaxColors: Record<string, Record<string, string>> = {
  keyword: {
    javascript: 'text-blue-400',
    typescript: 'text-blue-400',
    python: 'text-blue-400',
    sql: 'text-blue-400',
    default: 'text-blue-400',
  },
  string: {
    default: 'text-green-400',
  },
  comment: {
    default: 'text-gray-500',
  },
  number: {
    default: 'text-orange-400',
  },
  function: {
    default: 'text-blue-400',
  },
};

const keywordPatterns: Record<string, RegExp> = {
  javascript: /\b(const|let|var|function|return|if|else|for|while|class|import|export|from|async|await|try|catch|throw|new|this|typeof|instanceof)\b/g,
  typescript: /\b(const|let|var|function|return|if|else|for|while|class|import|export|from|async|await|try|catch|throw|new|this|typeof|instanceof|interface|type|extends|implements)\b/g,
  python: /\b(def|class|if|elif|else|for|while|return|import|from|as|try|except|raise|with|yield|async|await|None|True|False|and|or|not|in|is)\b/g,
  sql: /\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TABLE|INDEX|JOIN|LEFT|RIGHT|INNER|OUTER|ON|AND|OR|NOT|NULL|AS|ORDER|BY|GROUP|HAVING|LIMIT|OFFSET)\b/gi,
  default: /\b(function|return|if|else|for|while|class)\b/g,
};

export const CodeAreaModal = ({
  isOpen,
  onClose,
  title,
  initialCode = '',
  initialLanguage = 'javascript',
  onSave,
  readOnly = false,
}: CodeAreaModalProps) => {
  const { t } = useTranslation();
  const [code, setCode] = useState(initialCode);
  const [language, setLanguage] = useState(initialLanguage);
  const [lineNumbers, setLineNumbers] = useState<number[]>([]);

  useEffect(() => {
    setCode(initialCode);
    setLanguage(initialLanguage);
  }, [initialCode, initialLanguage, isOpen]);

  useEffect(() => {
    const lines = code.split('\n').length;
    setLineNumbers(Array.from({ length: lines }, (_, i) => i + 1));
  }, [code]);

  const highlightCode = useCallback(
    (text: string) => {
      const pattern = keywordPatterns[language] || keywordPatterns.default;
      let highlighted = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      if (syntaxColors.string) {
        highlighted = highlighted.replace(
          /(["'`])(?:(?!\1)[^\\]|\\.)*\1/g,
          `<span class="${syntaxColors.string.default}">$&</span>`
        );
      }

      if (syntaxColors.comment) {
        highlighted = highlighted.replace(
          /\/\/.*$/gm,
          `<span class="${syntaxColors.comment.default}">$&</span>`
        );

        highlighted = highlighted.replace(
          /#.*$/gm,
          `<span class="${syntaxColors.comment.default}">$&</span>`
        );
      }

      if (syntaxColors.number) {
        highlighted = highlighted.replace(
          /\b\d+\.?\d*\b/g,
          `<span class="${syntaxColors.number.default}">$&</span>`
        );
      }

      if (pattern && syntaxColors.keyword) {
        highlighted = highlighted.replace(pattern, (match) => {
          return `<span class="${syntaxColors.keyword![language] || syntaxColors.keyword!.default}">${match}</span>`;
        });
      }

      return highlighted;
    },
    [language]
  );

  const handleSave = () => {
    onSave(code, language);
    onClose();
  };

  const footer = readOnly ? (
    <Button onClick={onClose}>{t('common.close')}</Button>
  ) : (
    <>
      <Button variant="outline" onClick={onClose}>
        {t('common.cancel')}
      </Button>
      <Button onClick={handleSave}>{t('common.save')}</Button>
    </>
  );

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={title || t('modals.code.title')}
      size="full"
      footer={footer}
    >
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="w-48">
            <Select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              disabled={readOnly}
            >
              {languages.map((lang) => (
                <option key={lang.value} value={lang.value}>
                  {lang.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="text-sm text-muted-foreground">
            {t('modals.code.lines', { count: lineNumbers.length })}
          </div>
        </div>

        <div className="relative rounded-lg overflow-hidden border border-gray-300 dark:border-gray-600">
          <div className="flex bg-gray-900 min-h-[400px] max-h-[60vh] overflow-auto">
            <div className="flex-shrink-0 py-4 px-2 bg-gray-800 text-gray-500 text-right text-sm font-mono select-none">
              {lineNumbers.map((num) => (
                <div key={num} className="leading-6 h-6">
                  {num}
                </div>
              ))}
            </div>
            <div className="relative flex-1">
              <textarea
                value={code}
                onChange={(e) => setCode(e.target.value)}
                readOnly={readOnly}
                spellCheck={false}
                className={cn(
                  'absolute inset-0 w-full h-full p-4 font-mono text-sm leading-6',
                  'bg-transparent text-transparent caret-white',
                  'resize-none outline-none',
                  readOnly && 'cursor-default'
                )}
                style={{ WebkitTextFillColor: 'transparent' }}
              />
              <pre
                className="p-4 font-mono text-sm leading-6 text-gray-100 pointer-events-none whitespace-pre-wrap break-words"
                dangerouslySetInnerHTML={{ __html: highlightCode(code) }}
              />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>Tab = 2 {t('modals.code.spaces')}</span>
          <span>UTF-8</span>
          <span>{language.toUpperCase()}</span>
        </div>
      </div>
    </BaseModal>
  );
};

export default CodeAreaModal;
