import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus,
  MessageSquare,
  Hash,
  Users,
  Globe,
  Code,
  Terminal,
  FlaskConical,
  Power,
  PowerOff,
  Edit2,
  Trash2,
} from 'lucide-react';
import { PageShell } from '@/components/layout/PageShell';
import { EmptyState } from '@/components/common/EmptyState';
import { PageLoader } from '@/components/common/PageLoader';
import {
  Button,
  Card,
  CardContent,
  Input,
  Switch,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Select,
  Badge,
} from '@/components/ui';
import { useToast } from '@/components/ui/Toaster';
import { cn } from '@/lib/utils';
import {
  useChannelsList,
  useChannelDetail,
  useCreateChannel,
  useUpdateChannel,
  useDeleteChannel,
  useTestChannel,
  useActivateChannel,
  useDeactivateChannel,
  type ChannelConfig,
  type ChannelType,
  type ChannelStatus,
} from '@/hooks/useChannels';

const TYPE_ICONS: Record<ChannelType, typeof MessageSquare> = {
  dingtalk: MessageSquare,
  feishu: Hash,
  wechat_work: Users,
  web: Globe,
  api: Code,
  console: Terminal,
};

/** Icon container + type badge styling per channel kind */
const TYPE_PRESENTATION: Record<
  ChannelType,
  { iconWrap: string; typeBadge: 'default' | 'primary' | 'success' | 'warning' | 'error' | 'info' }
> = {
  dingtalk: {
    iconWrap:
      'bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300 ring-1 ring-blue-200/60 dark:ring-blue-800/60',
    typeBadge: 'primary',
  },
  feishu: {
    iconWrap:
      'bg-blue-100 text-blue-800 dark:bg-blue-950/50 dark:text-blue-300 ring-1 ring-blue-200/60 dark:ring-blue-800/60',
    typeBadge: 'info',
  },
  wechat_work: {
    iconWrap:
      'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 ring-1 ring-emerald-200/60 dark:ring-emerald-800/60',
    typeBadge: 'success',
  },
  web: {
    iconWrap:
      'bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300 ring-1 ring-sky-200/60 dark:ring-sky-800/60',
    typeBadge: 'info',
  },
  api: {
    iconWrap:
      'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 ring-1 ring-amber-200/60 dark:ring-amber-800/60',
    typeBadge: 'warning',
  },
  console: {
    iconWrap:
      'bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-200 ring-1 ring-slate-300/60 dark:ring-slate-600/60',
    typeBadge: 'default',
  },
};

const STATUS_STYLE: Record<ChannelStatus, 'success' | 'default' | 'error'> = {
  active: 'success',
  inactive: 'default',
  error: 'error',
};

function defaultConfigForType(type: ChannelType): Record<string, unknown> {
  switch (type) {
    case 'dingtalk':
    case 'wechat_work':
      return { webhook_url: '', secret: '' };
    case 'feishu':
      return { app_id: '', app_secret: '', webhook_url: '' };
    case 'web':
      return { url: '' };
    case 'api':
      return { base_url: '', api_key: '' };
    case 'console':
      return {};
    default:
      return {};
  }
}

export default function ChannelsPage() {
  const { t } = useTranslation();
  const { toast } = useToast();

  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [channelType, setChannelType] = useState<ChannelType>('dingtalk');
  const [enabled, setEnabled] = useState(true);
  const [config, setConfig] = useState<Record<string, unknown>>({});

  const filters = useMemo(
    () => ({
      status: statusFilter || undefined,
      channel_type: typeFilter || undefined,
    }),
    [statusFilter, typeFilter]
  );

  const { data: listData, isLoading } = useChannelsList(filters);
  const { data: detail } = useChannelDetail(editingId ?? '', {
    enabled: modalOpen && !!editingId,
  });

  const createMutation = useCreateChannel();
  const updateMutation = useUpdateChannel();
  const deleteMutation = useDeleteChannel();
  const testMutation = useTestChannel();
  const activateMutation = useActivateChannel();
  const deactivateMutation = useDeactivateChannel();

  useEffect(() => {
    if (!modalOpen) return;
    if (editingId && detail) {
      setName(detail.name);
      setChannelType(detail.channel_type);
      setEnabled(detail.enabled);
      setConfig(
        detail.config && typeof detail.config === 'object' && !Array.isArray(detail.config)
          ? { ...detail.config }
          : {}
      );
    }
    if (!editingId && modalOpen) {
      setName('');
      setChannelType('dingtalk');
      setEnabled(true);
      setConfig(defaultConfigForType('dingtalk'));
    }
  }, [modalOpen, editingId, detail]);

  const channels = listData?.channels ?? [];

  const openCreate = () => {
    setEditingId(null);
    setName('');
    setChannelType('dingtalk');
    setEnabled(true);
    setConfig(defaultConfigForType('dingtalk'));
    setModalOpen(true);
  };

  const openEdit = (c: ChannelConfig) => {
    setEditingId(c.id);
    setName(c.name);
    setChannelType(c.channel_type);
    setEnabled(c.enabled);
    setConfig(
      c.config && typeof c.config === 'object' && !Array.isArray(c.config) ? { ...c.config } : {}
    );
    setModalOpen(true);
  };

  const setConfigField = (key: string, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const handleTypeChange = (next: ChannelType) => {
    setChannelType(next);
    if (!editingId) {
      setConfig(defaultConfigForType(next));
    }
  };

  const handleSave = async () => {
    if (!name.trim()) {
      toast({
        title: t('channels.validation'),
        description: t('channels.nameRequired'),
        variant: 'error',
      });
      return;
    }
    try {
      if (editingId) {
        await updateMutation.mutateAsync({
          id: editingId,
          name: name.trim(),
          config,
          enabled,
        });
        toast({ title: t('channels.updated') });
      } else {
        await createMutation.mutateAsync({
          name: name.trim(),
          channel_type: channelType,
          config,
          enabled,
        });
        toast({ title: t('channels.created') });
      }
      setModalOpen(false);
      setEditingId(null);
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const handleDelete = async (c: ChannelConfig) => {
    if (!window.confirm(t('channels.confirmDelete', { name: c.name }))) return;
    try {
      await deleteMutation.mutateAsync(c.id);
      toast({ title: t('channels.deleted') });
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testMutation.mutateAsync(id);
      toast({
        title: t('channels.testSent'),
        description: res.success
          ? t('channels.testOk', { ms: String(res.latency_ms) })
          : (res.error ?? t('channels.testFailed')),
        variant: res.success ? undefined : 'error',
      });
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const handleActivate = async (id: string) => {
    try {
      await activateMutation.mutateAsync(id);
      toast({ title: t('channels.activated') });
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const handleDeactivate = async (id: string) => {
    try {
      await deactivateMutation.mutateAsync(id);
      toast({ title: t('channels.deactivated') });
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const handleEnabledToggle = async (c: ChannelConfig, next: boolean) => {
    try {
      await updateMutation.mutateAsync({ id: c.id, enabled: next });
      toast({
        title: next ? t('channels.enabled') : t('channels.disabled'),
      });
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const renderConfigFields = () => {
    switch (channelType) {
      case 'dingtalk':
      case 'wechat_work':
        return (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('channels.fields.webhookUrl')}
              </label>
              <Input
                value={String(config.webhook_url ?? '')}
                onChange={(e) => setConfigField('webhook_url', e.target.value)}
                placeholder={t('integrations.placeholderUrl')}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('channels.fields.secret')}
              </label>
              <Input
                type="password"
                value={String(config.secret ?? '')}
                onChange={(e) => setConfigField('secret', e.target.value)}
                autoComplete="off"
              />
            </div>
          </>
        );
      case 'feishu':
        return (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('channels.fields.appId')}
              </label>
              <Input
                value={String(config.app_id ?? '')}
                onChange={(e) => setConfigField('app_id', e.target.value)}
                autoComplete="off"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('channels.fields.appSecret')}
              </label>
              <Input
                type="password"
                value={String(config.app_secret ?? '')}
                onChange={(e) => setConfigField('app_secret', e.target.value)}
                autoComplete="off"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('channels.fields.webhookUrl')}
              </label>
              <Input
                value={String(config.webhook_url ?? '')}
                onChange={(e) => setConfigField('webhook_url', e.target.value)}
                placeholder={t('integrations.placeholderUrl')}
              />
            </div>
          </>
        );
      case 'web':
        return (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('channels.fields.url')}
            </label>
            <Input
              value={String(config.url ?? '')}
              onChange={(e) => setConfigField('url', e.target.value)}
              placeholder={t('integrations.placeholderUrl')}
            />
          </div>
        );
      case 'api':
        return (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('channels.fields.baseUrl')}
              </label>
              <Input
                value={String(config.base_url ?? '')}
                onChange={(e) => setConfigField('base_url', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('channels.fields.apiKey')}
              </label>
              <Input
                type="password"
                value={String(config.api_key ?? '')}
                onChange={(e) => setConfigField('api_key', e.target.value)}
                autoComplete="off"
              />
            </div>
          </>
        );
      case 'console':
        return (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('channels.consoleHint')}
          </p>
        );
      default:
        return null;
    }
  };

  return (
    <PageShell
      title={t('channels.title')}
      description={t('channels.subtitle')}
      icon={<MessageSquare className="w-5 h-5" />}
      actions={
        <Button onClick={openCreate} leftIcon={<Plus className="w-4 h-4" />}>
          {t('channels.add')}
        </Button>
      }
    >
        <div className="flex flex-wrap gap-3">
          <Select
            className="w-44"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label={t('channels.filterStatus')}
          >
            <option value="">{t('channels.allStatuses')}</option>
            <option value="active">active</option>
            <option value="inactive">inactive</option>
            <option value="error">error</option>
          </Select>
          <Select
            className="w-44"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            aria-label={t('channels.filterType')}
          >
            <option value="">{t('channels.allTypes')}</option>
            <option value="dingtalk">dingtalk</option>
            <option value="feishu">feishu</option>
            <option value="wechat_work">wechat_work</option>
            <option value="web">web</option>
            <option value="api">api</option>
            <option value="console">console</option>
          </Select>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-20">
            <PageLoader size="md" message={t('common.loading')} />
          </div>
        ) : channels.length === 0 ? (
          <EmptyState
            title={t('channels.empty')}
            description={t('channels.emptyHint')}
            action={{ label: t('channels.add'), onClick: openCreate }}
          />
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {channels.map((c) => {
              const Icon = TYPE_ICONS[c.channel_type] ?? MessageSquare;
              const look = TYPE_PRESENTATION[c.channel_type] ?? TYPE_PRESENTATION.console;
              return (
                <Card key={c.id} padding="md" className="flex flex-col">
                  <CardContent padding="none" className="flex flex-col flex-1 gap-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-3 min-w-0">
                        <div
                          className={cn(
                            'flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center',
                            look.iconWrap
                          )}
                        >
                          <Icon className="w-5 h-5" />
                        </div>
                        <div className="min-w-0">
                          <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                            {c.name}
                          </h3>
                          <Badge variant={look.typeBadge} size="sm" className="mt-1 font-mono text-[10px] uppercase">
                            {c.channel_type}
                          </Badge>
                        </div>
                      </div>
                      <Badge variant={STATUS_STYLE[c.status] ?? 'default'} size="sm">
                        {c.status}
                      </Badge>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-gray-800">
                      <span className="text-sm text-gray-600 dark:text-gray-400">
                        {t('channels.enabled')}
                      </span>
                      <Switch
                        checked={c.enabled}
                        onChange={(e) => handleEnabledToggle(c, e.target.checked)}
                        disabled={updateMutation.isPending}
                      />
                    </div>

                    <div className="flex flex-wrap gap-2 mt-auto">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        leftIcon={<FlaskConical className="w-4 h-4" />}
                        onClick={() => handleTest(c.id)}
                        disabled={testMutation.isPending}
                      >
                        {t('channels.testConnection')}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        leftIcon={<Power className="w-4 h-4" />}
                        onClick={() => handleActivate(c.id)}
                        disabled={activateMutation.isPending || c.status === 'active'}
                      >
                        {t('channels.activate')}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        leftIcon={<PowerOff className="w-4 h-4" />}
                        onClick={() => handleDeactivate(c.id)}
                        disabled={deactivateMutation.isPending || c.status === 'inactive'}
                      >
                        {t('channels.deactivate')}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        leftIcon={<Edit2 className="w-4 h-4" />}
                        onClick={() => openEdit(c)}
                      >
                        {t('common.edit')}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-red-600 dark:text-red-400"
                        leftIcon={<Trash2 className="w-4 h-4" />}
                        onClick={() => handleDelete(c)}
                      >
                        {t('common.delete')}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} size="lg">
          <ModalHeader onClose={() => setModalOpen(false)}>
            {editingId ? t('channels.edit') : t('channels.create')}
          </ModalHeader>
          <ModalBody className="space-y-4 max-h-[70vh] overflow-y-auto">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('channels.fields.name')}
              </label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('channels.fields.type')}
              </label>
              <Select
                value={channelType}
                onChange={(e) => handleTypeChange(e.target.value as ChannelType)}
                disabled={!!editingId}
              >
                <option value="dingtalk">dingtalk</option>
                <option value="feishu">feishu</option>
                <option value="wechat_work">wechat_work</option>
                <option value="web">web</option>
                <option value="api">api</option>
                <option value="console">console</option>
              </Select>
            </div>
            {renderConfigFields()}
            <div className="flex items-center justify-between rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2">
              <span className="text-sm text-gray-700 dark:text-gray-300">{t('channels.enabled')}</span>
              <Switch checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            </div>
          </ModalBody>
          <ModalFooter>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSave} loading={createMutation.isPending || updateMutation.isPending}>
              {t('common.save')}
            </Button>
          </ModalFooter>
        </Modal>
    </PageShell>
  );
}
