/**
 * Lazy depth-1 directory tree for a code-project folder.
 *
 * Each ``dir`` row owns its own expanded state and triggers a fresh
 * ``useProjectTree`` query when opened, so very large repos only pay
 * for what the user opens. ``is_ignored`` rows are surfaced with a
 * dimmer style and an "i" hint so the user knows they are gitignored
 * but visible.
 */
import { useState, type ReactNode } from 'react';
import { ChevronRight, ChevronDown, File, Folder, FolderOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useProjectTree, type ProjectTreeEntry } from '@/hooks/useProjectFolder';

interface ProjectFileTreeProps {
  folderId: string;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  showIgnored?: boolean;
}

export default function ProjectFileTree({
  folderId,
  selectedPath,
  onSelectFile,
  showIgnored = false,
}: ProjectFileTreeProps) {
  return (
    <div className="text-xs select-none">
      <DirectoryNode
        folderId={folderId}
        path=""
        depth={0}
        defaultOpen
        selectedPath={selectedPath}
        onSelectFile={onSelectFile}
        showIgnored={showIgnored}
      />
    </div>
  );
}

interface DirectoryNodeProps {
  folderId: string;
  path: string;
  depth: number;
  defaultOpen?: boolean;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  showIgnored: boolean;
}

function DirectoryNode({
  folderId,
  path,
  depth,
  defaultOpen = false,
  selectedPath,
  onSelectFile,
  showIgnored,
}: DirectoryNodeProps) {
  const [open, setOpen] = useState(defaultOpen);
  const { data, isLoading } = useProjectTree(folderId, path, 1, {
    includeIgnored: showIgnored,
    enabled: open,
  });

  const entries: ProjectTreeEntry[] = data ?? [];

  const indent: ReactNode = (
    <span style={{ width: depth * 12 }} className="inline-block" aria-hidden />
  );

  if (depth === 0) {
    return (
      <div>
        {isLoading && <div className="px-2 py-1 text-muted-foreground">Loading…</div>}
        {entries.map((e) => (
          <Entry
            key={e.rel_path}
            folderId={folderId}
            entry={e}
            depth={depth + 1}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
            showIgnored={showIgnored}
          />
        ))}
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        className={cn(
          'flex items-center w-full text-left rounded px-1 py-0.5 hover:bg-surface-sunken/60',
          'transition-colors',
        )}
        onClick={() => setOpen((v) => !v)}
      >
        {indent}
        {open ? (
          <ChevronDown className="w-3 h-3 mr-1 text-muted-foreground" />
        ) : (
          <ChevronRight className="w-3 h-3 mr-1 text-muted-foreground" />
        )}
        {open ? (
          <FolderOpen className="w-3.5 h-3.5 mr-1.5 text-muted-foreground" />
        ) : (
          <Folder className="w-3.5 h-3.5 mr-1.5 text-muted-foreground" />
        )}
        <span className="truncate" title={path}>
          {path.split('/').pop()}
        </span>
      </button>
      {open && (
        <div>
          {isLoading && (
            <div className="px-2 py-0.5 text-muted-foreground" style={{ paddingLeft: (depth + 1) * 12 }}>
              Loading…
            </div>
          )}
          {entries.map((e) => (
            <Entry
              key={e.rel_path}
              folderId={folderId}
              entry={e}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelectFile={onSelectFile}
              showIgnored={showIgnored}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface EntryProps {
  folderId: string;
  entry: ProjectTreeEntry;
  depth: number;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  showIgnored: boolean;
}

function Entry({ folderId, entry, depth, selectedPath, onSelectFile, showIgnored }: EntryProps) {
  if (entry.type === 'dir') {
    return (
      <DirectoryNode
        folderId={folderId}
        path={entry.rel_path}
        depth={depth}
        selectedPath={selectedPath}
        onSelectFile={onSelectFile}
        showIgnored={showIgnored}
      />
    );
  }
  const isSelected = selectedPath === entry.rel_path;
  return (
    <button
      type="button"
      className={cn(
        'flex items-center w-full text-left rounded px-1 py-0.5 hover:bg-surface-sunken/60',
        isSelected && 'bg-primary/10 text-primary',
        entry.is_ignored && 'opacity-60 italic',
      )}
      onClick={() => onSelectFile(entry.rel_path)}
      title={entry.is_ignored ? `${entry.rel_path} (ignored)` : entry.rel_path}
    >
      <span style={{ width: depth * 12 + 16 }} className="inline-block" aria-hidden />
      <File className="w-3.5 h-3.5 mr-1.5 text-muted-foreground" />
      <span className="truncate">{entry.name}</span>
    </button>
  );
}
