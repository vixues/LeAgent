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
}

export default function ProjectPanel({
  folderId,
  folderName,
  projectPath,
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
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <span className="text-xs text-muted-foreground truncate">
          {projectPath ?? ''}
        </span>
        <Button
          variant="primary"
          size="sm"
          className="ml-auto"
          onClick={handleRunCodingAgent}
          leftIcon={<Bot className="w-3.5 h-3.5" />}
        >
          {t('folders.project.runAgent', {
            defaultValue: 'Run coding agent on this project',
          })}
        </Button>
      </div>
      <ProjectGitStatusStrip folderId={folderId} />
      <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] flex-1 min-h-0">
        <div className="border-r border-border overflow-auto p-2">
          <ProjectFileTree
            folderId={folderId}
            selectedPath={selectedPath}
            onSelectFile={setSelectedPath}
          />
        </div>
        <div className="flex flex-col min-h-0">
          <ProjectFileViewer
            folderId={folderId}
            folderName={folderName}
            projectPath={projectPath}
            filePath={selectedPath}
            onOpenHistory={() => setHistoryOpen(true)}
          />
        </div>
      </div>

      <ProjectGitHistory
        folderId={folderId}
        filePath={selectedPath}
        open={historyOpen}
        onOpenChange={setHistoryOpen}
      />
    </div>
  );
}
