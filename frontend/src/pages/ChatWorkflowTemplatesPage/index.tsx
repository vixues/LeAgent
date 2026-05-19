import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Copy, Check, FlaskConical, MessageSquare, ChevronDown, ChevronRight } from 'lucide-react';
import { apiClient } from '@/api/client';
import { PageShell } from '@/components/layout/PageShell';
import { Button } from '@/components/ui';
import { cn } from '@/lib/utils';
import { PageLoader } from '@/components/common/PageLoader';
import type { ChatWorkflowSpecModel } from '@/types/chat';

interface ChatWorkflowTemplateRow {
  id: string;
  title: string;
  description: string;
  spec: ChatWorkflowSpecModel;
  digest: string;
}

interface MaterializeResponse {
  session_id: string;
  templates: { template_id: string; message_id: string }[];
}

export default function ChatWorkflowTemplatesPage() {
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
      <PageShell
        title={t('chat.workflowTemplatesPage.title')}
        description={t('chat.workflowTemplatesPage.description')}
      >
        <div className="flex justify-center py-20">
          <PageLoader size="md" message={t('common.loading')} />
        </div>
      </PageShell>
    );
  }

  if (templatesQuery.isError) {
    return (
      <PageShell
        title={t('chat.workflowTemplatesPage.title')}
        description={t('chat.workflowTemplatesPage.description')}
      >
        <p className="text-sm text-red-600 dark:text-red-400">
          {t('chat.workflowTemplatesPage.loadError')}
        </p>
      </PageShell>
    );
  }

  const items = templatesQuery.data ?? [];

  return (
    <PageShell
      title={t('chat.workflowTemplatesPage.title')}
      description={t('chat.workflowTemplatesPage.description')}
    >
      <div className="space-y-6 max-w-4xl">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-xl border border-border-subtle bg-surface-raised/60 p-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-primary-500/10 text-primary-600">
              <FlaskConical className="w-5 h-5" aria-hidden />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">
                {t('chat.workflowTemplatesPage.labBlurbTitle')}
              </p>
              <p className="text-xs text-muted-foreground-tertiary mt-1">
                {t('chat.workflowTemplatesPage.labBlurbBody')}
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="primary"
            className="shrink-0 inline-flex items-center gap-2"
            disabled={materialize.isPending}
            onClick={() => materialize.mutate()}
          >
            <MessageSquare className="w-4 h-4" />
            {materialize.isPending
              ? t('chat.workflowTemplatesPage.creating')
              : t('chat.workflowTemplatesPage.createLab')}
          </Button>
        </div>

        {materialize.isError && (
          <p className="text-sm text-red-600 dark:text-red-400">
            {t('chat.workflowTemplatesPage.materializeError')}
          </p>
        )}

        <ul className="space-y-2">
          {items.map((row) => {
            const isOpen = openId === row.id;
            return (
              <li
                key={row.id}
                className="rounded-xl border border-border-subtle bg-surface overflow-hidden"
              >
                <button
                  type="button"
                  className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-surface-sunken/50 transition-colors"
                  onClick={() => setOpenId(isOpen ? null : row.id)}
                >
                  {isOpen ? (
                    <ChevronDown className="w-4 h-4 shrink-0 text-muted-foreground-tertiary" />
                  ) : (
                    <ChevronRight className="w-4 h-4 shrink-0 text-muted-foreground-tertiary" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-foreground truncate">{row.title}</p>
                    {row.description ? (
                      <p className="text-xs text-muted-foreground-tertiary mt-0.5 line-clamp-2">
                        {row.description}
                      </p>
                    ) : null}
                  </div>
                  <code className="hidden sm:block text-[10px] text-muted-foreground-tertiary font-mono truncate max-w-[120px]">
                    {row.id}
                  </code>
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 pt-0 space-y-3 border-t border-border-subtle/80 bg-surface-sunken/20">
                    <div className="flex flex-wrap gap-2 pt-3">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="text-xs"
                        onClick={() => void copyJson(row.id, row.spec)}
                      >
                        {copiedId === row.id ? (
                          <Check className="w-3.5 h-3.5 mr-1 text-mint-500" />
                        ) : (
                          <Copy className="w-3.5 h-3.5 mr-1" />
                        )}
                        {t('chat.workflowTemplatesPage.copySpec')}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-xs font-mono"
                        onClick={() => void copyDigest(row.id, row.digest)}
                      >
                        {copiedDigest === row.id ? (
                          <Check className="w-3.5 h-3.5 mr-1 text-mint-500" />
                        ) : (
                          <Copy className="w-3.5 h-3.5 mr-1" />
                        )}
                        {t('chat.workflowTemplatesPage.digestShort')}
                      </Button>
                    </div>
                    <pre
                      className={cn(
                        'text-[11px] leading-relaxed p-3 rounded-lg',
                        'bg-surface-raised border border-border-subtle',
                        'overflow-x-auto text-foreground font-mono',
                      )}
                    >
                      {JSON.stringify(row.spec, null, 2)}
                    </pre>
                    <p className="text-[10px] text-muted-foreground-tertiary font-mono break-all">
                      SHA-256: {row.digest}
                    </p>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </PageShell>
  );
}
