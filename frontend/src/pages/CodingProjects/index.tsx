/**
 * Coding Projects — dual-pane layout aligned with FolderPage:
 * project list + workspace (Files / Git / Run).
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Loader2,
  PanelLeft,
  PlayCircle,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { PageShell } from '@/components/layout/PageShell';
import {
  Badge,
  Button,
  Card,
  Sheet,
  SheetContent,
} from '@/components/ui';
import {
  CodingProject,
  useCodingProjectTemplates,
  useCodingProjects,
  useCreateCodingProject,
  useDeleteCodingProject,
} from '@/hooks/useCodingProjects';
import { cn } from '@/lib/utils';
import { CreateCodingProjectModal } from './CreateCodingProjectModal';
import { CodingProjectStatusBadge } from './CodingProjectStatusBadge';
import { ProjectWorkspace } from './ProjectWorkspace';

export default function CodingProjectsPage() {
  const { t } = useTranslation();
  const { data: projects = [], isLoading, refetch } = useCodingProjects();
  const { data: templates = [] } = useCodingProjectTemplates();
  const create = useCreateCodingProject();
  const del = useDeleteCodingProject();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mobileListOpen, setMobileListOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [template, setTemplate] = useState('');

  const sorted = useMemo(
    () =>
      [...projects].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    [projects],
  );
  const selected =
    sorted.find((p) => p.id === selectedId) ?? sorted[0] ?? null;

  const handleSelectProject = (id: string) => {
    setSelectedId(id);
    setMobileListOpen(false);
  };

  const handleCreate = async () => {
    if (!name.trim() || !template) return;
    const created = await create.mutateAsync({
      name: name.trim(),
      template,
      description: description.trim() || null,
    });
    setSelectedId(created.id);
    setCreateOpen(false);
    setName('');
    setDescription('');
    setTemplate('');
  };

  const projectListItems = (
    <ul className="flex flex-col gap-1 p-2">
      {sorted.map((p) => (
        <ProjectListItem
          key={p.id}
          project={p}
          active={selected?.id === p.id}
          onSelect={() => handleSelectProject(p.id)}
          onDelete={() => del.mutate(p.id)}
        />
      ))}
    </ul>
  );

  const projectListBody = (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {isLoading ? (
        <div className="flex flex-1 items-center gap-2 p-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          {t('common.loading')}
        </div>
      ) : sorted.length === 0 ? (
        <div className="flex flex-1 items-start p-4 text-sm text-muted-foreground">
          {t('codingProjects.emptyHint')}
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">{projectListItems}</div>
      )}
    </div>
  );

  return (
    <PageShell
      fullBleed
      className="flex min-h-0 w-full max-w-none flex-1 flex-col"
      title={t('codingProjects.title')}
      description={t('codingProjects.subtitle')}
      contentClassName="flex min-h-0 flex-1 flex-col"
      actions={
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="lg:hidden"
            onClick={() => setMobileListOpen(true)}
            leftIcon={<PanelLeft className="size-4" />}
          >
            {t('codingProjects.showProjects')}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => refetch()}
            aria-label={t('common.refresh')}
          >
            <RefreshCw className="size-4" />
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => setCreateOpen(true)}
            leftIcon={<Plus className="w-4 h-4" />}
          >
            {t('codingProjects.new')}
          </Button>
        </div>
      }
    >
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        <Card
          padding="none"
          className="hidden min-h-0 flex-col overflow-hidden lg:flex"
        >
          {projectListBody}
        </Card>

        <Card
          padding="none"
          className="flex min-h-0 flex-1 flex-col overflow-hidden"
        >
          {selected ? (
            <ProjectWorkspace project={selected} />
          ) : (
            <div className="flex flex-col items-center justify-center gap-3 p-12 text-center text-sm text-muted-foreground">
              <PlayCircle className="size-10 opacity-50" aria-hidden />
              {t('codingProjects.selectHint')}
            </div>
          )}
        </Card>
      </div>

      <Sheet open={mobileListOpen} onOpenChange={setMobileListOpen} side="left">
        <SheetContent className="w-[min(100%,320px)] p-0">
          <div className="flex h-full min-h-0 flex-col overflow-hidden">
            <div className="shrink-0 border-b border-border px-4 py-3 text-sm font-semibold">
              {t('codingProjects.title')}
            </div>
            <div className="min-h-0 flex-1">{projectListBody}</div>
          </div>
        </SheetContent>
      </Sheet>

      <CreateCodingProjectModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        templates={templates}
        name={name}
        onNameChange={setName}
        description={description}
        onDescriptionChange={setDescription}
        template={template}
        onTemplateChange={setTemplate}
        onSubmit={handleCreate}
        isSubmitting={create.isPending}
      />
    </PageShell>
  );
}

interface ProjectListItemProps {
  project: CodingProject;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

function ProjectListItem({
  project,
  active,
  onSelect,
  onDelete,
}: ProjectListItemProps) {
  const { t } = useTranslation();
  return (
    <li>
      <div
        className={cn(
          'flex rounded-lg border transition-colors',
          active
            ? 'border-primary-200/80 bg-primary-100 ring-1 ring-primary-500/15 dark:border-primary-800/50 dark:bg-primary-900/30 dark:ring-primary-400/20'
            : 'border-transparent hover:bg-surface-sunken/60',
        )}
      >
        <button
          type="button"
          onClick={onSelect}
          className="min-w-0 flex-1 px-3 py-2.5 text-left"
        >
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div
                className={cn(
                  'truncate font-medium',
                  active && 'text-primary-700 dark:text-primary-300',
                )}
              >
                {project.name}
              </div>
              <div
                className={cn(
                  'truncate text-xs',
                  active
                    ? 'text-primary-600/80 dark:text-primary-400/80'
                    : 'text-muted-foreground',
                )}
              >
                {project.template}
              </div>
            </div>
            <CodingProjectStatusBadge status={project.status} />
          </div>
          <div className="mt-1 flex items-center gap-1.5">
            <Badge
              variant={project.runtime_kind === 'fastapi' ? 'success' : project.runtime_kind === 'python' ? 'warning' : 'primary'}
              className="text-[10px]"
            >
              {project.runtime_kind}
            </Badge>
          </div>
        </button>
        <button
          type="button"
          onClick={() => {
            if (window.confirm(t('codingProjects.confirmDeleteProject'))) {
              onDelete();
            }
          }}
          className="shrink-0 self-start rounded-md p-2.5 text-muted-foreground hover:bg-muted/70 hover:text-foreground"
          aria-label={t('common.delete')}
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
    </li>
  );
}
