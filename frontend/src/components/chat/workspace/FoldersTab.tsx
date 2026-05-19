import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileText,
  Folder,
  FolderOpen,
  FolderTree,
  Sparkles,
} from 'lucide-react';
import { useFolderTree, useFolderItems, type FolderTreeNode } from '@/hooks/useFolders';
import { useChatDraftStore } from '@/stores/chatDraft';
import { useFoldersStore } from '@/stores/foldersStore';
import { Badge } from '@/components/ui';
import { cn } from '@/lib/utils';

function isExpandable(node: FolderTreeNode): boolean {
  return (
    node.children.length > 0 ||
    node.file_count > 0 ||
    Boolean(node.is_project)
  );
}

function FolderRowExpandedFiles({ folderId }: { folderId: string }) {
  const { t } = useTranslation();
  const { data, isLoading } = useFolderItems(folderId, undefined, true);

  if (isLoading) {
    return (
      <div className="pl-7 pr-1 py-1 text-[11px] text-muted-foreground-tertiary">
        {t('chat.workspace.folders.filesLoading', { defaultValue: 'Loading files…' })}
      </div>
    );
  }

  const files = data ?? [];
  if (files.length === 0) {
    return (
      <div className="pl-7 pr-1 py-1 text-[11px] text-muted-foreground-tertiary italic">
        {t('chat.workspace.folders.filesEmpty', { defaultValue: 'No files in this folder.' })}
      </div>
    );
  }

  const max = 40;
  const shown = files.slice(0, max);

  return (
    <ul className="pl-6 pr-1 pb-1 space-y-0.5 border-l border-border-subtle/60 ml-3.5 my-0.5">
      {shown.map((f) => (
        <li
          key={f.file_id}
          className="flex items-center gap-1.5 min-w-0 text-[11px] text-muted-foreground"
        >
          <FileText className="w-3 h-3 flex-shrink-0 text-muted-foreground-tertiary" />
          <span className="truncate font-mono" title={f.file_name}>
            {f.file_name}
          </span>
        </li>
      ))}
      {files.length > max && (
        <li className="text-[10px] text-muted-foreground-tertiary pl-4">
          {t('chat.workspace.folders.filesTruncated', {
            defaultValue: '+ {{count}} more',
            count: files.length - max,
          })}
        </li>
      )}
    </ul>
  );
}

/**
 * Folders tab — compact tree with code-project cues, lazy-loaded file names,
 * and links to the full folder explorer.
 */
export function FoldersTab() {
  const { t } = useTranslation();
  const { data: tree, isLoading } = useFolderTree();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const setFolderContext = useChatDraftStore((s) => s.setFolderContext);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="text-center py-8">
        <p className="text-xs text-muted-foreground">
          {t('common.loading', { defaultValue: 'Loading…' })}
        </p>
      </div>
    );
  }

  if (!tree || tree.length === 0) {
    return (
      <div className="text-center py-10">
        <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-surface-sunken flex items-center justify-center">
          <FolderTree className="w-5 h-5 text-muted-foreground-tertiary" />
        </div>
        <p className="text-xs text-muted-foreground">
          {t('chat.workspace.folders.empty', {
            defaultValue: 'You have no folders yet.',
          })}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-y-auto px-1 pb-3">
      {tree.map((node) => (
        <FolderRow
          key={node.id}
          node={node}
          depth={0}
          expanded={expanded}
          onToggle={toggle}
          onAnalyze={(n) => setFolderContext(n.id, n.name)}
        />
      ))}
    </div>
  );
}

interface FolderRowProps {
  node: FolderTreeNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (id: string) => void;
  onAnalyze: (node: FolderTreeNode) => void;
}

function FolderRow({ node, depth, expanded, onToggle, onAnalyze }: FolderRowProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const selectFolder = useFoldersStore((s) => s.selectFolder);

  const isExpanded = expanded.has(node.id);
  const hasChildren = node.children.length > 0;
  const expandable = isExpandable(node);
  const showFileList =
    isExpanded && (node.file_count > 0 || Boolean(node.is_project));

  const openInExplorer = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectFolder(node.id);
    navigate('/folders');
  };

  const pathTitle =
    node.project_path?.trim() ||
    (node.is_project
      ? t('chat.workspace.folders.projectNoPath', { defaultValue: 'Project path not set' })
      : undefined);

  return (
    <div>
      <div
        className={cn(
          'group flex items-center gap-1.5 py-1.5 pr-1 rounded-md text-xs',
          'hover:bg-surface-sunken transition-colors'
        )}
        style={{ paddingLeft: `${depth * 14 + 4}px` }}
      >
        <button
          type="button"
          onClick={() => expandable && onToggle(node.id)}
          disabled={!expandable}
          className={cn(
            'flex-shrink-0 w-4 h-4 flex items-center justify-center text-muted-foreground-tertiary',
            !expandable && 'opacity-40 cursor-default'
          )}
          aria-label={
            expandable
              ? isExpanded
                ? t('chat.workspace.folders.collapse', { defaultValue: 'Collapse' })
                : t('chat.workspace.folders.expand', { defaultValue: 'Expand' })
              : undefined
          }
        >
          {expandable ? (
            isExpanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )
          ) : (
            <span className="w-3" />
          )}
        </button>
        {isExpanded ? (
          <FolderOpen className="w-3.5 h-3.5 flex-shrink-0 text-primary-600 dark:text-primary-400" />
        ) : (
          <Folder className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" />
        )}
        <span
          className={cn(
            'truncate flex-1 text-foreground min-w-0',
            expandable && 'cursor-pointer'
          )}
          title={pathTitle}
          onClick={() => expandable && onToggle(node.id)}
        >
          <span className="align-middle">{node.name}</span>
          {node.is_project ? (
            <Badge
              variant="secondary"
              className="ml-1.5 align-middle text-[9px] px-1 py-0 font-medium"
            >
              {t('chat.workspace.folders.projectBadge', { defaultValue: 'Project' })}
            </Badge>
          ) : null}
        </span>
        {node.file_count > 0 && (
          <span className="tabular-nums text-[11px] text-muted-foreground-tertiary flex-shrink-0">
            {node.file_count}
          </span>
        )}
        <button
          type="button"
          onClick={openInExplorer}
          className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 flex-shrink-0 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-all"
          aria-label={t('chat.workspace.folders.openExplorerAria', {
            defaultValue: 'Open {{name}} in folder explorer',
            name: node.name,
          })}
          title={t('chat.workspace.folders.openExplorer', { defaultValue: 'Open in folder explorer' })}
        >
          <ExternalLink className="w-3 h-3" />
        </button>
        <button
          type="button"
          onClick={() => onAnalyze(node)}
          className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 flex-shrink-0 p-1 rounded-md text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-all"
          aria-label={t('chat.workspace.folders.analyzeAria', {
            defaultValue: `Analyze ${node.name}`,
            name: node.name,
          })}
          title={t('chat.workspace.folders.analyzeAction', {
            defaultValue: 'Analyze in chat',
          })}
        >
          <Sparkles className="w-3 h-3" />
        </button>
      </div>
      {isExpanded && node.project_path?.trim() ? (
        <div
          className="text-[10px] font-mono text-muted-foreground-tertiary truncate px-1 pb-0.5"
          style={{ paddingLeft: `${depth * 14 + 24}px` }}
          title={node.project_path}
        >
          {node.project_path}
        </div>
      ) : null}
      {isExpanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <FolderRow
              key={child.id}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              onAnalyze={onAnalyze}
            />
          ))}
        </div>
      )}
      {showFileList ? <FolderRowExpandedFiles folderId={node.id} /> : null}
    </div>
  );
}
