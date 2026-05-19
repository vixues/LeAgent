import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs';
import { cn } from '@/lib/utils';

interface TextModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  initialText?: string;
  onSave: (text: string) => void;
  placeholder?: string;
  readOnly?: boolean;
}

const markdownToHtml = (text: string): string => {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  html = html.replace(/^### (.*$)/gm, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>');
  html = html.replace(/^## (.*$)/gm, '<h2 class="text-xl font-semibold mt-4 mb-2">$1</h2>');
  html = html.replace(/^# (.*$)/gm, '<h1 class="text-2xl font-bold mt-4 mb-2">$1</h1>');

  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 bg-surface-sunken rounded text-sm">$1</code>');

  html = html.replace(/^\- (.*$)/gm, '<li class="ml-4">$1</li>');
  html = html.replace(/^\d+\. (.*$)/gm, '<li class="ml-4 list-decimal">$1</li>');

  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-primary-600 hover:underline" target="_blank">$1</a>');

  html = html.replace(/^---$/gm, '<hr class="my-4 border-border" />');

  html = html.replace(/\n/g, '<br />');

  return html;
};

export const TextModal = ({
  isOpen,
  onClose,
  title,
  initialText = '',
  onSave,
  placeholder,
  readOnly = false,
}: TextModalProps) => {
  const { t } = useTranslation();
  const [text, setText] = useState(initialText);
  const [activeTab, setActiveTab] = useState<'edit' | 'preview'>('edit');

  useEffect(() => {
    setText(initialText);
    setActiveTab('edit');
  }, [initialText, isOpen]);

  const handleSave = () => {
    onSave(text);
    onClose();
  };

  const insertFormatting = useCallback(
    (before: string, after: string = before) => {
      const textarea = document.querySelector('textarea[data-text-editor]') as HTMLTextAreaElement;
      if (!textarea) return;

      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const selectedText = text.substring(start, end);
      const newText =
        text.substring(0, start) + before + selectedText + after + text.substring(end);

      setText(newText);

      setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(start + before.length, end + before.length);
      }, 0);
    },
    [text]
  );

  const formatActions = [
    { icon: 'B', title: t('modals.text.bold'), action: () => insertFormatting('**') },
    { icon: 'I', title: t('modals.text.italic'), action: () => insertFormatting('*') },
    { icon: 'H1', title: t('modals.text.heading'), action: () => insertFormatting('# ', '') },
    { icon: '•', title: t('modals.text.list'), action: () => insertFormatting('- ', '') },
    { icon: '<>', title: t('modals.text.code'), action: () => insertFormatting('`') },
    { icon: '🔗', title: t('modals.text.link'), action: () => insertFormatting('[', '](url)') },
  ];

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
      title={title || t('modals.text.title')}
      size="lg"
      footer={footer}
    >
      <div className="space-y-4">
        <Tabs
          defaultValue="edit"
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as 'edit' | 'preview')}
        >
          <div className="flex items-center justify-between mb-4">
            <TabsList>
              <TabsTrigger value="edit" disabled={readOnly}>
                {t('modals.text.edit')}
              </TabsTrigger>
              <TabsTrigger value="preview">{t('modals.text.preview')}</TabsTrigger>
            </TabsList>

            {activeTab === 'edit' && !readOnly && (
              <div className="flex items-center gap-1">
                {formatActions.map((action) => (
                  <button
                    key={action.icon}
                    onClick={action.action}
                    title={action.title}
                    className={cn(
                      'px-2 py-1 text-sm font-medium rounded',
                      'text-muted-foreground',
                      'hover:bg-surface-sunken',
                      'transition-colors'
                    )}
                  >
                    {action.icon}
                  </button>
                ))}
              </div>
            )}
          </div>

          <TabsContent value="edit">
            <textarea
              data-text-editor
              value={text}
              onChange={(e) => setText(e.target.value)}
              readOnly={readOnly}
              placeholder={placeholder || t('modals.text.placeholder')}
              className={cn(
                'w-full h-80 p-4 rounded-lg border text-sm',
                'bg-surface',
                'border-border',
                'focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500',
                'text-foreground resize-none',
                readOnly && 'cursor-default'
              )}
            />
          </TabsContent>

          <TabsContent value="preview">
            <div
              className={cn(
                'w-full h-80 p-4 rounded-lg border overflow-auto',
                'bg-surface-sunken',
                'border-border',
                'text-foreground',
                'prose dark:prose-invert max-w-none'
              )}
            >
              {text ? (
                <div dangerouslySetInnerHTML={{ __html: markdownToHtml(text) }} />
              ) : (
                <p className="text-muted-foreground-tertiary italic">{t('modals.text.noContent')}</p>
              )}
            </div>
          </TabsContent>
        </Tabs>

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {t('modals.text.characters', { count: text.length })}
          </span>
          <span>{t('modals.text.markdownSupported')}</span>
        </div>
      </div>
    </BaseModal>
  );
};

export default TextModal;
