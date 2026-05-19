import { useTranslation } from 'react-i18next';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui';
import type { CodingProject } from '@/hooks/useCodingProjects';
import { CodingProjectRunPanel } from './CodingProjectRunPanel';
import { FileExplorer } from './FileExplorer';
import { GitPanel } from './GitPanel';

interface ProjectWorkspaceProps {
  project: CodingProject;
}

export function ProjectWorkspace({ project }: ProjectWorkspaceProps) {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2 sm:px-4">
        <span className="min-w-0 truncate font-mono text-xs text-muted-foreground">
          {project.root_path}
        </span>
      </div>
      <Tabs
        defaultValue="files"
        className="flex min-h-0 flex-1 flex-col gap-0"
      >
        <TabsList className="mx-4 mt-2 flex-shrink-0 gap-0.5 self-start p-0.5 sm:mx-5">
          <TabsTrigger value="files" className="px-3 py-1.5 text-xs">
            {t('codingProjects.tabs.files')}
          </TabsTrigger>
          <TabsTrigger value="git" className="px-3 py-1.5 text-xs">
            {t('codingProjects.tabs.git')}
          </TabsTrigger>
          <TabsTrigger value="run" className="px-3 py-1.5 text-xs">
            {t('codingProjects.tabs.run')}
          </TabsTrigger>
        </TabsList>
        <TabsContent
          value="files"
          className="mt-0 flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden"
        >
          <FileExplorer projectId={project.id} />
        </TabsContent>
        <TabsContent
          value="git"
          className="mt-0 flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden"
        >
          <GitPanel projectId={project.id} />
        </TabsContent>
        <TabsContent
          value="run"
          className="mt-0 flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden"
        >
          <CodingProjectRunPanel project={project} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
