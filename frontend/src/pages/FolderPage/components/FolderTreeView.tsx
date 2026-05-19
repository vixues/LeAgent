import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import {
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  Plus,
  MoreHorizontal,
} from 'lucide-react';
import { Button } from '@/components/ui';
import type { FolderTreeNode } from '@/hooks/useFolders';

interface FolderTreeViewProps {
  tree: FolderTreeNode[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onContextMenu?: (e: React.MouseEvent, folderId: string) => void;
  onCreateFolder?: (parentId: string | null) => void;
}

interface TreeNodeProps {
  node: FolderTreeNode;
  depth: number;
  selectedId: string | null;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  onSelect: (id: string) => void;
  onContextMenu?: (e: React.MouseEvent, folderId: string) => void;
}

function TreeNode({
  node,
  depth,
  selectedId,
  expandedIds,
  onToggle,
  onSelect,
  onContextMenu,
}: TreeNodeProps) {
  const { t } = useTranslation();
  const isExpanded = expandedIds.has(node.id);
  const isSelected = selectedId === node.id;
  const hasChildren = node.children.length > 0;

  return (
    <div>
      <div
        className={cn(
          'group flex items-center gap-1.5 py-1.5 pr-2 rounded-lg cursor-pointer text-sm transition-colors',
          isSelected
            ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
            : 'hover:bg-surface-sunken text-muted-foreground'
        )}
        // Indent by depth; keep inline style simple — one numeric value avoids
        // invalidating CSS-variable fallbacks across deep trees.
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
        onClick={() => onSelect(node.id)}
        onContextMenu={(e) => onContextMenu?.(e, node.id)}
      >
        <button
          type="button"
          className="flex-shrink-0 w-4 h-4 flex items-center justify-center text-muted-foreground-tertiary"
          onClick={(e) => {
            e.stopPropagation();
            if (hasChildren) onToggle(node.id);
          }}
          aria-label={
            hasChildren ? (isExpanded ? t('folders.treeCollapse') : t('folders.treeExpand')) : undefined
          }
        >
          {hasChildren ? (
            isExpanded ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )
          ) : (
            <span className="w-3.5" />
          )}
        </button>

        {/*
          Drop the amber folder icon — it clashed with the rest of the app.
          Selected rows highlight through background + text color alone.
        */}
        {isExpanded ? (
          <FolderOpen
            className={cn(
              'w-4 h-4 flex-shrink-0',
              isSelected ? 'text-primary-600 dark:text-primary-400' : 'text-muted-foreground-tertiary'
            )}
          />
        ) : (
          <Folder
            className={cn(
              'w-4 h-4 flex-shrink-0',
              isSelected ? 'text-primary-600 dark:text-primary-400' : 'text-muted-foreground-tertiary'
            )}
          />
        )}

        <span className="truncate flex-1">{node.name}</span>

        {node.file_count > 0 && (
          <span className="text-xs text-muted-foreground-tertiary flex-shrink-0 tabular-nums">
            {node.file_count}
          </span>
        )}

        <button
          type="button"
          className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 flex-shrink-0 p-0.5 rounded hover:bg-surface-elevated transition-opacity"
          onClick={(e) => {
            e.stopPropagation();
            onContextMenu?.(e, node.id);
          }}
          aria-label={t('folders.folderActionsAria')}
        >
          <MoreHorizontal className="w-3.5 h-3.5" />
        </button>
      </div>

      {isExpanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              expandedIds={expandedIds}
              onToggle={onToggle}
              onSelect={onSelect}
              onContextMenu={onContextMenu}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function FolderTreeView({
  tree,
  selectedId,
  onSelect,
  onContextMenu,
  onCreateFolder,
}: FolderTreeViewProps) {
  const { t } = useTranslation();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center justify-between px-4 h-12 border-b border-border">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t('folders.showTree')}
        </span>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onCreateFolder?.(null)}
          aria-label={t('folders.newFolderAria')}
          className="h-7 w-7"
        >
          <Plus className="w-4 h-4" />
        </Button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto py-2 px-2" role="tree">
        <div
          className={cn(
            'flex items-center gap-2 py-1.5 px-2 rounded-lg cursor-pointer text-sm transition-colors',
            selectedId === null
              ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
              : 'hover:bg-surface-sunken text-muted-foreground'
          )}
          onClick={() => onSelect(null)}
          role="treeitem"
          aria-selected={selectedId === null}
        >
          <Folder
            className={cn(
              'w-4 h-4',
              selectedId === null
                ? 'text-primary-600 dark:text-primary-400'
                : 'text-muted-foreground-tertiary'
            )}
          />
          <span>{t('folders.allFiles')}</span>
        </div>

        <div className="mt-1 space-y-0.5">
          {tree.map((node) => (
            <TreeNode
              key={node.id}
              node={node}
              depth={0}
              selectedId={selectedId}
              expandedIds={expandedIds}
              onToggle={toggleExpand}
              onSelect={onSelect}
              onContextMenu={onContextMenu}
            />
          ))}
        </div>

        {tree.length === 0 && (
          <div className="px-3 py-6 text-center text-sm text-muted-foreground-tertiary">
            {t('folders.emptyTree')}
          </div>
        )}
      </div>
    </div>
  );
}
