import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import {
  Copy,
  Check,
  FlaskConical,
  MessageSquare,
  ChevronDown,
  ChevronRight,
  LayoutTemplate,
  Tag,
} from 'lucide-react';
import { apiClient } from '@/api/client';
import { Button } from '@/components/ui';
import { cn } from '@/lib/utils';
import { PageLoader } from '@/components/common/PageLoader';
import { WorkflowMiniGraphPreview } from '@/features/workflow/components/WorkflowMiniGraphPreview';
import { chatSpecToFlowData } from '@/lib/chatSpecToFlowData';
import type { ChatWorkflowSpecModel } from '@/types/chat';

interface ChatWorkflowTemplateRow {
  id: string;
  title: string;
  description: string;
  spec: ChatWorkflowSpecModel;
  digest: string;
  category?: string;
  playbook_id?: string | null;
}

interface MaterializeResponse {
  session_id: string;
  templates: { template_id: string; message_id: string }[];
}

function PlaybookCard({
  row,
  isOpen,
  onToggle,
  copiedId,
  copiedDigest,
  onCopyJson,
  onCopyDigest,
}: {
  row: ChatWorkflowTemplateRow;
  isOpen: boolean;
  onToggle: () => void;
  copiedId: string | null;
  copiedDigest: string | null;
  onCopyJson: () => void;
  onCopyDigest: () => void;
}) {
  const { t } = useTranslation();
  const previewFlow = chatSpecToFlowData(row.spec);
  const isPlaybook = row.category === 'playbook';

  return (
    <li className="rounded-xl border border-border bg-surface overflow-hidden flex flex-col hover:border-primary-300 dark:hover:border-primary-700 transition-colors">
      <div className="p-4 pb-3 flex flex-col gap-3 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground truncate">{row.title}</p>
            {row.description ? (
              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{row.description}</p>
            ) : null}
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            {isPlaybook ? (
              <span className="inline-flex items-center rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-700 dark:border-violet-800 dark:bg-violet-900/30 dark:text-violet-300">
                {t('list.hub.playbookBadge')}
              </span>
            ) : (
              <span className="inline-flex items-center rounded-full border border-border bg-surface-sunken px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {t('list.hub.demoBadge')}
              </span>
            )}
          </div>
        </div>

        <WorkflowMiniGraphPreview flowData={previewFlow} variant="card" />

        {row.playbook_id ? (
          <Link
            to={`/templates?search=${encodeURIComponent(row.playbook_id.replace(/_/g, ' '))}`}
            className="inline-flex items-center gap-1 text-[11px] text-primary-600 hover:underline dark:text-primary-400"
          >
            <LayoutTemplate className="h-3 w-3" />
            {t('list.hub.openDagTemplate')}
          </Link>
        ) : null}
      </div>

      <div className="border-t border-border-subtle px-4 py-2">
        <button
          type="button"
          className="flex w-full items-center gap-2 text-left text-xs text-muted-foreground hover:text-foreground"
          onClick={onToggle}
        >
          {isOpen ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          )}
          <span>{t('list.hub.advancedSpec')}</span>
          <code className="ml-auto hidden truncate font-mono text-[10px] text-muted-foreground-tertiary sm:block max-w-[140px]">
            {row.id}
          </code>
        </button>
        {isOpen ? (
          <div className="space-y-3 pb-2 pt-2">
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" className="text-xs" onClick={onCopyJson}>
                {copiedId === row.id ? (
                  <Check className="mr-1 h-3.5 w-3.5 text-mint-500" />
                ) : (
                  <Copy className="mr-1 h-3.5 w-3.5" />
                )}
                {t('chat.workflowTemplatesPage.copySpec')}
              </Button>
              <Button type="button" variant="ghost" size="sm" className="text-xs font-mono" onClick={onCopyDigest}>
                {copiedDigest === row.id ? (
                  <Check className="mr-1 h-3.5 w-3.5 text-mint-500" />
                ) : (
                  <Copy className="mr-1 h-3.5 w-3.5" />
                )}
                {t('chat.workflowTemplatesPage.digestShort')}
              </Button>
            </div>
            <pre
              className={cn(
                'overflow-x-auto rounded-lg border border-border-subtle bg-surface-raised p-3',
                'font-mono text-[11px] leading-relaxed text-foreground',
              )}
            >
              {JSON.stringify(row.spec, null, 2)}
            </pre>
            <p className="break-all font-mono text-[10px] text-muted-foreground-tertiary">
              SHA-256: {row.digest}
            </p>
          </div>
        ) : null}
      </div>
    </li>
  );
}

/** Chat workflow template catalog — the "Chat playbooks" tab of the hub. */
export function ChatTemplatesView() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [openId, setOpenId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copiedDigest, setCopiedDigest] = useState<string | null>(null);

  const templatesQuery = useQuery({
    queryKey: ['chat', 'workflow-templates'],
    queryFn: () => apiClient.get<ChatWorkflowTemplateRow[]>('/chat/workflow-templates'),
    staleTime: 60_000,
  });

  const materialize = useMutation({
    mutationFn: () =>
      apiClient.post<MaterializeResponse>('/chat/workflow-templates/materialize', {}),
    onSuccess: (data) => {
      navigate(`/chat/${data.session_id}`);
    },
  });

  const copyJson = async (id: string, spec: ChatWorkflowSpecModel) => {
    await navigator.clipboard.writeText(JSON.stringify(spec, null, 2));
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const copyDigest = async (id: string, digest: string) => {
    await navigator.clipboard.writeText(digest);
    setCopiedDigest(id);
    setTimeout(() => setCopiedDigest(null), 2000);
  };

  if (templatesQuery.isLoading) {
    return (
      <div className="flex justify-center py-20">
        <PageLoader size="md" message={t('common.loading')} />
      </div>
    );
  }

  if (templatesQuery.isError) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        {t('chat.workflowTemplatesPage.loadError')}
      </p>
    );
  }

  const items = templatesQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 rounded-xl border border-border-subtle bg-surface-raised/60 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-primary-500/10 p-2 text-primary-600">
            <FlaskConical className="h-5 w-5" aria-hidden />
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">{t('list.hub.playbooksBlurbTitle')}</p>
            <p className="mt-1 text-xs text-muted-foreground-tertiary">{t('list.hub.playbooksBlurbBody')}</p>
          </div>
        </div>
        <Button
          type="button"
          variant="primary"
          className="inline-flex shrink-0 items-center gap-2"
          disabled={materialize.isPending}
          onClick={() => materialize.mutate()}
        >
          <MessageSquare className="h-4 w-4" />
          {materialize.isPending
            ? t('chat.workflowTemplatesPage.creating')
            : t('chat.workflowTemplatesPage.createLab')}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Tag className="h-3.5 w-3.5" />
        <span>{t('list.hub.playbooksVsGallery')}</span>
        <Link to="/templates" className="text-primary-600 hover:underline dark:text-primary-400">
          {t('list.fromTemplate')}
        </Link>
      </div>

      {materialize.isError && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {t('chat.workflowTemplatesPage.materializeError')}
        </p>
      )}

      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((row) => (
          <PlaybookCard
            key={row.id}
            row={row}
            isOpen={openId === row.id}
            onToggle={() => setOpenId(openId === row.id ? null : row.id)}
            copiedId={copiedId}
            copiedDigest={copiedDigest}
            onCopyJson={() => void copyJson(row.id, row.spec)}
            onCopyDigest={() => void copyDigest(row.id, row.digest)}
          />
        ))}
      </ul>
    </div>
  );
}

export default ChatTemplatesView;
