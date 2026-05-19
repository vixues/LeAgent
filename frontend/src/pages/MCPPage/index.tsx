import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Server,
  Plus,
  Trash2,
  Activity,
  Wrench,
  Link2,
  X,
} from 'lucide-react';
import {
  Button,
  Badge,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Input,
  Card,
  CardContent,
  Select,
  Textarea,
} from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import { EmptyState } from '@/components/common/EmptyState';
import { PageLoader } from '@/components/common/PageLoader';
import { cn } from '@/lib/utils';
import {
  useMCPServers,
  useMCPServerDetail,
  useMCPTools,
  useMCPHealth,
  useAddMCPServer,
  useRemoveMCPServer,
  useConnectMCPServer,
  useDisconnectMCPServer,
  type MCPServerCreateInput,
  type MCPServerDetail,
  type MCPServerInfo,
} from '@/hooks/useMCP';

type MCPAddFormState = MCPServerCreateInput & { argsText: string };

const defaultCreateForm = (): MCPAddFormState => ({
  name: '',
  transport: 'stdio',
  command: '',
  argsText: '',
  url: '',
  description: '',
  enabled: true,
  auto_connect: true,
});

function configPayloadFromDetail(detail: MCPServerDetail) {
  return {
    name: detail.name,
    transport: detail.transport,
    command: detail.command,
    args: detail.args,
    url: detail.url,
    env: detail.env,
    description: detail.description,
    enabled: detail.enabled,
    auto_connect: detail.auto_connect,
  };
}

export default function MCPPage() {
  const { t } = useTranslation();
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState<MCPAddFormState>(() => defaultCreateForm());
  const [selectedName, setSelectedName] = useState<string | null>(null);

  const { data: servers, isLoading: serversLoading, error: serversError } = useMCPServers();
  const { data: health, isLoading: healthLoading } = useMCPHealth();
  const {
    data: detail,
    isLoading: detailLoading,
    error: detailError,
  } = useMCPServerDetail(selectedName ?? '');
  const { data: serverTools, isLoading: toolsLoading } = useMCPTools(selectedName ?? undefined);

  const addServer = useAddMCPServer();
  const removeServer = useRemoveMCPServer();
  const connectServer = useConnectMCPServer();
  const disconnectServer = useDisconnectMCPServer();

  const sortedServers = useMemo(() => {
    if (!servers) return [];
    return [...servers].sort((a, b) => a.name.localeCompare(b.name));
  }, [servers]);

  useEffect(() => {
    if (!selectedName || !servers) return;
    if (!servers.some((s) => s.name === selectedName)) {
      setSelectedName(null);
    }
  }, [servers, selectedName]);

  const connectBusy = (name: string) =>
    connectServer.isPending && connectServer.variables === name;
  const disconnectBusy = (name: string) =>
    disconnectServer.isPending && disconnectServer.variables === name;

  const handleToggleConnection = async (e: React.MouseEvent, server: MCPServerInfo) => {
    e.stopPropagation();
    if (server.connected) {
      await disconnectServer.mutateAsync(server.name);
    } else {
      await connectServer.mutateAsync(server.name);
    }
  };

  const handleDelete = async (e: React.MouseEvent, name: string) => {
    e.stopPropagation();
    if (
      window.confirm(
        t('mcp.confirmDelete', { name })
      )
    ) {
      await removeServer.mutateAsync(name);
      if (selectedName === name) setSelectedName(null);
    }
  };

  const resetForm = () => {
    setForm(defaultCreateForm());
  };

  const handleAddSubmit = async () => {
    const args = form.argsText
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);

    const payload: MCPServerCreateInput = {
      name: form.name.trim(),
      transport: form.transport,
      args,
      enabled: form.enabled ?? true,
      auto_connect: form.auto_connect ?? true,
      description: (form.description ?? '').trim() || undefined,
    };

    if (form.transport === 'stdio') {
      payload.command = (form.command ?? '').trim() || undefined;
    } else {
      payload.url = (form.url ?? '').trim() || undefined;
    }

    await addServer.mutateAsync(payload);
    setAddOpen(false);
    resetForm();
  };

  const healthState: 'empty' | 'ok' | 'partial' =
    !health || health.total_count === 0
      ? 'empty'
      : health.connected_count === health.total_count
        ? 'ok'
        : 'partial';

  const serverHealthBlock =
    selectedName && health?.servers?.[selectedName] != null
      ? health.servers[selectedName]
      : null;

  const toolsForPanel = useMemo(() => {
    if (serverTools && serverTools.length > 0) return serverTools;
    if (detail?.tools?.length) {
      return detail.tools.map((tool) => ({
        name: tool.name,
        description: tool.description ?? '',
        inputSchema: {} as Record<string, unknown>,
        server_name: detail.name,
      }));
    }
    return [];
  }, [serverTools, detail]);

  return (
    // Dropped the one-off titleClassName="text-3xl" override: every page
    // header uses the same text-xl scale for visual consistency.
    <PageShell
      title={t('mcp.pageTitle')}
      description={t('mcp.pageDescription')}
      actions={
        <Button
          variant="primary"
          leftIcon={<Plus className="w-4 h-4" />}
          onClick={() => {
            resetForm();
            setAddOpen(true);
          }}
        >
          {t('mcp.addServer')}
        </Button>
      }
    >

        <Card className="border border-border/80 rounded-xl">
          <CardContent padding="md">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className={cn(
                    'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
                    healthState === 'ok'
                      ? 'bg-mint-100 dark:bg-mint-900/30 text-mint-600 dark:text-mint-400'
                      : healthState === 'partial'
                        ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                        : 'bg-surface-sunken text-muted-foreground'
                  )}
                >
                  <Activity className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">
                    {t('mcp.healthTitle')}
                  </p>
                  {healthLoading ? (
                    <p className="text-xs text-muted-foreground">
                      {t('common.loading')}
                    </p>
                  ) : health ? (
                    <p className="text-xs text-muted-foreground truncate">
                      {t('mcp.healthSummary', {
                        connected: health.connected_count,
                        total: health.total_count,
                      })}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">—</p>
                  )}
                </div>
              </div>
              {health && !healthLoading && (
                <Badge
                  variant={
                    healthState === 'ok'
                      ? 'success'
                      : healthState === 'partial'
                        ? 'warning'
                        : 'default'
                  }
                >
                  {healthState === 'ok'
                    ? t('mcp.healthAllConnected')
                    : healthState === 'partial'
                      ? t('mcp.healthPartial')
                      : t('mcp.healthNoServers')}
                </Badge>
              )}
            </div>
          </CardContent>
        </Card>

        {serversError && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200">
            {serversError instanceof Error ? serversError.message : String(serversError)}
          </div>
        )}

        <div className="grid gap-8 lg:grid-cols-5 items-start lg:items-stretch">
          <section className="lg:col-span-2">
            <Card className="border border-border/80 rounded-xl h-full">
              <CardContent padding="md" className="space-y-4">
                <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <Server className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                  {t('mcp.serverList')}
                </h2>

                {serversLoading ? (
                  <div className="flex justify-center py-12">
                    <PageLoader size="md" message={t('common.loading')} />
                  </div>
                ) : sortedServers.length === 0 ? (
                  <EmptyState
                    type="data"
                    title={t('mcp.noServers')}
                    description={t('mcp.noServersHint')}
                    size="sm"
                  />
                ) : (
                  <ul className="space-y-3">
                    {sortedServers.map((server) => {
                      const selected = selectedName === server.name;
                      return (
                        <li key={server.name}>
                          <div
                            role="button"
                            tabIndex={0}
                            onClick={() => setSelectedName(server.name)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                setSelectedName(server.name);
                              }
                            }}
                            className={cn(
                              'w-full text-left rounded-xl border transition-shadow',
                              'border-border/80 bg-surface/40',
                              'hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
                              selected &&
                                'ring-2 ring-primary-500 border-primary-300 dark:border-primary-700'
                            )}
                          >
                            <div className="p-4">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="font-medium text-foreground truncate">
                                      {server.name}
                                    </span>
                                    <Badge variant="default" size="sm">
                                      {server.transport}
                                    </Badge>
                                    <Badge
                                      variant={server.connected ? 'success' : 'error'}
                                      size="sm"
                                    >
                                      {server.connected
                                        ? t('mcp.status.connected')
                                        : t('mcp.status.disconnected')}
                                    </Badge>
                                  </div>
                                  <p className="mt-2 text-xs text-muted-foreground inline-flex items-center gap-1">
                                    <Wrench className="w-3.5 h-3.5" />
                                    {t('mcp.counts.tools', { n: server.tool_count })}
                                  </p>
                                </div>
                                <div
                                  className="flex flex-col items-end gap-2 shrink-0"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <Button
                                    type="button"
                                    variant={server.connected ? 'secondary' : 'primary'}
                                    size="sm"
                                    loading={connectBusy(server.name) || disconnectBusy(server.name)}
                                    disabled={
                                      !server.enabled ||
                                      connectBusy(server.name) ||
                                      disconnectBusy(server.name)
                                    }
                                    onClick={(e) => void handleToggleConnection(e, server)}
                                  >
                                    {server.connected
                                      ? t('mcp.disconnect')
                                      : t('mcp.connect')}
                                  </Button>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    className="text-red-600 hover:text-red-700 dark:text-red-400"
                                    onClick={(e) => void handleDelete(e, server.name)}
                                    disabled={removeServer.isPending}
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </Button>
                                </div>
                              </div>
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </CardContent>
            </Card>
          </section>

          <section className="lg:col-span-3 min-h-[320px]">
            <Card className="border border-border/80 rounded-xl h-full">
              <CardContent padding="md" className="space-y-4">
                <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <Wrench className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                  {t('mcp.detailTitle')}
                </h2>

                {!selectedName ? (
                  <EmptyState
                    type="search"
                    title={t('mcp.selectServer')}
                    description={t('mcp.selectServerHint')}
                    size="sm"
                  />
                ) : detailLoading ? (
                  <div className="flex justify-center py-16">
                    <PageLoader size="md" message={t('common.loading')} />
                  </div>
                ) : detailError ? (
                  <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200">
                    {detailError instanceof Error ? detailError.message : String(detailError)}
                  </div>
                ) : detail ? (
                  <div className="space-y-6">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-semibold text-foreground">
                          {detail.name}
                        </h3>
                        <div className="mt-1 flex flex-wrap gap-2">
                          <Badge variant="default" size="sm">
                            {detail.transport}
                          </Badge>
                          <Badge variant={detail.connected ? 'success' : 'error'} size="sm">
                            {detail.connected
                              ? t('mcp.status.connected')
                              : t('mcp.status.disconnected')}
                          </Badge>
                        </div>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-label={t('mcp.clearSelection')}
                        onClick={() => setSelectedName(null)}
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>

                    <div>
                      <h4 className="text-sm font-semibold text-foreground mb-2">
                        {t('mcp.section.config')}
                      </h4>
                      <pre className="text-xs font-mono rounded-xl border border-border bg-surface-sunken/80 p-3 overflow-x-auto max-h-56 overflow-y-auto">
                        {JSON.stringify(configPayloadFromDetail(detail), null, 2)}
                      </pre>
                    </div>

                    <div>
                      <h4 className="text-sm font-semibold text-foreground mb-2">
                        {t('mcp.section.health')}
                      </h4>
                      <div className="space-y-2 text-sm">
                        {detail.health != null && Object.keys(detail.health).length > 0 ? (
                          <pre className="text-xs font-mono rounded-xl border border-border bg-surface-sunken/80 p-3 overflow-x-auto max-h-40 overflow-y-auto">
                            {JSON.stringify(detail.health, null, 2)}
                          </pre>
                        ) : (
                          <p className="text-muted-foreground text-xs">
                            {t('mcp.healthDetailEmpty')}
                          </p>
                        )}
                        {serverHealthBlock != null && (
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">
                              {t('mcp.healthFromAggregator')}
                            </p>
                            <pre className="text-xs font-mono rounded-xl border border-border bg-surface-sunken/80 p-3 overflow-x-auto max-h-40 overflow-y-auto">
                              {JSON.stringify(serverHealthBlock, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    </div>

                    <div>
                      <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                        <Link2 className="w-4 h-4 text-primary-600 dark:text-primary-400" />
                        {t('mcp.section.tools')}
                      </h4>
                      {toolsLoading ? (
                        <div className="flex justify-center py-8">
                          <PageLoader size="sm" message={t('common.loading')} />
                        </div>
                      ) : toolsForPanel.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          {t('mcp.noToolsForServer')}
                        </p>
                      ) : (
                        <ul className="rounded-xl border border-border divide-y divide-border-subtle max-h-64 overflow-y-auto">
                          {toolsForPanel.map((tool) => (
                            <li
                              key={`${tool.server_name}:${tool.name}`}
                              className="px-3 py-2.5 text-sm hover:bg-surface-sunken/80"
                            >
                              <span className="font-mono text-xs text-primary-700 dark:text-primary-300">
                                {tool.name}
                              </span>
                              {tool.description ? (
                                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                                  {tool.description}
                                </p>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </section>
        </div>

      <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} size="md">
        <ModalHeader onClose={() => setAddOpen(false)}>
          {t('mcp.addServerTitle')}
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              {t('mcp.form.name')}
            </label>
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder={t('mcp.form.namePlaceholder')}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              {t('mcp.form.transport')}
            </label>
            <Select
              value={form.transport}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  transport: e.target.value as MCPServerCreateInput['transport'],
                }))
              }
            >
              <option value="stdio">stdio</option>
              <option value="sse">SSE</option>
            </Select>
          </div>
          {form.transport === 'stdio' ? (
            <>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  {t('mcp.form.command')}
                </label>
                <Input
                  value={form.command}
                  onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                  placeholder={t('mcp.form.commandPlaceholder')}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  {t('mcp.form.args')}
                </label>
                <Textarea
                  rows={3}
                  value={form.argsText}
                  onChange={(e) => setForm((f) => ({ ...f, argsText: e.target.value }))}
                  placeholder={t('mcp.form.argsPlaceholder')}
                  className="font-mono text-xs"
                />
              </div>
            </>
          ) : (
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                {t('mcp.form.url')}
              </label>
              <Input
                value={form.url}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                placeholder={t('integrations.placeholderUrl')}
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              {t('mcp.form.description')}
            </label>
            <Input
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex flex-wrap gap-6">
            <label className="inline-flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                className="rounded border-border"
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
              {t('mcp.form.enabled')}
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                className="rounded border-border"
                checked={form.auto_connect}
                onChange={(e) => setForm((f) => ({ ...f, auto_connect: e.target.checked }))}
              />
              {t('mcp.form.autoConnect')}
            </label>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setAddOpen(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            variant="primary"
            onClick={() => void handleAddSubmit()}
            disabled={!form.name.trim() || addServer.isPending}
            loading={addServer.isPending}
          >
            {t('mcp.form.submit')}
          </Button>
        </ModalFooter>
      </Modal>
    </PageShell>
  );
}
