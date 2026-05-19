/**
 * Header chip + popover that toggles a folder's "code project" mode.
 *
 * - When project mode is OFF, shows a "Set up project" button that opens
 *   a popover where the user types the absolute path of an on-disk
 *   project root.
 * - When ON, shows the active path with quick "Re-target" / "Disable" /
 *   "Init git" actions.
 *
 * The component does not own any state about the path itself — that
 * lives on the Folder row and is updated via PATCH /folders/{id}/project.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FolderGit2, GitBranch, X } from 'lucide-react';
import {
  Badge,
  Button,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui';
import { cn } from '@/lib/utils';
import {
  useInitProjectGit,
  useUpdateFolderProject,
} from '@/hooks/useProjectFolder';

interface ProjectModeBadgeProps {
  folderId: string;
  isProject: boolean;
  projectPath: string | null;
}

export default function ProjectModeBadge({
  folderId,
  isProject,
  projectPath,
}: ProjectModeBadgeProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [pathInput, setPathInput] = useState(projectPath ?? '');
  const [error, setError] = useState<string | null>(null);

  const update = useUpdateFolderProject(folderId);
  const initGit = useInitProjectGit(folderId);

  const handleEnable = async () => {
    setError(null);
    try {
      await update.mutateAsync({ enabled: true, project_path: pathInput.trim() });
      setOpen(false);
    } catch (e: unknown) {
      const message =
        (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data
          ?.detail ?? (e as { message?: string })?.message ?? 'Failed to enable project mode';
      setError(message);
    }
  };

  const handleDisable = async () => {
    setError(null);
    try {
      await update.mutateAsync({ enabled: false });
      setOpen(false);
    } catch (e: unknown) {
      const message = (e as { message?: string })?.message ?? 'Failed to disable project mode';
      setError(message);
    }
  };

  const handleInitGit = async () => {
    setError(null);
    try {
      await initGit.mutateAsync();
    } catch (e: unknown) {
      const message =
        (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data
          ?.detail ?? (e as { message?: string })?.message ?? 'git init failed';
      setError(message);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        className={cn(
          'inline-flex items-center gap-2 rounded-md text-xs font-medium',
          'px-2.5 py-1 transition-colors',
          isProject
            ? 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
            : 'text-muted-foreground hover:bg-surface-sunken/60',
        )}
      >
        <FolderGit2 className="w-4 h-4" />
        {isProject ? (
          <>
            <Badge variant="default" className="text-[10px]">
              {t('folders.project.modeBadge', { defaultValue: 'Project' })}
            </Badge>
            <span className="truncate max-w-[200px]" title={projectPath ?? ''}>
              {projectPath ?? ''}
            </span>
          </>
        ) : (
          t('folders.project.enable', { defaultValue: 'Set up project' })
        )}
      </PopoverTrigger>
      <PopoverContent className="w-[420px]">
        <div className="space-y-3">
          <div>
            <h4 className="text-sm font-medium">
              {t('folders.project.title', { defaultValue: 'Code project mode' })}
            </h4>
            <p className="text-xs text-muted-foreground mt-1">
              {t('folders.project.description', {
                defaultValue:
                  'Bind this folder to an on-disk directory so the coding agent and project_* tools can read, edit and grep inside it.',
              })}
            </p>
          </div>
          <div className="space-y-2">
            <label htmlFor="project-path-input" className="text-xs font-medium">
              {t('folders.project.pathLabel', { defaultValue: 'Absolute project path' })}
            </label>
            <Input
              id="project-path-input"
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              placeholder="/absolute/path/to/repo"
              className="font-mono text-xs"
            />
            <p className="text-[11px] text-muted-foreground">
              {t('folders.project.pathHint', {
                defaultValue:
                  'Must be an existing directory and (when configured) inside FILES_PROJECTS_ALLOWED_ROOTS.',
              })}
            </p>
          </div>
          {error && (
            <div className="text-xs text-destructive whitespace-pre-wrap">{error}</div>
          )}
          <div className="flex justify-between gap-2 pt-2 border-t border-border">
            {isProject ? (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleDisable}
                  leftIcon={<X className="w-3 h-3" />}
                  disabled={update.isPending}
                >
                  {t('folders.project.disable', { defaultValue: 'Disable project mode' })}
                </Button>
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleInitGit}
                    leftIcon={<GitBranch className="w-3 h-3" />}
                    disabled={initGit.isPending}
                  >
                    {t('folders.project.initGit', { defaultValue: 'git init' })}
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleEnable}
                    disabled={update.isPending || !pathInput.trim()}
                  >
                    {t('folders.project.retarget', { defaultValue: 'Re-target' })}
                  </Button>
                </div>
              </>
            ) : (
              <Button
                variant="primary"
                size="sm"
                className="ml-auto"
                onClick={handleEnable}
                disabled={update.isPending || !pathInput.trim()}
              >
                {t('folders.project.enableConfirm', { defaultValue: 'Enable project mode' })}
              </Button>
            )}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
