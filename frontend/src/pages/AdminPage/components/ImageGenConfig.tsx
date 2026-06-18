import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus,
  Trash2,
  Star,
  FlaskConical,
  Cpu,
  KeyRound,
  Server,
  Pencil,
  Image as ImageIcon,
  Film,
  Music,
  Plug,
} from 'lucide-react';
import {
  Card,
  CardContent,
  Button,
  Input,
  Select,
  Switch,
  Badge,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Textarea,
} from '@/components/ui';
import { useToast } from '@/components/ui/Toaster';
import {
  useImageGenPresets,
  useImageGenDefault,
  useImageGenBackends,
  useImageGenCredentials,
  useImageGenLocal,
  useImageGenModels,
  useImageGenCustomProviders,
  useCreatePreset,
  useUpdatePreset,
  useDeletePreset,
  useSetDefaultPreset,
  useSetCredentials,
  useSetLocalConfig,
  useTestImageGen,
  useCreateCustomProvider,
  useUpdateCustomProvider,
  useDeleteCustomProvider,
} from '@/hooks/useImageGen';
import type {
  ImageGenPreset,
  ImageGenLocalConfig,
  ImageGenKind,
  ImageGenCustomProvider,
  ImageGenCustomProviderUpdate,
} from '@/types/admin';

const KIND_TABS: { kind: ImageGenKind; icon: typeof ImageIcon }[] = [
  { kind: 'image', icon: ImageIcon },
  { kind: 'video', icon: Film },
  { kind: 'audio', icon: Music },
];

interface PresetForm {
  id: string;
  label: string;
  backend: string;
  model: string;
  kind: ImageGenKind;
  width: string;
  height: string;
  steps: string;
  guidance: string;
  advancedJson: string;
  enabled: boolean;
}

const emptyPreset = (kind: ImageGenKind): PresetForm => ({
  id: '',
  label: '',
  backend: kind === 'image' ? 'siliconflow' : kind === 'audio' ? 'elevenlabs' : 'replicate',
  model: '',
  kind,
  width: '1024',
  height: '1024',
  steps: '20',
  guidance: '7.5',
  advancedJson: '{}',
  enabled: true,
});

function presetToForm(p: ImageGenPreset): PresetForm {
  const params = { ...(p.params ?? {}) } as Record<string, unknown>;
  const num = (k: string, d: string) => (params[k] !== undefined ? String(params[k]) : d);
  const known = ['width', 'height', 'num_inference_steps', 'guidance_scale'];
  const advanced: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) if (!known.includes(k)) advanced[k] = v;
  return {
    id: p.id,
    label: p.label,
    backend: p.backend,
    model: p.model,
    kind: (p.kind as ImageGenKind) || 'image',
    width: num('width', '1024'),
    height: num('height', '1024'),
    steps: num('num_inference_steps', '20'),
    guidance: num('guidance_scale', '7.5'),
    advancedJson: Object.keys(advanced).length ? JSON.stringify(advanced, null, 2) : '{}',
    enabled: p.enabled,
  };
}

function formToPreset(f: PresetForm): ImageGenPreset {
  let advanced: Record<string, unknown> = {};
  try {
    advanced = JSON.parse(f.advancedJson || '{}');
  } catch {
    advanced = {};
  }
  const params: Record<string, unknown> = { ...advanced };
  if (f.kind === 'image') {
    if (f.width) params.width = Number(f.width);
    if (f.height) params.height = Number(f.height);
    if (f.steps) params.num_inference_steps = Number(f.steps);
    if (f.guidance) params.guidance_scale = Number(f.guidance);
  }
  return {
    id: f.id.trim(),
    label: f.label.trim() || f.id.trim(),
    backend: f.backend,
    model: f.model.trim(),
    kind: f.kind,
    params,
    enabled: f.enabled,
  };
}

export function ImageGenConfig() {
  const { t } = useTranslation();
  const { toast } = useToast();

  const [kind, setKind] = useState<ImageGenKind>('image');

  const { data: presets, isLoading } = useImageGenPresets();
  const { data: def } = useImageGenDefault();
  const { data: backends } = useImageGenBackends();

  const createPreset = useCreatePreset();
  const updatePreset = useUpdatePreset();
  const deletePreset = useDeletePreset();
  const setDefault = useSetDefaultPreset();
  const testGen = useTestImageGen();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PresetForm>(emptyPreset('image'));

  const { data: modelOptions } = useImageGenModels(modalOpen ? form.backend : undefined);

  const kindBackends = useMemo(
    () => (backends ?? []).filter((b) => b.kinds.includes(form.kind)),
    [backends, form.kind],
  );

  const visiblePresets = useMemo(
    () => (presets ?? []).filter((p) => (p.kind || 'image') === kind),
    [presets, kind],
  );

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyPreset(kind));
    setModalOpen(true);
  };

  const openEdit = (p: ImageGenPreset) => {
    setEditingId(p.id);
    setForm(presetToForm(p));
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.id.trim()) {
      toast({ variant: 'error', title: t('admin.imageGen.preset.idRequired') });
      return;
    }
    const payload = formToPreset(form);
    try {
      if (editingId) {
        await updatePreset.mutateAsync({ id: editingId, data: payload });
      } else {
        await createPreset.mutateAsync(payload);
      }
      toast({ variant: 'success', title: t('admin.imageGen.preset.saved') });
      setModalOpen(false);
    } catch (e) {
      toast({
        variant: 'error',
        title: t('admin.imageGen.preset.saveError'),
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deletePreset.mutateAsync(id);
      toast({ variant: 'success', title: t('admin.imageGen.preset.deleted') });
    } catch (e) {
      toast({ variant: 'error', title: t('admin.imageGen.preset.deleteError'), description: e instanceof Error ? e.message : String(e) });
    }
  };

  const handleSetDefault = async (id: string) => {
    try {
      await setDefault.mutateAsync(id);
      toast({ variant: 'success', title: t('admin.imageGen.default.updated') });
    } catch (e) {
      toast({ variant: 'error', title: t('admin.imageGen.default.error'), description: e instanceof Error ? e.message : String(e) });
    }
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testGen.mutateAsync({ preset_id: id });
      if (res.success) {
        toast({
          variant: res.placeholder ? 'warning' : 'success',
          title: res.placeholder ? t('admin.imageGen.test.placeholder') : t('admin.imageGen.test.ok'),
          description: `${res.provider}${res.model ? ` · ${res.model}` : ''}`,
        });
      } else {
        toast({ variant: 'error', title: t('admin.imageGen.test.failed'), description: res.error });
      }
    } catch (e) {
      toast({ variant: 'error', title: t('admin.imageGen.test.failed'), description: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header + kind segmented filter */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-foreground">{t('admin.imageGen.title')}</h3>
          <p className="text-sm text-muted-foreground">{t('admin.imageGen.subtitle')}</p>
        </div>
        <div className="inline-flex rounded-lg border border-border bg-surface-sunken p-0.5">
          {KIND_TABS.map(({ kind: k, icon: Icon }) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                kind === k ? 'bg-surface text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icon className="h-4 w-4" />
              {t(`admin.imageGen.kind.${k}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Default preset (workflow-level active model) */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col gap-0.5">
            <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Star className="h-4 w-4" /> {t('admin.imageGen.default.title')}
            </h4>
            <p className="text-xs text-muted-foreground">{t('admin.imageGen.default.help')}</p>
          </div>
          <div className="mt-3 max-w-md">
            <Select value={def?.preset_id ?? ''} onChange={(e) => handleSetDefault(e.target.value)}>
              <option value="">{t('admin.imageGen.default.none')}</option>
              {(presets ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label} ({p.kind || 'image'} · {p.backend})
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Presets (filtered by kind) */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h4 className="text-sm font-semibold text-foreground">{t('admin.imageGen.presets.title')}</h4>
            <p className="text-xs text-muted-foreground">{t('admin.imageGen.presets.help')}</p>
          </div>
          <Button onClick={openCreate} size="sm" leftIcon={<Plus className="h-4 w-4" />}>
            {t('admin.imageGen.presets.add')}
          </Button>
        </div>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : visiblePresets.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('admin.imageGen.presets.empty')}</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {visiblePresets.map((p) => (
              <Card key={p.id} className="overflow-hidden">
                <CardContent className="p-3 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm text-foreground truncate">{p.label}</span>
                        {def?.preset_id === p.id && (
                          <Badge variant="success" className="shrink-0">{t('admin.imageGen.default.badge')}</Badge>
                        )}
                        {!p.enabled && <Badge variant="secondary">{t('admin.imageGen.preset.disabled')}</Badge>}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5 truncate">
                        {p.backend}{p.model ? ` · ${p.model}` : ''}
                      </p>
                    </div>
                  </div>
                  <code className="block text-[11px] text-muted-foreground bg-surface-sunken rounded px-2 py-1 truncate">
                    {Object.entries(p.params ?? {}).map(([k, v]) => `${k}=${v}`).join(', ') || '—'}
                  </code>
                  <div className="flex items-center gap-1 flex-wrap">
                    <Button size="sm" variant="ghost" leftIcon={<Pencil className="h-3.5 w-3.5" />} onClick={() => openEdit(p)}>
                      {t('common.edit')}
                    </Button>
                    <Button size="sm" variant="ghost" leftIcon={<FlaskConical className="h-3.5 w-3.5" />} onClick={() => handleTest(p.id)} disabled={testGen.isPending}>
                      {t('admin.imageGen.test.button')}
                    </Button>
                    {def?.preset_id !== p.id && (
                      <Button size="sm" variant="ghost" leftIcon={<Star className="h-3.5 w-3.5" />} onClick={() => handleSetDefault(p.id)}>
                        {t('admin.imageGen.default.set')}
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" className="text-red-500" onClick={() => handleDelete(p.id)}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* Custom providers */}
      <CustomProviders kind={kind} />

      {/* Backends + credentials */}
      <BackendCredentials />

      {/* Local diffusion (image only) */}
      {kind === 'image' && <LocalDiffusion />}

      {/* Preset editor modal */}
      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} size="2xl">
        <ModalHeader onClose={() => setModalOpen(false)}>
          {editingId ? t('admin.imageGen.preset.editTitle') : t('admin.imageGen.preset.newTitle')}
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label={t('admin.imageGen.preset.id')}>
              <Input
                value={form.id}
                disabled={!!editingId}
                onChange={(e) => setForm({ ...form, id: e.target.value })}
                placeholder="kolors-hi"
              />
            </Field>
            <Field label={t('admin.imageGen.preset.label')}>
              <Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
            </Field>
            <Field label={t('admin.imageGen.preset.kind')}>
              <Select
                value={form.kind}
                disabled={!!editingId}
                onChange={(e) => setForm({ ...form, kind: e.target.value as ImageGenKind, backend: '', model: '' })}
              >
                {KIND_TABS.map(({ kind: k }) => (
                  <option key={k} value={k}>{t(`admin.imageGen.kind.${k}`)}</option>
                ))}
              </Select>
            </Field>
            <Field label={t('admin.imageGen.preset.backend')}>
              <Select value={form.backend} onChange={(e) => setForm({ ...form, backend: e.target.value, model: '' })}>
                {form.backend && !kindBackends.some((b) => b.name === form.backend) && (
                  <option value={form.backend}>{form.backend}</option>
                )}
                {kindBackends.length === 0 && !form.backend && <option value="">—</option>}
                {kindBackends.map((b) => (
                  <option key={b.name} value={b.name}>
                    {b.name}{b.available ? '' : ` (${t('admin.imageGen.backend.unconfigured')})`}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t('admin.imageGen.preset.model')}>
              <Select value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>
                <option value="">{t('admin.imageGen.preset.modelDefault')}</option>
                {(modelOptions ?? []).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
                {form.model && !(modelOptions ?? []).includes(form.model) && (
                  <option value={form.model}>{form.model}</option>
                )}
              </Select>
            </Field>
            {form.kind === 'image' && (
              <>
                <Field label={t('admin.imageGen.preset.width')}>
                  <Input type="number" value={form.width} onChange={(e) => setForm({ ...form, width: e.target.value })} />
                </Field>
                <Field label={t('admin.imageGen.preset.height')}>
                  <Input type="number" value={form.height} onChange={(e) => setForm({ ...form, height: e.target.value })} />
                </Field>
                <Field label={t('admin.imageGen.preset.steps')}>
                  <Input type="number" value={form.steps} onChange={(e) => setForm({ ...form, steps: e.target.value })} />
                </Field>
                <Field label={t('admin.imageGen.preset.guidance')}>
                  <Input type="number" step="0.1" value={form.guidance} onChange={(e) => setForm({ ...form, guidance: e.target.value })} />
                </Field>
              </>
            )}
          </div>
          <Field label={t('admin.imageGen.preset.advanced')}>
            <Textarea
              rows={4}
              className="font-mono text-xs"
              value={form.advancedJson}
              onChange={(e) => setForm({ ...form, advancedJson: e.target.value })}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <Switch checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} />
            {t('admin.imageGen.preset.enabled')}
          </label>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} disabled={createPreset.isPending || updatePreset.isPending}>
            {t('common.save')}
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}

interface CustomProviderForm {
  name: string;
  kinds: ImageGenKind[];
  protocol: 'openai' | 'http';
  base_url: string;
  api_key: string;
  models: string;
  enabled: boolean;
}

const emptyProvider = (kind: ImageGenKind): CustomProviderForm => ({
  name: '',
  kinds: [kind],
  protocol: 'openai',
  base_url: '',
  api_key: '',
  models: '',
  enabled: true,
});

function CustomProviders({ kind }: { kind: ImageGenKind }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data: providers } = useImageGenCustomProviders();
  const createProvider = useCreateCustomProvider();
  const updateProvider = useUpdateCustomProvider();
  const deleteProvider = useDeleteCustomProvider();

  const [open, setOpen] = useState(false);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [form, setForm] = useState<CustomProviderForm>(emptyProvider(kind));

  const visible = useMemo(
    () => (providers ?? []).filter((p) => p.kinds.includes(kind)),
    [providers, kind],
  );

  const openCreate = () => {
    setEditingName(null);
    setForm(emptyProvider(kind));
    setOpen(true);
  };

  const openEdit = (p: ImageGenCustomProvider) => {
    setEditingName(p.name);
    setForm({
      name: p.name,
      kinds: (p.kinds as ImageGenKind[]) || [kind],
      protocol: p.protocol,
      base_url: p.base_url,
      api_key: '',
      models: (p.models ?? []).join(', '),
      enabled: p.enabled,
    });
    setOpen(true);
  };

  const toggleKind = (k: ImageGenKind) => {
    setForm((f) => ({
      ...f,
      kinds: f.kinds.includes(k) ? f.kinds.filter((x) => x !== k) : [...f.kinds, k],
    }));
  };

  const save = async () => {
    if (!form.name.trim()) {
      toast({ variant: 'error', title: t('admin.imageGen.provider.nameRequired') });
      return;
    }
    const payload: ImageGenCustomProviderUpdate = {
      name: form.name.trim(),
      kinds: form.kinds.length ? form.kinds : ['image'],
      protocol: form.protocol,
      base_url: form.base_url.trim(),
      api_key: form.api_key.trim() || undefined,
      models: form.models.split(',').map((m) => m.trim()).filter(Boolean),
      enabled: form.enabled,
    };
    try {
      if (editingName) {
        await updateProvider.mutateAsync({ name: editingName, data: payload });
      } else {
        await createProvider.mutateAsync(payload);
      }
      toast({ variant: 'success', title: t('admin.imageGen.provider.saved') });
      setOpen(false);
    } catch (e) {
      toast({ variant: 'error', title: t('admin.imageGen.provider.saveError'), description: e instanceof Error ? e.message : String(e) });
    }
  };

  const remove = async (name: string) => {
    try {
      await deleteProvider.mutateAsync(name);
      toast({ variant: 'success', title: t('admin.imageGen.provider.deleted') });
    } catch (e) {
      toast({ variant: 'error', title: t('admin.imageGen.provider.deleteError'), description: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Plug className="h-4 w-4" /> {t('admin.imageGen.provider.title')}
          </h4>
          <p className="text-xs text-muted-foreground">{t('admin.imageGen.provider.help')}</p>
        </div>
        <Button onClick={openCreate} size="sm" variant="secondary" leftIcon={<Plus className="h-4 w-4" />}>
          {t('admin.imageGen.provider.add')}
        </Button>
      </div>
      {visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('admin.imageGen.provider.empty')}</p>
      ) : (
        <div className="space-y-2">
          {visible.map((p) => (
            <Card key={p.name}>
              <CardContent className="p-3 flex flex-col lg:flex-row lg:items-center gap-3">
                <div className="flex items-center gap-2 lg:w-56 shrink-0 min-w-0">
                  <span className="font-medium text-sm text-foreground truncate">{p.name}</span>
                  {p.configured
                    ? <Badge variant="success">{t('admin.imageGen.backend.ready')}</Badge>
                    : <Badge variant="secondary">{t('admin.imageGen.backend.unconfigured')}</Badge>}
                  {!p.enabled && <Badge variant="secondary">{t('admin.imageGen.preset.disabled')}</Badge>}
                </div>
                <div className="flex-1 min-w-0 text-xs text-muted-foreground">
                  <span className="uppercase font-medium">{p.protocol}</span>
                  {' · '}{p.kinds.join(', ')}
                  {p.base_url ? <span className="block truncate">{p.base_url}</span> : null}
                </div>
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="ghost" leftIcon={<Pencil className="h-3.5 w-3.5" />} onClick={() => openEdit(p)}>
                    {t('common.edit')}
                  </Button>
                  <Button size="sm" variant="ghost" className="text-red-500" onClick={() => remove(p.name)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Modal isOpen={open} onClose={() => setOpen(false)} size="lg">
        <ModalHeader onClose={() => setOpen(false)}>
          {editingName ? t('admin.imageGen.provider.editTitle') : t('admin.imageGen.provider.newTitle')}
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label={t('admin.imageGen.provider.name')}>
              <Input value={form.name} disabled={!!editingName} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="my-provider" />
            </Field>
            <Field label={t('admin.imageGen.provider.protocol')}>
              <Select value={form.protocol} onChange={(e) => setForm({ ...form, protocol: e.target.value as 'openai' | 'http' })}>
                <option value="openai">{t('admin.imageGen.provider.protocolOpenai')}</option>
                <option value="http">{t('admin.imageGen.provider.protocolHttp')}</option>
              </Select>
            </Field>
          </div>
          <Field label={t('admin.imageGen.provider.kinds')}>
            <div className="flex flex-wrap gap-2">
              {KIND_TABS.map(({ kind: k }) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => toggleKind(k)}
                  className={`rounded-md border px-3 py-1 text-sm ${
                    form.kinds.includes(k)
                      ? 'border-primary bg-primary/10 text-foreground'
                      : 'border-border text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {t(`admin.imageGen.kind.${k}`)}
                </button>
              ))}
            </div>
          </Field>
          <Field label={t('admin.imageGen.provider.baseUrl')}>
            <Input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://api.example.com/v1" />
          </Field>
          <Field label={t('admin.imageGen.provider.apiKey')}>
            <Input
              type="password"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              placeholder={editingName ? t('admin.imageGen.backend.secretKeep') : t('admin.imageGen.backend.secretEnter')}
            />
          </Field>
          <Field label={t('admin.imageGen.provider.models')}>
            <Textarea rows={2} value={form.models} onChange={(e) => setForm({ ...form, models: e.target.value })} placeholder="model-a, model-b" />
          </Field>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <Switch checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} />
            {t('admin.imageGen.preset.enabled')}
          </label>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button onClick={save} disabled={createProvider.isPending || updateProvider.isPending}>
            {t('common.save')}
          </Button>
        </ModalFooter>
      </Modal>
    </section>
  );
}

function BackendCredentials() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data: creds } = useImageGenCredentials();
  const { data: backends } = useImageGenBackends();
  const setCreds = useSetCredentials();
  const [drafts, setDrafts] = useState<Record<string, { secret: string; endpoint: string }>>({});

  const availability = useMemo(() => {
    const map: Record<string, boolean> = {};
    for (const b of backends ?? []) map[b.name] = b.available;
    return map;
  }, [backends]);

  const save = async (name: string, type: 'api_key' | 'http') => {
    const draft = drafts[name] ?? { secret: '', endpoint: '' };
    const payload = type === 'api_key'
      ? { api_key: draft.secret, base_url: draft.endpoint || undefined }
      : { url: draft.endpoint || undefined, key: draft.secret || undefined };
    try {
      await setCreds.mutateAsync({ backend: name, data: payload });
      toast({ variant: 'success', title: t('admin.imageGen.backend.saved') });
      setDrafts((d) => ({ ...d, [name]: { secret: '', endpoint: draft.endpoint } }));
    } catch (e) {
      toast({ variant: 'error', title: t('admin.imageGen.backend.saveError'), description: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <section>
      <div className="mb-3">
        <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <KeyRound className="h-4 w-4" /> {t('admin.imageGen.backend.title')}
        </h4>
        <p className="text-xs text-muted-foreground">{t('admin.imageGen.backend.help')}</p>
      </div>
      <div className="space-y-2">
        {(creds ?? []).map((c) => {
          const draft = drafts[c.name] ?? { secret: '', endpoint: c.base_url || c.url || '' };
          const isHttp = c.credential_type === 'http';
          return (
            <Card key={c.name}>
              <CardContent className="p-3 flex flex-col lg:flex-row lg:items-center gap-3">
                <div className="flex items-center gap-2 lg:w-48 shrink-0">
                  <span className="font-medium text-sm text-foreground">{c.name}</span>
                  {availability[c.name]
                    ? <Badge variant="success">{t('admin.imageGen.backend.ready')}</Badge>
                    : <Badge variant="secondary">{t('admin.imageGen.backend.unconfigured')}</Badge>}
                </div>
                <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <Input
                    placeholder={isHttp ? t('admin.imageGen.backend.urlPlaceholder') : t('admin.imageGen.backend.baseUrlPlaceholder')}
                    value={draft.endpoint}
                    onChange={(e) => setDrafts((d) => ({ ...d, [c.name]: { ...draft, endpoint: e.target.value } }))}
                  />
                  <Input
                    type="password"
                    placeholder={c.configured ? t('admin.imageGen.backend.secretKeep') : t('admin.imageGen.backend.secretEnter')}
                    value={draft.secret}
                    onChange={(e) => setDrafts((d) => ({ ...d, [c.name]: { ...draft, secret: e.target.value } }))}
                  />
                </div>
                <Button size="sm" onClick={() => save(c.name, c.credential_type)} disabled={setCreds.isPending}>
                  {t('common.save')}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </section>
  );
}

function LocalDiffusion() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data } = useImageGenLocal();
  const setLocal = useSetLocalConfig();
  const [form, setForm] = useState<ImageGenLocalConfig | null>(null);

  useEffect(() => {
    if (data && form === null) {
      setForm({
        enabled: data.enabled,
        models_dir: data.models_dir,
        lora_dir: data.lora_dir,
        default_model: data.default_model,
      });
    }
  }, [data, form]);

  const save = async () => {
    if (!form) return;
    try {
      await setLocal.mutateAsync(form);
      toast({ variant: 'success', title: t('admin.imageGen.local.saved') });
    } catch (e) {
      toast({ variant: 'error', title: t('admin.imageGen.local.saveError'), description: e instanceof Error ? e.message : String(e) });
    }
  };

  const f = form ?? { enabled: true, models_dir: '', lora_dir: '', default_model: '' };

  return (
    <section>
      <div className="mb-3">
        <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Cpu className="h-4 w-4" /> {t('admin.imageGen.local.title')}
        </h4>
        <p className="text-xs text-muted-foreground">{t('admin.imageGen.local.help')}</p>
      </div>
      <Card>
        <CardContent className="p-4 space-y-4">
          <label className="flex items-center gap-2 text-sm text-foreground">
            <Switch checked={f.enabled} onCheckedChange={(v) => setForm({ ...f, enabled: v })} />
            {t('admin.imageGen.local.enabled')}
          </label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label={t('admin.imageGen.local.modelsDir')}>
              <Input value={f.models_dir} placeholder="~/.leagent/models/diffusion" onChange={(e) => setForm({ ...f, models_dir: e.target.value })} />
            </Field>
            <Field label={t('admin.imageGen.local.loraDir')}>
              <Input value={f.lora_dir} placeholder="~/.leagent/models/lora" onChange={(e) => setForm({ ...f, lora_dir: e.target.value })} />
            </Field>
            <Field label={t('admin.imageGen.local.defaultModel')}>
              <Input value={f.default_model} placeholder="stabilityai/stable-diffusion-xl-base-1.0" onChange={(e) => setForm({ ...f, default_model: e.target.value })} />
            </Field>
          </div>
          {data?.discovered_models?.length ? (
            <div className="text-xs text-muted-foreground">
              <span className="flex items-center gap-1 mb-1"><Server className="h-3.5 w-3.5" /> {t('admin.imageGen.local.discovered')}</span>
              <div className="flex flex-wrap gap-1.5">
                {data.discovered_models.map((m) => <Badge key={m} variant="secondary">{m}</Badge>)}
              </div>
            </div>
          ) : null}
          <div className="flex justify-end">
            <Button onClick={save} disabled={setLocal.isPending}>{t('common.save')}</Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
