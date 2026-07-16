/**
 * Read-only viewer for a single file inside a project folder.
 *
 * Wraps the existing :class:`CodeBlock` so highlight.js handles
 * tokenisation while this component owns the toolbar (history toggle,
 * "send to coding agent", copy path, status). Binary / truncated
 * files render as a friendly placeholder instead of a code block.
 */
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Copy, History, Send } from 'lucide-react';
import { Button, Badge } from '@/components/ui';
import { CodeBlock } from '@/components/common/CodeBlock';
import { useProjectFile } from '@/hooks/useProjectFolder';
import { useChatDraftStore } from '@/stores/chatDraft';
import { extToLanguage } from './extToLanguage';

interface ProjectFileViewerProps {
  folderId: string;
  folderName: string;
  projectPath: string | null;
  filePath: string | null;
  onOpenHistory: () => void;
}

export default function ProjectFileViewer({
  folderId,
  folderName,
  projectPath,
  filePath,
  onOpenHistory,
}: ProjectFileViewerProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setProjectFolder = useChatDraftStore((s) => s.setProjectFolderContext);
  const pushInsert = useChatDraftStore((s) => s.pushInsert);

  const { data, isLoading, isError, error } = useProjectFile(folderId, filePath);

  if (!filePath) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
        {t('folders.project.viewer.empty', {
          defaultValue: 'Select a file from the tree to preview it here.',
        })}
      </div>
    );
  }

  const handleSendToCodingAgent = () => {
    setProjectFolder(folderId, folderName, projectPath);
    pushInsert(
      t('folders.project.viewer.sendPrompt', {
        defaultValue:
          'Open `{{path}}` in the active project, summarise what it does, and propose any improvements.',
        path: filePath,
      }) as string,
    );
    navigate('/');
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-surface-sunken/40">
        <span className="font-mono text-xs truncate" title={filePath}>
          {filePath}
        </span>
        {data?.encoding && (
          <Badge variant="outline" className="text-[10px]">
            {data.encoding}
          </Badge>
        )}
        {data?.is_binary && (
          <Badge variant="warning" className="text-[10px]">
            {t('folders.project.viewer.binary', { defaultValue: 'binary' })}
          </Badge>
        )}
        {data?.truncated && (
          <Badge variant="warning" className="text-[10px]">
            {t('folders.project.viewer.truncated', { defaultValue: 'truncated' })}
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('folders.project.viewer.copyPath', { defaultValue: 'Copy path' })}
            onClick={() => navigator.clipboard?.writeText(filePath)}
          >
            <Copy className="w-3.5 h-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onOpenHistory}
            leftIcon={<History className="w-3.5 h-3.5" />}
          >
            {t('folders.project.viewer.history', { defaultValue: 'History' })}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleSendToCodingAgent}
            leftIcon={<Send className="w-3.5 h-3.5" />}
          >
            {t('folders.project.viewer.send', { defaultValue: 'Ask coding agent' })}
          </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {isLoading && (
          <div className="p-4 text-sm text-muted-foreground">
            {t('common.loading', { defaultValue: 'Loading…' })}
          </div>
        )}
        {isError && (
          <div className="p-4 text-sm text-destructive">
            {(error as Error)?.message ?? 'Failed to load file'}
          </div>
        )}
        {data && data.is_binary && (
          <div className="p-4 text-sm text-muted-foreground">
            {t('folders.project.viewer.binaryNotice', {
              defaultValue:
                'This file appears to be binary and cannot be previewed inline.',
            })}
          </div>
        )}
        {data && !data.is_binary && (
          <>
            {data.truncated && (
              <p className="shrink-0 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-800 dark:text-amber-200">
                {t('folders.project.viewer.truncatedNotice', {
                  defaultValue:
                    'File is too large to preview in full. Content below may be truncated.',
                })}
              </p>
            )}
            <CodeBlock
              code={data.content}
              language={extToLanguage(filePath)}
              showLineNumbers
              showLanguage
              showCopyButton
              fill
              className="border-0 rounded-none"
            />
          </>
        )}
      </div>
    </div>
  );
}
