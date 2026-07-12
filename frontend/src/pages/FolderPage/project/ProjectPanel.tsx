/**
 * Right-pane content for a folder running in code-project mode.
 *
 * Composes the file tree (left), file viewer (center), git status
 * strip (top), git history sheet (right slide-over), and a "Run
 * coding agent on this project" CTA in the header. All four
 * sub-components share state through this parent so a click in the
 * tree drives the viewer, and the viewer can open the history
 * sheet for the currently selected file.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Bot } from 'lucide-react';
import { Button } from '@/components/ui';
import { useChatDraftStore } from '@/stores/chatDraft';
import ProjectFileTree from './ProjectFileTree';
import ProjectFileViewer from './ProjectFileViewer';
import ProjectGitHistory from './ProjectGitHistory';
import ProjectGitStatusStrip from './ProjectGitStatusStrip';

interface ProjectPanelProps {
  folderId: string;
  folderName: string;
  projectPath: string | null;
  mode?: 'full' | 'code' | 'git';
}

export default function ProjectPanel({
  folderId,
  folderName,
  projectPath,
  mode = 'full',
}: ProjectPanelProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setProjectFolder = useChatDraftStore((s) => s.setProjectFolderContext);
  const pushInsert = useChatDraftStore((s) => s.pushInsert);

  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  const handleRunCodingAgent = () => {
    setProjectFolder(folderId, folderName, projectPath);
    pushInsert(
      t('folders.project.runAgentPrompt', {
        defaultValue:
          'In project `{{name}}` ({{path}}), explore the structure and propose the next concrete improvement to make.',
        name: folderName,
        path: projectPath ?? '',
      }) as string,
    );
    navigate('/');
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {mode !== 'git' && (
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <span className="truncate text-xs text-muted-foreground">
            {projectPath ?? ''}
          </span>
          <Button
            variant="primary"
            size="sm"
            className="ml-auto"
            onClick={handleRunCodingAgent}
            leftIcon={<Bot className="h-3.5 w-3.5" />}
          >
            {t('folders.project.runAgent', {
              defaultValue: 'Run coding agent on this project',
            })}
          </Button>
        </div>
      )}
      {mode !== 'code' && <ProjectGitStatusStrip folderId={folderId} />}
      {mode === 'git' ? (
        <div className="min-h-0 flex-1 overflow-hidden">
          <ProjectGitHistory
            folderId={folderId}
            filePath={selectedPath}
            variant="inline"
          />
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[260px_1fr]">
          <div className="overflow-auto border-r border-border p-2">
            <ProjectFileTree
              folderId={folderId}
              selectedPath={selectedPath}
              onSelectFile={setSelectedPath}
            />
          </div>
          <div className="flex min-h-0 flex-col">
            <ProjectFileViewer
              folderId={folderId}
              folderName={folderName}
              projectPath={projectPath}
              filePath={selectedPath}
              onOpenHistory={() => setHistoryOpen(true)}
            />
          </div>
        </div>
      )}

      {mode !== 'git' && (
        <ProjectGitHistory
          folderId={folderId}
          filePath={selectedPath}
          variant="sheet"
          open={historyOpen}
          onOpenChange={setHistoryOpen}
        />
      )}
    </div>
  );
}
