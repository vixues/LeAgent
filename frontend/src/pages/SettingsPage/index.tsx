import { useState, useCallback, memo, useEffect, useMemo, useRef, type ChangeEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { changeAppLanguage } from '@/i18n';
import { PageShell } from '@/components/layout/PageShell';
import { useNavigate } from 'react-router-dom';
import {
  useCronJobs,
  useCronJob,
  useCreateCronJob,
  useUpdateCronJob,
  useDeleteCronJob,
  usePauseCronJob,
  useResumeCronJob,
  useTriggerCronJob,
  type CronJobInfo,
} from '@/controllers/API/queries/cron';
import { useGetFlows } from '@/controllers/API/queries/flows';
import {
  Wrench,
  Clock,
  Cpu,
  Package,
  Globe,
  FolderOpen,
  Bot,
  Zap,
  Database,
  Bell,
  Code,
  Plus,
  Trash2,
  Edit2,
  Play,
  Pause,
  Settings2,
  CheckCircle2,
  XCircle,
  Circle,
  AlertCircle,
  Sun,
  Moon,
  Monitor,
  Key,
  Sparkles,
  Flame,
  Star,
  RefreshCw,
  Terminal,
  KeyRound,
  Mail,
  Info,
  Search,
  ArrowUpCircle,
  GitBranch,
} from 'lucide-react';
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Button,
  Input,
  Select,
  Switch,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Badge,
} from '@/components/ui';
import { useThemeStore } from '@/stores/theme';
import { useTheme } from '@/hooks/useTheme';
import { getLogoBackdropStyle } from '@/lib/brandingBackdrop';
import {
  useBrandingStore,
  LOGO_BACKDROP_PRESETS,
  BRAND_FONT_PRESETS,
  type LogoBackdropPreset,
  type BrandFontPreset,
} from '@/stores/branding';
import { fileToBrandingIconDataUrl } from '@/lib/brandingIcon';
import { AppLogo } from '@/components/brand/AppLogo';
import {
  useProviders,
  useUpdateProvider,
  useTestProvider,
  useDefaultModel,
  useSetDefaultModel,
} from '@/hooks/useAdmin';
import { adminApi } from '@/api/admin';
import type { DeepSeekBalanceResponse } from '@/types/admin';
import { cn } from '@/lib/utils';
import { PageLoader } from '@/components/common/PageLoader';
import { SectionHeader } from '@/components/common/SectionHeader';
import { apiClient, HttpError } from '@/api/client';
import { useToast } from '@/components/ui/Toaster';

/* ── Types ── */

type SettingsTab =
  | 'general'
  | 'tools'
  | 'schedule'
  | 'models'
  | 'plugins'
  | 'tokens'
  | 'mail'
  | 'pythonPackages'
  | 'about';

interface ExtensionPackRow {
  id: string;
  name: string;
  description: string;
  installed: boolean;
}

interface PythonPackageRow {
  name: string;
  version: string;
  is_direct?: boolean;
  latest_version?: string;
}

interface PythonEnvInfoResponse {
  python_executable: string;
  backend_root: string;
  uses_uv: boolean;
  project_mode: boolean;
  has_lockfile: boolean;
}

type PythonFilterMode = 'all' | 'direct' | 'outdated';

/** GET /settings/mail */
interface MailStatusApiResponse {
  host: string;
  port: number;
  from_email: string;
  from_name: string;
  use_tls: boolean;
  use_ssl: boolean;
  username_set: boolean;
  password_set: boolean;
}

type MailEncryptionMode = 'starttls' | 'ssl' | 'none';

function mailEncryptionFromFlags(use_tls: boolean, use_ssl: boolean): MailEncryptionMode {
  if (use_ssl) return 'ssl';
  if (use_tls) return 'starttls';
  return 'none';
}

/** Backend GET /settings/tokens entry */
interface TokenStatusApiEntry {
  env_key: string;
  set: boolean;
}

const TOKEN_ENV_ROWS: { key: string; labelKey: string }[] = [
  { key: 'LEAGENT_GITHUB_TOKEN', labelKey: 'settings.tokensGithubWa' },
  { key: 'GITHUB_TOKEN', labelKey: 'settings.tokensGithub' },
  { key: 'OPENAI_API_KEY', labelKey: 'settings.tokensOpenai' },
  { key: 'ANTHROPIC_API_KEY', labelKey: 'settings.tokensAnthropic' },
  { key: 'DEEPSEEK_API_KEY', labelKey: 'settings.tokensDeepseek' },
  { key: 'DEEPSEEK_BASE_URL', labelKey: 'settings.tokensDeepseekBaseUrl' },
  { key: 'DEEPSEEK_MODEL', labelKey: 'settings.tokensDeepseekModel' },
  { key: 'DEEPSEEK_THINKING_TYPE', labelKey: 'settings.tokensDeepseekThinkingType' },
  { key: 'DEEPSEEK_REASONING_EFFORT', labelKey: 'settings.tokensDeepseekReasoningEffort' },
  { key: 'DASHSCOPE_API_KEY', labelKey: 'settings.tokensDashscope' },
  { key: 'WEB_SEARCH_PROVIDER', labelKey: 'settings.tokensWebSearchProvider' },
  { key: 'WEB_SEARCH_BING_API_KEY', labelKey: 'settings.tokensWebSearchBing' },
  { key: 'WEB_SEARCH_SEARXNG_BASE_URL', labelKey: 'settings.tokensWebSearchSearxng' },
  { key: 'IMAGE_SEARCH_API_KEY', labelKey: 'settings.tokensImageSearchApiKey' },
  { key: 'IMAGE_SEARCH_CX', labelKey: 'settings.tokensImageSearchCx' },
  { key: 'WEB_FETCH_ENABLED', labelKey: 'settings.tokensWebFetchEnabled' },
  { key: 'WEB_FETCH_CHECK_ROBOTS', labelKey: 'settings.tokensWebFetchRobots' },
  { key: 'WEB_FETCH_MIN_INTERVAL_MS', labelKey: 'settings.tokensWebFetchInterval' },
  { key: 'WEB_FETCH_USER_AGENT', labelKey: 'settings.tokensWebFetchUa' },
];

interface Tool {
  id: string;
  nameKey: string;
  descriptionKey: string;
  category: string;
  enabled: boolean;
}

/* ── Constants (hoisted to module scope per rerender-memo-with-default-value) ── */

const CATEGORY_ICONS: Record<string, typeof Globe> = {
  web: Globe,
  file: FolderOpen,
  llm: Bot,
  api: Zap,
  data: Database,
  notification: Bell,
  custom: Code,
};

const MOCK_TOOLS: Tool[] = [
  { id: '1', nameKey: 'settings.mockTools.webSearch.name', descriptionKey: 'settings.mockTools.webSearch.description', category: 'web', enabled: true },
  { id: '2', nameKey: 'settings.mockTools.fileRead.name', descriptionKey: 'settings.mockTools.fileRead.description', category: 'file', enabled: true },
  { id: '3', nameKey: 'settings.mockTools.gpt4.name', descriptionKey: 'settings.mockTools.gpt4.description', category: 'llm', enabled: true },
  { id: '4', nameKey: 'settings.mockTools.claude.name', descriptionKey: 'settings.mockTools.claude.description', category: 'llm', enabled: false },
  { id: '5', nameKey: 'settings.mockTools.apiCall.name', descriptionKey: 'settings.mockTools.apiCall.description', category: 'api', enabled: true },
  { id: '6', nameKey: 'settings.mockTools.dbQuery.name', descriptionKey: 'settings.mockTools.dbQuery.description', category: 'data', enabled: false },
];

const DEFAULT_BRAND = { bg: 'bg-gray-100 dark:bg-surface', text: 'text-gray-700 dark:text-gray-300', letter: '?' } as const;

const PROVIDER_BRAND: Record<string, { bg: string; text: string; letter: string }> = {
  openai: { bg: 'bg-mint-100 dark:bg-mint-900/30', text: 'text-mint-700 dark:text-mint-400', letter: 'O' },
  anthropic: { bg: 'bg-peach-100 dark:bg-peach-900/30', text: 'text-peach-700 dark:text-peach-400', letter: 'A' },
  qwen: { bg: 'bg-sky-100 dark:bg-sky-900/30', text: 'text-sky-800 dark:text-sky-400', letter: 'Q' },
  dashscope: { bg: 'bg-sky-100 dark:bg-sky-900/30', text: 'text-sky-800 dark:text-sky-400', letter: 'D' },
  deepseek: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400', letter: 'DS' },
  ollama: { bg: 'bg-gray-100 dark:bg-surface', text: 'text-gray-700 dark:text-gray-300', letter: 'L' },
  custom: { bg: 'bg-gray-100 dark:bg-surface', text: 'text-gray-700 dark:text-gray-300', letter: 'C' },
  azure: { bg: 'bg-sky-100 dark:bg-sky-900/30', text: 'text-sky-700 dark:text-sky-400', letter: 'Az' },
};

const THEME_OPTIONS = [
  { value: 'light' as const, label: 'settings.themeLight', icon: Sun },
  { value: 'dark' as const, label: 'settings.themeDark', icon: Moon },
  { value: 'system' as const, label: 'settings.themeSystem', icon: Monitor },
] as const;

type DeepSeekBalanceStatus =
  | { state: 'loading' }
  | { state: 'success'; data: DeepSeekBalanceResponse }
  | { state: 'error'; error: string };

function formatDeepSeekBalance(data: DeepSeekBalanceResponse): string {
  const balances = data.balance_infos
    .map((item) => {
      const total = item.total_balance || item.topped_up_balance || item.granted_balance;
      return total ? `${total} ${item.currency}`.trim() : '';
    })
    .filter(Boolean);

  return balances.length > 0 ? balances.join(' · ') : '—';
}

const BRANDING_BACKDROP_META: Record<
  LogoBackdropPreset,
  { labelKey: string; icon: typeof Sun }
> = {
  auto: { labelKey: 'settings.brandingBackdropAuto', icon: Clock },
  aurora: { labelKey: 'settings.brandingBackdropAurora', icon: Sparkles },
  circuit: { labelKey: 'settings.brandingBackdropCircuit', icon: Cpu },
  ember: { labelKey: 'settings.brandingBackdropEmber', icon: Flame },
  void: { labelKey: 'settings.brandingBackdropVoid', icon: Star },
};

const BRAND_FONT_META: Record<
  BrandFontPreset,
  { labelKey: string; sample: string; className: string }
> = {
  modern: {
    labelKey: 'settings.brandFontModern',
    sample: 'LeAgent',
    className: 'font-sans tracking-[-0.035em]',
  },
  rounded: {
    labelKey: 'settings.brandFontRounded',
    sample: 'LeAgent',
    className: 'font-sans tracking-[-0.025em]',
  },
  handwritten: {
    labelKey: 'settings.brandFontHandwritten',
    sample: 'LeAgent',
    className: 'tracking-[-0.015em] [font-family:"Comic_Sans_MS","Bradley_Hand","Segoe_Print",cursive]',
  },
  mono: {
    labelKey: 'settings.brandFontMono',
    sample: 'LeAgent',
    className: 'font-mono tracking-[-0.04em]',
  },
};

/* ── Sub-components (extracted per rerender-memo to isolate re-renders) ── */

const SettingRow = memo(function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <p className="font-medium text-gray-900 dark:text-white">{label}</p>
        <p className="text-sm text-gray-500 dark:text-gray-400">{description}</p>
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
});

/* ── About tab (extracted to keep SettingsPage body manageable) ── */

function AboutTabContent() {
  const { t } = useTranslation();
  const { resolvedTheme } = useTheme();
  const customIcon = useBrandingStore((s) => s.customIconDataUrl);
  const preset = useBrandingStore((s) => s.logoBackdropPreset);
  const hour = new Date().getHours();
  const backdropStyle = useMemo(
    () => getLogoBackdropStyle(hour, preset, resolvedTheme),
    [hour, preset, resolvedTheme],
  );

  const rows: { label: string; value: ReactNode }[] = [
    { label: t('about.companyLabel'), value: 'Vixues Technology' },
    { label: t('about.authorLabel'), value: 'Cheng Yuanqi' },
    {
      label: t('about.supportPrefix'),
      value: (
        <a
          href="mailto:vixues@gmail.com"
          className="text-primary-600 dark:text-primary-400 hover:underline"
        >
          vixues@gmail.com
        </a>
      ),
    },
    { label: t('about.version'), value: '1.0.0' },
    { label: t('about.licenseLabel'), value: t('about.license') },
    {
      label: t('about.websiteLabel'),
      value: (
        <a
          href="https://vixues.com.cn"
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary-600 dark:text-primary-400 hover:underline"
        >
          vixues.com.cn
        </a>
      ),
    },
    {
      label: t('about.githubLabel'),
      value: (
        <a
          href="https://github.com/vixues/LeAgent"
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary-600 dark:text-primary-400 hover:underline"
        >
          github.com/vixues/LeAgent
        </a>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-6">
          {/* Logo banner — mirrors sidebar LogoStage backdrop */}
          <div className="relative overflow-hidden rounded-xl ring-1 ring-black/5 dark:ring-white/10">
            <div className="absolute inset-0" style={backdropStyle} aria-hidden />
            <div
              className={cn(
                'pointer-events-none absolute inset-0 mix-blend-soft-light',
                resolvedTheme === 'dark' ? 'opacity-[0.055]' : 'opacity-[0.035]',
              )}
              style={{
                backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
              }}
              aria-hidden
            />
            <div className="relative z-[1] flex items-center gap-4 px-5 py-5">
              <AppLogo
                src={customIcon}
                className={cn(
                  'size-14 shrink-0 rounded-xl',
                  resolvedTheme === 'dark'
                    ? 'drop-shadow-[0_1px_3px_rgba(0,0,0,0.4)]'
                    : 'drop-shadow-[0_1px_3px_rgba(15,23,42,0.3)]',
                )}
              />
              <div className="min-w-0">
                <h2
                  className={cn(
                    'text-2xl font-extrabold text-white leading-tight',
                    resolvedTheme === 'dark'
                      ? 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.35)]'
                      : 'drop-shadow-[0_1px_2px_rgba(15,23,42,0.22)]',
                  )}
                >
                  {t('about.brandName')}
                </h2>
                <p
                  className={cn(
                    'text-sm text-white/80 mt-0.5',
                    resolvedTheme === 'dark'
                      ? 'drop-shadow-[0_1px_1px_rgba(0,0,0,0.3)]'
                      : 'drop-shadow-[0_1px_1px_rgba(15,23,42,0.15)]',
                  )}
                >
                  {t('about.description')}
                </p>
              </div>
            </div>
          </div>

          {/* Info rows — no divider lines */}
          <div className="rounded-lg overflow-hidden">
            {rows.map((row, i) => (
              <div
                key={row.label}
                className={cn(
                  'flex items-center justify-between px-4 py-2.5',
                  i % 2 === 0 && 'bg-surface-sunken/40',
                )}
              >
                <span className="text-sm text-muted-foreground">{row.label}</span>
                <span className="text-sm font-medium text-foreground">{row.value}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="px-1 space-y-1">
        <p className="text-xs text-muted-foreground">
          {t('about.copyright')}
        </p>
        <p className="text-xs text-muted-foreground">
          {t('about.thirdParty')}
        </p>
      </div>
    </div>
  );
}

/* ── Main Component ── */

export default function SettingsPage() {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const { theme, setTheme } = useThemeStore();
  const displayName = useBrandingStore((s) => s.displayName);
  const setDisplayName = useBrandingStore((s) => s.setDisplayName);
  const customIconDataUrl = useBrandingStore((s) => s.customIconDataUrl);
  const setCustomIconDataUrl = useBrandingStore((s) => s.setCustomIconDataUrl);
  const logoBackdropPreset = useBrandingStore((s) => s.logoBackdropPreset);
  const setLogoBackdropPreset = useBrandingStore((s) => s.setLogoBackdropPreset);
  const brandFontPreset = useBrandingStore((s) => s.brandFontPreset);
  const setBrandFontPreset = useBrandingStore((s) => s.setBrandFontPreset);
  const resetBranding = useBrandingStore((s) => s.resetBranding);
  const brandingIconInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const onBrandingIconFile = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = '';
      if (!file) return;
      try {
        const url = await fileToBrandingIconDataUrl(file);
        setCustomIconDataUrl(url);
        toast({ variant: 'success', title: t('settings.brandingIcon') });
      } catch (err) {
        const msg =
          err instanceof Error && err.message === 'ICON_TOO_LARGE'
            ? t('settings.brandingIconTooLarge')
            : t('settings.brandingIconReadError');
        toast({ variant: 'error', title: msg });
      }
    },
    [setCustomIconDataUrl, t, toast]
  );

  const { data: providers, isLoading: providersLoading } = useProviders();
  const { data: defaultModelConfig } = useDefaultModel();
  const setDefaultModelMutation = useSetDefaultModel();
  const updateProviderMutation = useUpdateProvider();
  const testProviderMutation = useTestProvider();

  const [editingProviderKey, setEditingProviderKey] = useState<string | null>(null);
  const [providerKeyDraft, setProviderKeyDraft] = useState('');
  const [providerTestStatus, setProviderTestStatus] = useState<Record<string, 'idle' | 'testing' | 'success' | 'error'>>({});
  const [deepSeekBalances, setDeepSeekBalances] = useState<Record<string, DeepSeekBalanceStatus>>({});

  const [activeTab, setActiveTab] = useState<SettingsTab>('general');

  const [tools, setTools] = useState<Tool[]>(MOCK_TOOLS);

  const [isScheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<CronJobInfo | null>(null);
  const [taskFormName, setTaskFormName] = useState('');
  const [taskFormFlowId, setTaskFormFlowId] = useState('');
  const [taskFormCron, setTaskFormCron] = useState('');
  const [taskBusyId, setTaskBusyId] = useState<string | null>(null);

  const {
    data: cronJobsData,
    isLoading: cronJobsLoading,
    isError: cronJobsError,
  } = useCronJobs({ job_type: 'flow' });
  const scheduledTasks = useMemo(() => cronJobsData?.jobs ?? [], [cronJobsData]);

  const { data: flowsListData } = useGetFlows(
    { pageSize: 100 },
    { enabled: activeTab === 'schedule' || isScheduleModalOpen },
  );
  const availableFlows = flowsListData?.data ?? [];

  const createCronJob = useCreateCronJob();
  const updateCronJob = useUpdateCronJob();
  const deleteCronJob = useDeleteCronJob();
  const pauseCronJob = usePauseCronJob();
  const resumeCronJob = useResumeCronJob();
  const triggerCronJob = useTriggerCronJob();

  const { data: editingTaskDetail } = useCronJob(editingTask?.id ?? '', {
    enabled: !!editingTask?.id && isScheduleModalOpen,
  });

  useEffect(() => {
    if (editingTaskDetail && editingTask?.id === editingTaskDetail.id) {
      const flowId = editingTaskDetail.target_id ?? '';
      setTaskFormFlowId((prev) => (prev ? prev : flowId));
    }
  }, [editingTaskDetail, editingTask?.id]);

  const [extensionPacks, setExtensionPacks] = useState<ExtensionPackRow[]>([]);
  const [extensionsLoading, setExtensionsLoading] = useState(false);
  const [extensionBusyId, setExtensionBusyId] = useState<string | null>(null);

  const [pythonEnvInfo, setPythonEnvInfo] = useState<PythonEnvInfoResponse | null>(null);
  const [pythonPackages, setPythonPackages] = useState<PythonPackageRow[]>([]);
  const [pythonPackagesLoading, setPythonPackagesLoading] = useState(false);
  const [pythonInstallSpec, setPythonInstallSpec] = useState('');
  const [pythonEnvBusyId, setPythonEnvBusyId] = useState<string | null>(null);
  const [pythonSearch, setPythonSearch] = useState('');
  const [pythonFilter, setPythonFilter] = useState<PythonFilterMode>('all');
  const [pythonOutdated, setPythonOutdated] = useState<Record<string, string>>({});
  const [pythonOutdatedLoading, setPythonOutdatedLoading] = useState(false);
  const [pythonLogText, setPythonLogText] = useState<string | null>(null);
  const [pythonTreeText, setPythonTreeText] = useState<string | null>(null);
  const [pythonConfirmUninstall, setPythonConfirmUninstall] = useState<string | null>(null);

  const [tokenStatus, setTokenStatus] = useState<Record<string, boolean>>({});
  const [tokenDrafts, setTokenDrafts] = useState<Record<string, string>>({});
  const [tokensLoading, setTokensLoading] = useState(false);
  const [tokensSaving, setTokensSaving] = useState(false);

  const [mailSnapshot, setMailSnapshot] = useState<MailStatusApiResponse | null>(null);
  const [mailLoading, setMailLoading] = useState(false);
  const [mailSaving, setMailSaving] = useState(false);
  const [mailTestBusy, setMailTestBusy] = useState(false);
  const [mailHost, setMailHost] = useState('');
  const [mailPort, setMailPort] = useState('587');
  const [mailEncryption, setMailEncryption] = useState<MailEncryptionMode>('starttls');
  const [mailUsername, setMailUsername] = useState('');
  const [mailPassword, setMailPassword] = useState('');
  const [mailFromEmail, setMailFromEmail] = useState('');
  const [mailFromName, setMailFromName] = useState('');
  const [mailTestTo, setMailTestTo] = useState('');

  // Derived state (per rerender-derived-state-no-effect)
  const enabledProviders = providers?.filter((p) => p.enabled) ?? [];
  const currentDefault = defaultModelConfig
    ? `${defaultModelConfig.provider}/${defaultModelConfig.model}`
    : '';

  useEffect(() => {
    const deepSeekProviders = (providers ?? []).filter(
      (provider) => provider.type === 'deepseek' && provider.enabled && provider.api_key_set
    );
    if (deepSeekProviders.length === 0) {
      setDeepSeekBalances({});
      return;
    }

    let cancelled = false;
    setDeepSeekBalances((prev) => {
      const next: Record<string, DeepSeekBalanceStatus> = {};
      for (const provider of deepSeekProviders) {
        next[provider.name] = prev[provider.name] ?? { state: 'loading' };
      }
      return next;
    });

    void Promise.all(
      deepSeekProviders.map(async (provider) => {
        try {
          const data = await adminApi.providers.balance(provider.name);
          if (!cancelled) {
            setDeepSeekBalances((prev) => ({
              ...prev,
              [provider.name]: { state: 'success', data },
            }));
          }
        } catch (error) {
          if (!cancelled) {
            setDeepSeekBalances((prev) => ({
              ...prev,
              [provider.name]: {
                state: 'error',
                error: error instanceof Error ? error.message : String(error),
              },
            }));
          }
        }
      })
    );

    return () => {
      cancelled = true;
    };
  }, [providers]);

  const handleDefaultModelChange = useCallback(
    (value: string) => {
      const [providerName = '', ...modelParts] = value.split('/');
      const model = modelParts.join('/');
      if (providerName && model) {
        setDefaultModelMutation.mutate({ provider: providerName, model });
      }
    },
    [setDefaultModelMutation]
  );

  const handleSaveProviderApiKey = useCallback(
    async (providerName: string) => {
      if (!providerKeyDraft.trim()) return;
      try {
        await updateProviderMutation.mutateAsync({
          name: providerName,
          data: { api_key: providerKeyDraft },
        });
        toast({ variant: 'success', title: t('settings.apiKeySaved') });
        setEditingProviderKey(null);
        setProviderKeyDraft('');
      } catch (e) {
        toast({ variant: 'error', title: e instanceof Error ? e.message : 'Error' });
      }
    },
    [providerKeyDraft, updateProviderMutation, t, toast]
  );

  const handleTestProvider = useCallback(
    async (providerName: string) => {
      setProviderTestStatus((prev) => ({ ...prev, [providerName]: 'testing' }));
      try {
        const result = await testProviderMutation.mutateAsync(providerName);
        setProviderTestStatus((prev) => ({
          ...prev,
          [providerName]: result?.is_healthy ? 'success' : 'error',
        }));
        setTimeout(() => {
          setProviderTestStatus((prev) => ({ ...prev, [providerName]: 'idle' }));
        }, 3000);
      } catch {
        setProviderTestStatus((prev) => ({ ...prev, [providerName]: 'error' }));
        setTimeout(() => {
          setProviderTestStatus((prev) => ({ ...prev, [providerName]: 'idle' }));
        }, 3000);
      }
    },
    [testProviderMutation]
  );

  const handleLanguageChange = useCallback(async (lang: string) => {
    await changeAppLanguage(lang);
  }, []);

  // Functional setState (per rerender-functional-setstate)
  const handleToggleTool = useCallback((toolId: string) => {
    setTools((prev) =>
      prev.map((tool) =>
        tool.id === toolId ? { ...tool, enabled: !tool.enabled } : tool
      )
    );
  }, []);

  const handleToggleTask = useCallback(
    async (task: CronJobInfo) => {
      setTaskBusyId(task.id);
      try {
        if (task.status === 'active' || task.status === 'running') {
          await pauseCronJob.mutateAsync(task.id);
          toast({ variant: 'success', title: t('settings.scheduleTaskPaused', { name: task.name }) });
        } else {
          await resumeCronJob.mutateAsync(task.id);
          toast({ variant: 'success', title: t('settings.scheduleTaskResumed', { name: task.name }) });
        }
      } catch (e) {
        toast({ variant: 'error', title: e instanceof Error ? e.message : 'Error' });
      } finally {
        setTaskBusyId(null);
      }
    },
    [pauseCronJob, resumeCronJob, t, toast]
  );

  const handleDeleteTask = useCallback(
    async (task: CronJobInfo) => {
      if (!window.confirm(t('settings.confirmDeleteScheduleTask'))) return;
      setTaskBusyId(task.id);
      try {
        await deleteCronJob.mutateAsync(task.id);
        toast({ variant: 'success', title: t('settings.scheduleTaskDeleted', { name: task.name }) });
      } catch (e) {
        toast({ variant: 'error', title: e instanceof Error ? e.message : 'Error' });
      } finally {
        setTaskBusyId(null);
      }
    },
    [deleteCronJob, t, toast]
  );

  const handleRunTask = useCallback(
    async (task: CronJobInfo) => {
      setTaskBusyId(task.id);
      try {
        await triggerCronJob.mutateAsync(task.id);
        toast({ variant: 'success', title: t('settings.scheduleTaskTriggered', { name: task.name }) });
      } catch (e) {
        toast({ variant: 'error', title: e instanceof Error ? e.message : 'Error' });
      } finally {
        setTaskBusyId(null);
      }
    },
    [triggerCronJob, t, toast]
  );

  const handleOpenAddSchedule = useCallback(() => {
    setEditingTask(null);
    setTaskFormName('');
    setTaskFormFlowId('');
    setTaskFormCron('0 9 * * *');
    setScheduleModalOpen(true);
  }, []);

  const handleOpenEditSchedule = useCallback((task: CronJobInfo) => {
    setEditingTask(task);
    setTaskFormName(task.name);
    setTaskFormFlowId(''); // populated by GET /cron/{id} via useCronJob if needed; safe default
    setTaskFormCron(task.cron_expression);
    setScheduleModalOpen(true);
  }, []);

  const handleCloseScheduleModal = useCallback(() => {
    setScheduleModalOpen(false);
    setEditingTask(null);
    setTaskFormName('');
    setTaskFormFlowId('');
    setTaskFormCron('');
  }, []);

  const handleSaveScheduleTask = useCallback(async () => {
    const name = taskFormName.trim();
    const flowId = taskFormFlowId.trim();
    const cron = taskFormCron.trim();
    if (!name) {
      toast({ variant: 'error', title: t('settings.scheduleErrorNameRequired') });
      return;
    }
    if (!flowId) {
      toast({ variant: 'error', title: t('settings.scheduleErrorFlowRequired') });
      return;
    }
    if (!cron || cron.split(/\s+/).length < 5) {
      toast({ variant: 'error', title: t('settings.scheduleErrorCronInvalid') });
      return;
    }
    try {
      if (editingTask) {
        await updateCronJob.mutateAsync({
          id: editingTask.id,
          name,
          cron_expression: cron,
          target_id: flowId,
          enabled: true,
        });
        toast({ variant: 'success', title: t('settings.scheduleTaskSaved', { name }) });
      } else {
        await createCronJob.mutateAsync({
          name,
          job_type: 'flow',
          cron_expression: cron,
          target_id: flowId,
          enabled: true,
        });
        toast({ variant: 'success', title: t('settings.scheduleTaskCreated', { name }) });
      }
      handleCloseScheduleModal();
    } catch (e) {
      toast({ variant: 'error', title: e instanceof Error ? e.message : 'Error' });
    }
  }, [
    taskFormName,
    taskFormFlowId,
    taskFormCron,
    editingTask,
    createCronJob,
    updateCronJob,
    handleCloseScheduleModal,
    t,
    toast,
  ]);

  useEffect(() => {
    if (activeTab !== 'plugins') return;
    let cancelled = false;
    setExtensionsLoading(true);
    void apiClient
      .get<{ packs: ExtensionPackRow[] }>('/extensions')
      .then((r) => {
        if (!cancelled) setExtensionPacks(r.packs);
      })
      .catch(() => {
        if (!cancelled) setExtensionPacks([]);
      })
      .finally(() => {
        if (!cancelled) setExtensionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab]);

  const handleInstallPack = useCallback(
    async (id: string) => {
      setExtensionBusyId(id);
      try {
        const res = await apiClient.post<{
          ok?: boolean;
          playwright_install_ok?: boolean;
          pack_id?: string;
        }>('/extensions/install', { pack_id: id });
        const r = await apiClient.get<{ packs: ExtensionPackRow[] }>('/extensions');
        setExtensionPacks(r.packs);
        if (id === 'browser' && res.playwright_install_ok === false) {
          toast({
            variant: 'warning',
            title: t('settings.pluginsInstallSuccess'),
            description: t('settings.pluginsPlaywrightInstallWarn'),
          });
        } else {
          toast({ variant: 'success', title: t('settings.pluginsInstallSuccess') });
        }
      } catch (e) {
        toast({
          variant: 'error',
          title: e instanceof Error ? e.message : 'Error',
        });
      } finally {
        setExtensionBusyId(null);
      }
    },
    [t, toast]
  );

  const handleUninstallPack = useCallback(
    async (id: string) => {
      setExtensionBusyId(id);
      try {
        await apiClient.delete(`/extensions/${id}`);
        const r = await apiClient.get<{ packs: ExtensionPackRow[] }>('/extensions');
        setExtensionPacks(r.packs);
        toast({ variant: 'success', title: t('settings.pluginsUninstall') });
      } catch (e) {
        toast({
          variant: 'error',
          title: e instanceof Error ? e.message : 'Error',
        });
      } finally {
        setExtensionBusyId(null);
      }
    },
    [t, toast]
  );

  const loadPythonEnvironment = useCallback(async () => {
    setPythonPackagesLoading(true);
    try {
      const [infoRes, pkgRes] = await Promise.all([
        apiClient.get<PythonEnvInfoResponse>('/python-env/info'),
        apiClient.get<{ packages: PythonPackageRow[] }>('/python-env/packages'),
      ]);
      setPythonEnvInfo(infoRes);
      setPythonPackages(pkgRes.packages);
    } catch (e) {
      setPythonEnvInfo(null);
      setPythonPackages([]);
      toast({
        variant: 'error',
        title: e instanceof Error ? e.message : t('settings.pythonPackagesEmpty'),
      });
    } finally {
      setPythonPackagesLoading(false);
    }
  }, [t, toast]);

  useEffect(() => {
    if (activeTab !== 'pythonPackages') return;
    void loadPythonEnvironment();
  }, [activeTab, loadPythonEnvironment]);

  const handlePythonInstall = useCallback(async () => {
    const spec = pythonInstallSpec.trim();
    if (!spec) return;
    setPythonEnvBusyId('install');
    try {
      const res = await apiClient.post<{ ok: boolean; log: string }>('/python-env/install', { spec });
      toast({ variant: 'success', title: t('settings.pythonPackagesInstall') });
      setPythonInstallSpec('');
      if (res.log) setPythonLogText(res.log);
      await loadPythonEnvironment();
    } catch (e) {
      toast({
        variant: 'error',
        title: e instanceof Error ? e.message : 'Error',
      });
    } finally {
      setPythonEnvBusyId(null);
    }
  }, [pythonInstallSpec, loadPythonEnvironment, t, toast]);

  const handlePythonUninstall = useCallback(
    async (pkgName: string) => {
      setPythonEnvBusyId(pkgName);
      setPythonConfirmUninstall(null);
      try {
        const res = await apiClient.post<{ ok: boolean; log: string }>('/python-env/uninstall', { package: pkgName });
        toast({ variant: 'success', title: t('settings.pythonPackagesUninstall') });
        if (res.log) setPythonLogText(res.log);
        await loadPythonEnvironment();
      } catch (e) {
        toast({
          variant: 'error',
          title: e instanceof Error ? e.message : 'Error',
        });
      } finally {
        setPythonEnvBusyId(null);
      }
    },
    [loadPythonEnvironment, t, toast]
  );

  const handlePythonUpgrade = useCallback(
    async (pkgName: string) => {
      setPythonEnvBusyId(`upgrade:${pkgName}`);
      try {
        const res = await apiClient.post<{ ok: boolean; log: string }>('/python-env/upgrade', { package: pkgName });
        toast({ variant: 'success', title: t('settings.pythonPackagesUpgradeSuccess') });
        if (res.log) setPythonLogText(res.log);
        setPythonOutdated((prev) => {
          const next = { ...prev };
          delete next[pkgName];
          return next;
        });
        await loadPythonEnvironment();
      } catch (e) {
        toast({ variant: 'error', title: e instanceof Error ? e.message : 'Error' });
      } finally {
        setPythonEnvBusyId(null);
      }
    },
    [loadPythonEnvironment, t, toast]
  );

  const handleCheckOutdated = useCallback(async () => {
    setPythonOutdatedLoading(true);
    try {
      const res = await apiClient.get<{ packages: Array<{ name: string; latest_version: string }> }>('/python-env/outdated');
      const map: Record<string, string> = {};
      for (const pkg of res.packages) {
        map[pkg.name] = pkg.latest_version;
      }
      setPythonOutdated(map);
      if (res.packages.length === 0) {
        toast({ variant: 'success', title: t('settings.pythonPackagesNoOutdated') });
      }
    } catch (e) {
      toast({ variant: 'error', title: e instanceof Error ? e.message : 'Error' });
    } finally {
      setPythonOutdatedLoading(false);
    }
  }, [t, toast]);

  const handlePythonSync = useCallback(async () => {
    setPythonEnvBusyId('sync');
    try {
      const res = await apiClient.post<{ ok: boolean; log: string }>('/python-env/sync');
      toast({ variant: 'success', title: t('settings.pythonPackagesSyncSuccess') });
      if (res.log) setPythonLogText(res.log);
      await loadPythonEnvironment();
    } catch (e) {
      toast({ variant: 'error', title: e instanceof Error ? e.message : 'Error' });
    } finally {
      setPythonEnvBusyId(null);
    }
  }, [loadPythonEnvironment, t, toast]);

  const handlePythonTree = useCallback(async () => {
    setPythonEnvBusyId('tree');
    try {
      const res = await apiClient.get<{ tree: string }>('/python-env/tree');
      setPythonTreeText(res.tree);
    } catch (e) {
      toast({ variant: 'error', title: e instanceof Error ? e.message : 'Error' });
    } finally {
      setPythonEnvBusyId(null);
    }
  }, [toast]);

  const filteredPythonPackages = useMemo(() => {
    let list = pythonPackages;
    if (pythonFilter === 'direct') {
      list = list.filter((p) => p.is_direct);
    } else if (pythonFilter === 'outdated') {
      list = list.filter((p) => p.name in pythonOutdated);
    }
    const q = pythonSearch.trim().toLowerCase();
    if (q) {
      list = list.filter((p) => p.name.toLowerCase().includes(q));
    }
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
  }, [pythonPackages, pythonSearch, pythonFilter, pythonOutdated]);

  const loadTokenStatus = useCallback(async () => {
    setTokensLoading(true);
    try {
      const res = await apiClient.get<{ keys: TokenStatusApiEntry[] }>('/settings/tokens');
      const next: Record<string, boolean> = {};
      for (const row of res.keys) {
        next[row.env_key] = row.set;
      }
      setTokenStatus(next);
    } catch (e) {
      toast({
        variant: 'error',
        title: e instanceof Error ? e.message : 'Error',
      });
    } finally {
      setTokensLoading(false);
    }
  }, [toast]);

  const handleSaveEnvTokens = useCallback(async () => {
    const values: Record<string, string> = {};
    for (const { key } of TOKEN_ENV_ROWS) {
      const v = (tokenDrafts[key] ?? '').trim();
      if (v) {
        values[key] = v;
      }
    }
    if (Object.keys(values).length === 0) {
      return;
    }
    setTokensSaving(true);
    try {
      await apiClient.put('/settings/tokens', { values });
      toast({ variant: 'success', title: t('settings.tokensSaved') });
      setTokenDrafts({});
      await loadTokenStatus();
    } catch (e) {
      toast({
        variant: 'error',
        title: e instanceof Error ? e.message : 'Error',
      });
    } finally {
      setTokensSaving(false);
    }
  }, [loadTokenStatus, t, toast, tokenDrafts]);

  const handleClearEnvToken = useCallback(
    async (envKey: string) => {
      setTokensSaving(true);
      try {
        await apiClient.put('/settings/tokens', { values: { [envKey]: '' } });
        toast({ variant: 'success', title: t('settings.tokensSaved') });
        setTokenDrafts((d) => ({ ...d, [envKey]: '' }));
        await loadTokenStatus();
      } catch (e) {
        toast({
          variant: 'error',
          title: e instanceof Error ? e.message : 'Error',
        });
      } finally {
        setTokensSaving(false);
      }
    },
    [loadTokenStatus, t, toast]
  );

  useEffect(() => {
    if (activeTab === 'tokens') {
      void loadTokenStatus();
    }
  }, [activeTab, loadTokenStatus]);

  const loadMailSettings = useCallback(async () => {
    setMailLoading(true);
    try {
      const res = await apiClient.get<MailStatusApiResponse>('/settings/mail');
      setMailSnapshot(res);
      setMailHost(res.host);
      setMailPort(String(res.port || 587));
      setMailEncryption(mailEncryptionFromFlags(res.use_tls, res.use_ssl));
      setMailUsername('');
      setMailPassword('');
      setMailFromEmail(res.from_email);
      setMailFromName(res.from_name);
    } catch (e) {
      setMailSnapshot(null);
      toast({
        variant: 'error',
        title: e instanceof Error ? e.message : 'Error',
      });
    } finally {
      setMailLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (activeTab !== 'mail') return;
    void loadMailSettings();
  }, [activeTab, loadMailSettings]);

  const handleSaveMail = useCallback(async () => {
    const values: Record<string, string> = {
      LEAGENT_SMTP_HOST: mailHost.trim(),
      LEAGENT_SMTP_PORT: String(parseInt(mailPort, 10) || 587),
      LEAGENT_SMTP_FROM_EMAIL: mailFromEmail.trim(),
      LEAGENT_SMTP_FROM_NAME: mailFromName.trim(),
    };
    if (mailUsername.trim()) {
      values.LEAGENT_SMTP_USERNAME = mailUsername.trim();
    }
    if (mailEncryption === 'ssl') {
      values.LEAGENT_SMTP_USE_SSL = 'true';
      values.LEAGENT_SMTP_USE_TLS = 'false';
    } else if (mailEncryption === 'starttls') {
      values.LEAGENT_SMTP_USE_SSL = 'false';
      values.LEAGENT_SMTP_USE_TLS = 'true';
    } else {
      values.LEAGENT_SMTP_USE_SSL = 'false';
      values.LEAGENT_SMTP_USE_TLS = 'false';
    }
    if (mailPassword.trim()) {
      values.LEAGENT_SMTP_PASSWORD = mailPassword.trim();
    }
    setMailSaving(true);
    try {
      await apiClient.put('/settings/tokens', { values });
      toast({ variant: 'success', title: t('settings.mailSaved') });
      setMailPassword('');
      await loadMailSettings();
    } catch (e) {
      toast({
        variant: 'error',
        title: e instanceof Error ? e.message : 'Error',
      });
    } finally {
      setMailSaving(false);
    }
  }, [
    mailHost,
    mailPort,
    mailEncryption,
    mailUsername,
    mailPassword,
    mailFromEmail,
    mailFromName,
    loadMailSettings,
    t,
    toast,
  ]);

  const handleClearMailPassword = useCallback(async () => {
    setMailSaving(true);
    try {
      await apiClient.put('/settings/tokens', { values: { LEAGENT_SMTP_PASSWORD: '' } });
      toast({ variant: 'success', title: t('settings.mailSaved') });
      await loadMailSettings();
    } catch (e) {
      toast({
        variant: 'error',
        title: e instanceof Error ? e.message : 'Error',
      });
    } finally {
      setMailSaving(false);
    }
  }, [loadMailSettings, t, toast]);

  const handleMailTest = useCallback(async () => {
    setMailTestBusy(true);
    try {
      const res = await apiClient.post<{ ok?: boolean; detail?: string }>('/settings/mail/test', {
        to: mailTestTo.trim() || null,
      });
      toast({
        variant: 'success',
        title: res.detail ?? t('settings.mailTestOk'),
      });
    } catch (e: unknown) {
      const title =
        e instanceof HttpError ? e.message : e instanceof Error ? e.message : 'Error';
      toast({ variant: 'error', title });
    } finally {
      setMailTestBusy(false);
    }
  }, [mailTestTo, t, toast]);

  const tabs: Array<{ id: SettingsTab; label: string; icon: typeof Settings2 }> = [
    { id: 'general', label: t('settings.general'), icon: Settings2 },
    { id: 'tools', label: t('settings.tools'), icon: Wrench },
    { id: 'schedule', label: t('settings.schedule'), icon: Clock },
    { id: 'models', label: t('settings.models'), icon: Cpu },
    { id: 'plugins', label: t('settings.plugins'), icon: Package },
    { id: 'tokens', label: t('settings.tokensNav'), icon: KeyRound },
    { id: 'mail', label: t('settings.mailNav'), icon: Mail },
    { id: 'pythonPackages', label: t('settings.pythonPackages'), icon: Terminal },
    { id: 'about', label: t('settings.aboutNav'), icon: Info },
  ];

  const resolvedUiLang = i18n.language === 'en' || i18n.language === 'en-US' ? 'en-US' : 'zh-CN';

  return (
    // SettingsPage intentionally uses a slightly narrower column than the
    // default PageShell (max-w-6xl) for comfortable form reading, applied via
    // `className` rather than nesting another max-w wrapper.
    <PageShell
      title={t('settings.title')}
      description={t('settings.description')}
      className="max-w-6xl"
    >
      <div className="flex flex-col lg:flex-row gap-8">
        {/* Sidebar nav */}
        <div className="lg:w-56 flex-shrink-0">
          <Card className="sticky top-6">
            <CardContent padding="sm">
              <nav className="space-y-0.5" aria-label={t('settings.ariaSettingsNav')}>
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={cn(
                      'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors',
                      activeTab === tab.id
                        ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300 font-medium'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                    )}
                    aria-current={activeTab === tab.id ? 'page' : undefined}
                  >
                    <tab.icon className="w-4.5 h-4.5" aria-hidden="true" />
                    <span className="text-sm">{tab.label}</span>
                  </button>
                ))}
              </nav>
            </CardContent>
          </Card>
        </div>

        {/* Main content area */}
        <div className="flex-1 min-w-0 space-y-6">
          {/* ── General tab ── */}
          {activeTab === 'general' && (
            <>
              {/* Language & theme */}
              <Card>
                <CardHeader>
                  <CardTitle>{t('settings.general')}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <SettingRow
                    label={t('settings.language')}
                    description={t('settings.languageDescription')}
                  >
                    <Select
                      value={resolvedUiLang}
                      onChange={(e) => void handleLanguageChange(e.target.value)}
                      className="w-36"
                      aria-label={t('settings.language')}
                    >
                      <option value="zh-CN">{t('settings.langZhCN')}</option>
                      <option value="en-US">{t('settings.langEnUS')}</option>
                    </Select>
                  </SettingRow>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="mb-0 border-b border-border pb-4">
                  <CardTitle>{t('settings.appearance')}</CardTitle>
                </CardHeader>
                <CardContent padding="none" className="pt-5">
                  {/* Interface theme */}
                  <section aria-labelledby="settings-appearance-theme">
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <h4
                          id="settings-appearance-theme"
                          className="text-sm font-semibold tracking-tight text-foreground"
                        >
                          {t('settings.theme')}
                        </h4>
                        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                          {t('settings.themeDescription')}
                        </p>
                      </div>
                      <div
                        className="flex flex-wrap gap-2 sm:shrink-0"
                        role="radiogroup"
                        aria-label={t('settings.theme')}
                      >
                      {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
                        <button
                          key={value}
                          type="button"
                          role="radio"
                          aria-checked={theme === value}
                          onClick={() => setTheme(value)}
                          className={cn(
                            'inline-flex min-h-[2.5rem] flex-1 items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors sm:flex-initial sm:min-w-[7.5rem]',
                            theme === value
                              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/25 text-primary-700 dark:text-primary-300 shadow-sm'
                              : 'border-border bg-surface text-muted-foreground hover:border-border hover:bg-surface-sunken hover:text-foreground dark:hover:bg-surface-elevated'
                          )}
                        >
                          <Icon className="h-4 w-4 shrink-0 opacity-90" aria-hidden="true" />
                          <span>{t(label)}</span>
                        </button>
                      ))}
                      </div>
                    </div>
                  </section>

                  <div className="py-6" role="presentation">
                    <div className="h-px bg-border" />
                  </div>

                  {/* Sidebar logo & backdrop */}
                  <section className="space-y-4" aria-labelledby="settings-appearance-brand">
                    <div>
                      <h4
                        id="settings-appearance-brand"
                        className="text-sm font-semibold tracking-tight text-foreground"
                      >
                        {t('settings.brandingSectionTitle')}
                      </h4>
                      <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                        {t('settings.brandingSectionDescription')}
                      </p>
                    </div>

                    <div className="space-y-6 rounded-xl border border-border-subtle bg-surface-sunken/40 p-4 sm:p-5 dark:bg-surface-elevated/20">
                      <div className="space-y-2">
                        <label
                          htmlFor="branding-display-name"
                          className="text-sm font-medium text-foreground"
                        >
                          {t('settings.brandingDisplayName')}
                        </label>
                        <p className="text-xs leading-relaxed text-muted-foreground">
                          {t('settings.brandingDisplayNameDescription')}
                        </p>
                        <Input
                          id="branding-display-name"
                          value={displayName}
                          onChange={(e) => setDisplayName(e.target.value)}
                          className="w-full max-w-md"
                          maxLength={32}
                          placeholder={t('settings.brandingDisplayNamePlaceholder')}
                          autoComplete="off"
                        />
                      </div>

                      <div className="h-px bg-border/80" role="presentation" />

                      <div className="space-y-3">
                        <div>
                          <p className="text-sm font-medium text-foreground">{t('settings.brandFont')}</p>
                          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                            {t('settings.brandFontDescription')}
                          </p>
                        </div>
                        <div
                          className="grid grid-cols-2 gap-2 lg:grid-cols-4"
                          role="radiogroup"
                          aria-label={t('settings.brandFont')}
                        >
                          {BRAND_FONT_PRESETS.map((value) => {
                            const { labelKey, sample, className } = BRAND_FONT_META[value];
                            return (
                              <button
                                key={value}
                                type="button"
                                role="radio"
                                aria-checked={brandFontPreset === value}
                                onClick={() => setBrandFontPreset(value)}
                                className={cn(
                                  'flex min-h-[3.25rem] w-full flex-col items-center justify-center rounded-lg border px-2 py-2 text-center transition-colors',
                                  brandFontPreset === value
                                    ? 'border-primary-500 bg-primary-50 text-primary-700 shadow-sm dark:bg-primary-900/25 dark:text-primary-300'
                                    : 'border-border bg-surface text-muted-foreground hover:bg-surface-sunken hover:text-foreground dark:hover:bg-surface-elevated'
                                )}
                              >
                                <span className={cn('text-sm font-bold leading-none', className)}>{sample}</span>
                                <span className="mt-1 text-[11px] leading-none">{t(labelKey)}</span>
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      <div className="h-px bg-border/80" role="presentation" />

                      <div className="space-y-3">
                        <input
                          ref={brandingIconInputRef}
                          type="file"
                          accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml"
                          className="sr-only"
                          aria-label={t('settings.brandingIcon')}
                          onChange={(e) => void onBrandingIconFile(e)}
                        />
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-foreground">{t('settings.brandingIcon')}</p>
                            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                              {t('settings.brandingIconDescription')}
                            </p>
                          </div>
                          <div className="flex flex-wrap justify-start gap-2 sm:ml-auto sm:shrink-0 sm:justify-end">
                            <button
                              type="button"
                              className="flex min-h-[2.75rem] min-w-[5.5rem] items-center justify-center gap-2 rounded-lg border border-border bg-surface px-2 py-2 text-center text-xs font-medium text-muted-foreground transition-colors hover:border-border hover:bg-surface-sunken hover:text-foreground sm:text-sm dark:hover:bg-surface-elevated"
                              onClick={() => brandingIconInputRef.current?.click()}
                            >
                              {t('settings.brandingIconUpload')}
                            </button>
                            {customIconDataUrl ? (
                              <button
                                type="button"
                                className="flex min-h-[2.75rem] min-w-[5.5rem] items-center justify-center gap-2 rounded-lg border border-border bg-surface px-2 py-2 text-center text-xs font-medium text-muted-foreground transition-colors hover:border-border hover:bg-surface-sunken hover:text-foreground sm:text-sm dark:hover:bg-surface-elevated"
                                onClick={() => setCustomIconDataUrl(null)}
                              >
                                {t('settings.brandingIconClear')}
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <div className="flex flex-col gap-4 sm:flex-row sm:items-stretch">
                          <div className="flex shrink-0 items-center justify-center p-1">
                            <AppLogo src={customIconDataUrl} className="size-16 rounded-lg" />
                          </div>
                        </div>
                      </div>

                      <div className="h-px bg-border/80" role="presentation" />

                      <div className="space-y-3">
                        <div>
                          <p className="text-sm font-medium text-foreground">{t('settings.brandingBackdrop')}</p>
                          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                            {t('settings.brandingBackdropDescription')}
                          </p>
                        </div>
                        <div
                          className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5"
                          role="radiogroup"
                          aria-label={t('settings.brandingBackdrop')}
                        >
                          {LOGO_BACKDROP_PRESETS.map((value) => {
                            const { labelKey, icon: Icon } = BRANDING_BACKDROP_META[value];
                            return (
                              <button
                                key={value}
                                type="button"
                                role="radio"
                                aria-checked={logoBackdropPreset === value}
                                onClick={() => setLogoBackdropPreset(value)}
                                className={cn(
                                  'flex min-h-[2.75rem] w-full items-center justify-center gap-2 rounded-lg border px-2 py-2 text-center text-xs font-medium transition-colors sm:text-sm',
                                  logoBackdropPreset === value
                                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/25 text-primary-700 dark:text-primary-300 shadow-sm'
                                    : 'border-border bg-surface text-muted-foreground hover:border-border hover:bg-surface-sunken hover:text-foreground dark:hover:bg-surface-elevated'
                                )}
                              >
                                <Icon className="h-3.5 w-3.5 shrink-0 opacity-90 sm:h-4 sm:w-4" aria-hidden />
                                <span className="leading-tight">{t(labelKey)}</span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col gap-3 rounded-lg border border-dashed border-border bg-surface-sunken/30 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between dark:bg-surface-elevated/15">
                      <p className="text-sm leading-relaxed text-muted-foreground sm:max-w-xl">
                        {t('settings.brandingResetDescription')}
                      </p>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        className="shrink-0 self-start sm:self-auto"
                        onClick={() => resetBranding()}
                      >
                        {t('settings.brandingReset')}
                      </Button>
                    </div>
                  </section>
                </CardContent>
              </Card>

              {/* Danger zone */}
              <Card>
                <CardHeader>
                  <CardTitle>{t('settings.dangerZone')}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between p-4 rounded-xl border border-red-200 dark:border-red-800/50 bg-red-50/60 dark:bg-red-900/10">
                    <div className="min-w-0 mr-4">
                      <p className="font-medium text-red-700 dark:text-red-400">
                        {t('settings.deleteAccount')}
                      </p>
                      <p className="text-sm text-red-600/80 dark:text-red-400/70">
                        {t('settings.deleteAccountDescription')}
                      </p>
                    </div>
                    <Button variant="danger" className="flex-shrink-0">{t('settings.deleteAccountButton')}</Button>
                  </div>
                </CardContent>
              </Card>
            </>
          )}

          {/* ── Tools tab ── */}
          {activeTab === 'tools' && (
            <Card>
              <CardHeader>
                <SectionHeader
                  className="w-full"
                  titleAs="h3"
                  icon={<Wrench className="h-5 w-5" aria-hidden />}
                  title={t('settings.toolsTabCardTitle')}
                  description={t('settings.toolsTabCardDesc')}
                  actions={
                    <Button
                      size="sm"
                      responsive="md"
                      leftIcon={<Plus className="w-4 h-4" aria-hidden />}
                    >
                      {t('settings.addCustomTool')}
                    </Button>
                  }
                />
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {tools.map((tool) => {
                    const Icon = CATEGORY_ICONS[tool.category] || Code;
                    return (
                      <div
                        key={tool.id}
                        className={cn(
                          'flex items-center justify-between p-4 rounded-xl border transition-colors',
                          tool.enabled
                            ? 'border-gray-200 dark:border-gray-700 bg-surface'
                            : 'border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-surface/40 opacity-60'
                        )}
                      >
                        <div className="flex items-center gap-3">
                          <div className={cn(
                            'w-9 h-9 rounded-lg flex items-center justify-center',
                            tool.enabled
                              ? 'bg-primary-100 dark:bg-primary-900/30'
                              : 'bg-gray-100 dark:bg-surface'
                          )}>
                            <Icon
                              className={cn(
                                'w-4.5 h-4.5',
                                tool.enabled ? 'text-primary-600 dark:text-primary-400' : 'text-gray-400'
                              )}
                              aria-hidden="true"
                            />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-medium text-gray-900 dark:text-white">
                                {t(tool.nameKey)}
                              </p>
                              <Badge variant="default" size="sm">{tool.category}</Badge>
                            </div>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                              {t(tool.descriptionKey)}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <Button variant="ghost" size="sm" aria-label={t('settings.ariaConfigureTool', { name: t(tool.nameKey) })}>
                            <Settings2 className="w-4 h-4" aria-hidden="true" />
                          </Button>
                          <Switch
                            checked={tool.enabled}
                            onChange={() => handleToggleTool(tool.id)}
                            aria-label={t('settings.ariaToggleTool', { name: t(tool.nameKey) })}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          {/* ── Schedule tab ── */}
          {activeTab === 'schedule' && (
            <Card>
              <CardHeader>
                <SectionHeader
                  className="w-full"
                  titleAs="h3"
                  icon={<Clock className="h-5 w-5" aria-hidden />}
                  title={t('settings.scheduleTabCardTitle')}
                  description={t('settings.scheduleTabCardDesc')}
                  actions={
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        responsive="md"
                        onClick={() => navigate('/cron')}
                        leftIcon={<Settings2 className="w-4 h-4" aria-hidden />}
                      >
                        {t('settings.manageAllScheduleTasks')}
                      </Button>
                      <Button
                        size="sm"
                        responsive="md"
                        onClick={handleOpenAddSchedule}
                        leftIcon={<Plus className="w-4 h-4" aria-hidden />}
                      >
                        {t('settings.addScheduleTask')}
                      </Button>
                    </div>
                  }
                />
              </CardHeader>
              <CardContent>
                {cronJobsLoading ? (
                  <div className="flex justify-center py-10">
                    <PageLoader size="sm" message={t('settings.scheduleLoading')} />
                  </div>
                ) : cronJobsError ? (
                  <p className="text-sm text-red-600 dark:text-red-400 py-6 text-center">
                    {t('settings.scheduleErrorLoading')}
                  </p>
                ) : scheduledTasks.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-14">
                    <p className="text-sm text-muted-foreground mb-4">{t('settings.emptySchedule')}</p>
                    <Button
                      size="sm"
                      onClick={handleOpenAddSchedule}
                      leftIcon={<Plus className="w-4 h-4" />}
                    >
                      {t('settings.createFirstSchedule')}
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {scheduledTasks.map((task) => (
                      <ScheduleTaskRow
                        key={task.id}
                        task={task}
                        busy={taskBusyId === task.id}
                        onToggle={handleToggleTask}
                        onRun={handleRunTask}
                        onEdit={handleOpenEditSchedule}
                        onDelete={handleDeleteTask}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* ── Models tab ── */}
          {activeTab === 'models' && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>{t('settings.defaultModelCardTitle')}</CardTitle>
                </CardHeader>
                <CardContent>
                  <SettingRow
                    label={t('settings.defaultModelLabel')}
                    description={t('settings.defaultModelDesc')}
                  >
                    <Select
                      value={currentDefault}
                      onChange={(e) => handleDefaultModelChange(e.target.value)}
                      className="w-64"
                      aria-label={t('settings.defaultModelAria')}
                    >
                      <option value="">{t('settings.selectModelPlaceholder')}</option>
                      {enabledProviders.map((provider) => (
                        <optgroup key={provider.name} label={provider.label || provider.name}>
                          {provider.models
                            .filter((m) => m.enabled !== false)
                            .map((m) => (
                            <option key={`${provider.name}/${m.name}`} value={`${provider.name}/${m.name}`}>
                              {m.name}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </Select>
                  </SettingRow>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <SectionHeader
                    className="w-full"
                    titleAs="h3"
                    icon={<Cpu className="h-5 w-5" aria-hidden />}
                    title={t('settings.providerCardTitle')}
                    description={t('settings.providerCardDesc')}
                    actions={
                      <Button
                        size="sm"
                        variant="outline"
                        responsive="md"
                        onClick={() => navigate('/admin')}
                        leftIcon={<Settings2 className="w-4 h-4" aria-hidden />}
                      >
                        {t('settings.manageProvidersBtn')}
                      </Button>
                    }
                  />
                </CardHeader>
                <CardContent>
                  {providersLoading ? (
                    <div className="flex items-center justify-center py-10">
                      <PageLoader size="sm" message={t('settings.loadingProvidersMsg')} />
                    </div>
                  ) : providers && providers.length > 0 ? (
                    <div className="space-y-3">
                      {providers.map((provider) => {
                        const brand = PROVIDER_BRAND[provider.type] ?? DEFAULT_BRAND;
                        const isEditingKey = editingProviderKey === provider.name;
                        const testStatus = providerTestStatus[provider.name] ?? 'idle';
                        const deepSeekBalance = provider.type === 'deepseek'
                          ? deepSeekBalances[provider.name]
                          : undefined;
                        return (
                          <div
                            key={provider.name}
                            className={cn(
                              'p-4 rounded-xl border transition-colors',
                              provider.enabled
                                ? 'border-gray-200 dark:border-gray-700 bg-surface'
                                : 'border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-surface/40 opacity-60'
                            )}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-3.5">
                                <div className={cn(
                                  'w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm',
                                  brand.bg, brand.text,
                                )}>
                                  {brand.letter}
                                </div>
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2">
                                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                                      {provider.name}
                                    </p>
                                    <HealthIcon status={provider.is_healthy} />
                                  </div>
                                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                    {provider.label} · {t('settings.modelCount', { count: provider.models.length })}
                                    {provider.type === 'deepseek' && provider.api_key_set && (
                                      <>
                                        {' · '}
                                        {t('settings.deepseekBalanceLabel', { defaultValue: 'Balance' })}:{' '}
                                        {deepSeekBalance?.state === 'success'
                                          ? formatDeepSeekBalance(deepSeekBalance.data)
                                          : deepSeekBalance?.state === 'error'
                                            ? t('settings.deepseekBalanceUnavailable', { defaultValue: 'Unavailable' })
                                            : t('settings.deepseekBalanceLoading', { defaultValue: 'Loading…' })}
                                        {deepSeekBalance?.state === 'success' && !deepSeekBalance.data.is_available && (
                                          <span className="ml-1 text-amber-600 dark:text-amber-400">
                                            {t('settings.deepseekBalanceInsufficient', { defaultValue: 'insufficient' })}
                                          </span>
                                        )}
                                      </>
                                    )}
                                  </p>
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => void handleTestProvider(provider.name)}
                                  disabled={testStatus === 'testing'}
                                  loading={testStatus === 'testing'}
                                  aria-label={t('settings.testConnection', { defaultValue: 'Test connection' })}
                                  title={t('settings.testConnection', { defaultValue: 'Test connection' })}
                                  leftIcon={
                                    testStatus === 'success' ? (
                                      <CheckCircle2 className="w-3.5 h-3.5 text-mint-500" aria-hidden />
                                    ) : testStatus === 'error' ? (
                                      <XCircle className="w-3.5 h-3.5 text-red-500" aria-hidden />
                                    ) : (
                                      <RefreshCw className="w-3.5 h-3.5" aria-hidden />
                                    )
                                  }
                                >
                                  {t('settings.testConnection', { defaultValue: 'Test connection' })}
                                </Button>
                                <Badge variant={provider.enabled ? 'success' : 'default'} size="sm">
                                  {provider.enabled ? t('settings.providerEnabled') : t('settings.providerDisabled')}
                                </Badge>
                              </div>
                            </div>

                            {/* Models chips */}
                            <div className="flex flex-wrap gap-1 mt-2.5 ml-[3.375rem]">
                              {provider.models.slice(0, 4).map((m) => (
                                <span
                                  key={m.name}
                                  className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700/60 text-gray-600 dark:text-gray-400 rounded-md"
                                >
                                  {m.name}
                                </span>
                              ))}
                              {provider.models.length > 4 && (
                                <span className="px-2 py-0.5 text-xs text-gray-400 dark:text-gray-500">
                                  +{provider.models.length - 4}
                                </span>
                              )}
                            </div>

                            {/* Inline API key config */}
                            <div className="mt-3 ml-[3.375rem] pt-3 border-t border-border-subtle/60">
                              {provider.requires_api_key === false ? (
                                <p className="text-xs text-muted-foreground">
                                  {t('admin.provider.apiKeyNotRequired')}
                                </p>
                              ) : isEditingKey ? (
                                <div className="flex items-center gap-2">
                                  <Input
                                    type="password"
                                    value={providerKeyDraft}
                                    onChange={(e) => setProviderKeyDraft(e.target.value)}
                                    placeholder={t('settings.apiKeyPlaceholder', { defaultValue: 'Enter API key...' })}
                                    className="flex-1 text-sm font-mono"
                                    autoComplete="off"
                                    autoFocus
                                  />
                                  <Button
                                    size="sm"
                                    onClick={() => void handleSaveProviderApiKey(provider.name)}
                                    disabled={!providerKeyDraft.trim()}
                                  >
                                    {t('common.save', { defaultValue: 'Save' })}
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => { setEditingProviderKey(null); setProviderKeyDraft(''); }}
                                  >
                                    {t('common.cancel', { defaultValue: 'Cancel' })}
                                  </Button>
                                </div>
                              ) : (
                                <div className="flex items-center gap-2 min-w-0">
                                  <Key className="w-3.5 h-3.5 text-muted-foreground-tertiary flex-shrink-0" aria-hidden />
                                  <span className="text-xs text-muted-foreground min-w-0">
                                    {provider.api_key_set
                                      ? t('settings.apiKeyConfigured', { defaultValue: '••••••••' })
                                      : t('settings.apiKeyNotConfigured', { defaultValue: 'Not configured' })}
                                  </span>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="text-xs shrink-0"
                                    onClick={() => { setEditingProviderKey(provider.name); setProviderKeyDraft(''); }}
                                    leftIcon={<Edit2 className="w-3 h-3" aria-hidden />}
                                  >
                                    {t('settings.editApiKey', { defaultValue: 'Edit' })}
                                  </Button>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-14">
                      <PageLoader size="md" message={t('settings.noProvidersMsg')} />
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 mb-4">
                        {t('settings.noProvidersHint')}
                      </p>
                      <Button
                        size="sm"
                        onClick={() => navigate('/admin')}
                        leftIcon={<Plus className="w-4 h-4" />}
                      >
                        {t('settings.addProviderBtn')}
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* DeepSeek-specific settings */}
              {providers?.some((p) => p.type === 'deepseek' && p.enabled) && (
                <Card>
                  <CardHeader>
                    <CardTitle>{t('settings.deepseekSettingsTitle', { defaultValue: 'DeepSeek Thinking Mode' })}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    <SettingRow
                      label={t('settings.deepseekThinkingMode', { defaultValue: 'Thinking mode' })}
                      description={t('settings.deepseekThinkingModeDesc', { defaultValue: 'Enable chain-of-thought reasoning before final answers (DeepSeek V4)' })}
                    >
                      <Select
                        defaultValue="enabled"
                        className="w-36"
                        aria-label={t('settings.deepseekThinkingMode', { defaultValue: 'Thinking mode' })}
                      >
                        <option value="enabled">{t('settings.enabled', { defaultValue: 'Enabled' })}</option>
                        <option value="disabled">{t('settings.disabled', { defaultValue: 'Disabled' })}</option>
                      </Select>
                    </SettingRow>
                    <SettingRow
                      label={t('settings.deepseekReasoningEffort', { defaultValue: 'Reasoning effort' })}
                      description={t('settings.deepseekReasoningEffortDesc', { defaultValue: 'Controls depth of reasoning (high = standard, max = complex tasks)' })}
                    >
                      <Select
                        defaultValue="high"
                        className="w-36"
                        aria-label={t('settings.deepseekReasoningEffort', { defaultValue: 'Reasoning effort' })}
                      >
                        <option value="high">{t('settings.effortHigh', { defaultValue: 'High' })}</option>
                        <option value="max">{t('settings.effortMax', { defaultValue: 'Max' })}</option>
                      </Select>
                    </SettingRow>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader>
                  <CardTitle>{t('settings.advancedSettingsTitle')}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  <SettingRow label={t('settings.streamingLabel')} description={t('settings.streamingDesc')}>
                    <Switch defaultChecked aria-label={t('settings.streamingLabel')} />
                  </SettingRow>
                  <SettingRow label={t('settings.autoRetryLabel')} description={t('settings.autoRetryDesc')}>
                    <Switch defaultChecked aria-label={t('settings.autoRetryLabel')} />
                  </SettingRow>
                  <SettingRow label={t('settings.debugLabel')} description={t('settings.debugDesc')}>
                    <Switch aria-label={t('settings.debugLabel')} />
                  </SettingRow>
                </CardContent>
              </Card>
            </>
          )}

          {/* ── Plugins tab ── */}
          {activeTab === 'plugins' && (
            <Card>
              <CardHeader>
                <CardTitle>{t('settings.pluginsCardTitle')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">{t('settings.pluginsCardDesc')}</p>
                {extensionsLoading ? (
                  <div className="flex justify-center py-8">
                    <PageLoader size="sm" message={t('settings.pluginsLoading')} />
                  </div>
                ) : extensionPacks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t('settings.pluginsEmpty')}</p>
                ) : (
                  <ul className="space-y-3">
                    {extensionPacks.map((pack) => (
                      <li
                        key={pack.id}
                        className="flex flex-col gap-2 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="min-w-0">
                          <p className="font-medium text-foreground">{pack.name}</p>
                          <p className="text-xs text-muted-foreground mt-1">{pack.description}</p>
                          <Badge variant={pack.installed ? 'success' : 'default'} size="sm" className="mt-2">
                            {pack.installed ? t('settings.pluginsInstalled') : t('settings.pluginsPending')}
                          </Badge>
                        </div>
                        <div className="flex gap-2 shrink-0">
                          {!pack.installed ? (
                            <Button
                              size="sm"
                              onClick={() => void handleInstallPack(pack.id)}
                              disabled={extensionBusyId !== null}
                            >
                              {extensionBusyId === pack.id ? '…' : t('settings.pluginsInstall')}
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void handleUninstallPack(pack.id)}
                              disabled={extensionBusyId !== null}
                            >
                              {extensionBusyId === pack.id ? '…' : t('settings.pluginsUninstall')}
                            </Button>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          )}

          {/* ── Environment tokens (.env) ── */}
          {activeTab === 'tokens' && (
            <Card>
              <CardHeader>
                <CardTitle>{t('settings.tokensTitle')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">{t('settings.tokensDesc')}</p>
                {tokensLoading ? (
                  <div className="flex justify-center py-10">
                    <PageLoader size="sm" message={t('settings.tokensLoading')} />
                  </div>
                ) : (
                  <>
                    <ul className="space-y-4">
                      {TOKEN_ENV_ROWS.map(({ key, labelKey }) => (
                        <li
                          key={key}
                          className="rounded-lg border border-border bg-muted/10 p-3 sm:p-4 space-y-2"
                        >
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-foreground">{t(labelKey)}</p>
                              <p className="font-mono text-[11px] text-muted-foreground truncate">
                                {key}
                              </p>
                            </div>
                            <Badge
                              variant={tokenStatus[key] ? 'success' : 'default'}
                              size="sm"
                              className="w-fit shrink-0"
                            >
                              {tokenStatus[key]
                                ? t('settings.tokensConfigured')
                                : t('settings.tokensNotConfigured')}
                            </Badge>
                          </div>
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                            <Input
                              type="password"
                              autoComplete="off"
                              value={tokenDrafts[key] ?? ''}
                              onChange={(e) =>
                                setTokenDrafts((d) => ({ ...d, [key]: e.target.value }))
                              }
                              placeholder={t('settings.tokensPlaceholder')}
                              className="font-mono text-sm sm:flex-1"
                              aria-label={t(labelKey)}
                              disabled={tokensSaving}
                            />
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="shrink-0"
                              disabled={tokensSaving || !tokenStatus[key]}
                              onClick={() => void handleClearEnvToken(key)}
                            >
                              {t('settings.tokensClear')}
                            </Button>
                          </div>
                        </li>
                      ))}
                    </ul>
                    <div className="flex justify-end pt-2">
                      <Button
                        type="button"
                        onClick={() => void handleSaveEnvTokens()}
                        loading={tokensSaving}
                        disabled={
                          tokensSaving ||
                          !TOKEN_ENV_ROWS.some(({ key }) => (tokenDrafts[key] ?? '').trim())
                        }
                      >
                        {t('settings.tokensSave')}
                      </Button>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          )}

          {/* ── Outbound mail (SMTP) ── */}
          {activeTab === 'mail' && (
            <Card>
              <CardHeader>
                <CardTitle>{t('settings.mailTitle')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <p className="text-sm text-muted-foreground">{t('settings.mailDesc')}</p>
                {mailLoading ? (
                  <div className="flex justify-center py-10">
                    <PageLoader size="sm" message={t('settings.mailLoading')} />
                  </div>
                ) : (
                  <>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="space-y-2 sm:col-span-2">
                        <label className="text-sm font-medium text-foreground" htmlFor="mail-host">
                          {t('settings.mailHost')}
                        </label>
                        <Input
                          id="mail-host"
                          value={mailHost}
                          onChange={(e) => setMailHost(e.target.value)}
                          autoComplete="off"
                          placeholder="smtp.example.com"
                          disabled={mailSaving}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-foreground" htmlFor="mail-port">
                          {t('settings.mailPort')}
                        </label>
                        <Input
                          id="mail-port"
                          type="number"
                          min={1}
                          max={65535}
                          value={mailPort}
                          onChange={(e) => setMailPort(e.target.value)}
                          autoComplete="off"
                          disabled={mailSaving}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-foreground" htmlFor="mail-enc">
                          {t('settings.mailEncryption')}
                        </label>
                        <Select
                          id="mail-enc"
                          value={mailEncryption}
                          onChange={(e) => setMailEncryption(e.target.value as MailEncryptionMode)}
                          disabled={mailSaving}
                        >
                          <option value="starttls">{t('settings.mailEncryptionStarttls')}</option>
                          <option value="ssl">{t('settings.mailEncryptionSsl')}</option>
                          <option value="none">{t('settings.mailEncryptionNone')}</option>
                        </Select>
                      </div>
                      <div className="space-y-2 sm:col-span-2">
                        <label className="text-sm font-medium text-foreground" htmlFor="mail-user">
                          {t('settings.mailUsername')}
                        </label>
                        <Input
                          id="mail-user"
                          value={mailUsername}
                          onChange={(e) => setMailUsername(e.target.value)}
                          autoComplete="off"
                          placeholder={t('settings.mailUsernamePlaceholder')}
                          disabled={mailSaving}
                        />
                        {mailSnapshot ? (
                          <p className="text-xs text-muted-foreground">
                            {mailSnapshot.username_set
                              ? t('settings.mailUsernameStored')
                              : t('settings.mailUsernameNotStored')}
                          </p>
                        ) : null}
                      </div>
                      <div className="space-y-2 sm:col-span-2">
                        <label className="text-sm font-medium text-foreground" htmlFor="mail-pass">
                          {t('settings.mailPassword')}
                        </label>
                        <Input
                          id="mail-pass"
                          type="password"
                          value={mailPassword}
                          onChange={(e) => setMailPassword(e.target.value)}
                          autoComplete="new-password"
                          placeholder={t('settings.mailPasswordPlaceholder')}
                          disabled={mailSaving}
                        />
                        <div className="flex flex-wrap items-center gap-2">
                          {mailSnapshot ? (
                            <p className="text-xs text-muted-foreground">
                              {mailSnapshot.password_set
                                ? t('settings.mailPasswordStored')
                                : t('settings.mailPasswordNotStored')}
                            </p>
                          ) : null}
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={mailSaving || !mailSnapshot?.password_set}
                            onClick={() => void handleClearMailPassword()}
                          >
                            {t('settings.mailPasswordClear')}
                          </Button>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-foreground" htmlFor="mail-from">
                          {t('settings.mailFromEmail')}
                        </label>
                        <Input
                          id="mail-from"
                          type="email"
                          value={mailFromEmail}
                          onChange={(e) => setMailFromEmail(e.target.value)}
                          autoComplete="off"
                          disabled={mailSaving}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-foreground" htmlFor="mail-from-name">
                          {t('settings.mailFromName')}
                        </label>
                        <Input
                          id="mail-from-name"
                          value={mailFromName}
                          onChange={(e) => setMailFromName(e.target.value)}
                          autoComplete="off"
                          disabled={mailSaving}
                        />
                      </div>
                    </div>
                    <div className="rounded-lg border border-border bg-muted/10 p-4 space-y-3">
                      <p className="text-sm font-medium text-foreground">{t('settings.mailTestSection')}</p>
                      <Input
                        value={mailTestTo}
                        onChange={(e) => setMailTestTo(e.target.value)}
                        type="email"
                        autoComplete="off"
                        placeholder={t('settings.mailTestToPlaceholder')}
                        disabled={mailTestBusy || mailSaving}
                        aria-label={t('settings.mailTestTo')}
                      />
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => void handleMailTest()}
                          loading={mailTestBusy}
                          disabled={mailTestBusy || mailSaving || !mailHost.trim()}
                        >
                          {mailTestTo.trim()
                            ? t('settings.mailTestSend')
                            : t('settings.mailTestConnection')}
                        </Button>
                      </div>
                    </div>
                    <div className="flex justify-end pt-2">
                      <Button
                        type="button"
                        onClick={() => void handleSaveMail()}
                        loading={mailSaving}
                        disabled={mailSaving || mailTestBusy}
                      >
                        {t('settings.mailSave')}
                      </Button>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          )}

          {/* ── Python packages tab ── */}
          {activeTab === 'pythonPackages' && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>{t('settings.pythonPackagesTitle')}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">{t('settings.pythonPackagesDesc')}</p>

                  {/* env info banner */}
                  {pythonEnvInfo ? (
                    <div className="rounded-lg border border-border bg-muted/10 p-3 space-y-1.5">
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                          <Terminal className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
                          <span className="font-medium text-foreground/80">{t('settings.pythonPackagesInterpreter')}:</span>
                          <code className="font-mono text-[11px] break-all">{pythonEnvInfo.python_executable}</code>
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {pythonEnvInfo.project_mode ? (
                          <Badge variant="default" className="text-[10px] px-1.5 py-0">
                            {t('settings.pythonPackagesUvProject')}
                          </Badge>
                        ) : pythonEnvInfo.uses_uv ? (
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                            {t('settings.pythonPackagesUv')}
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">pip</Badge>
                        )}
                        {pythonEnvInfo.has_lockfile && (
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0">uv.lock</Badge>
                        )}
                        {pythonPackages.length > 0 && (
                          <span className="text-[11px] text-muted-foreground tabular-nums">
                            {t('settings.pythonPackagesTotal', { count: pythonPackages.length })}
                          </span>
                        )}
                      </div>
                    </div>
                  ) : null}

                  {/* install bar */}
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                    <div className="flex-1 min-w-0">
                      <Input
                        value={pythonInstallSpec}
                        onChange={(e) => setPythonInstallSpec(e.target.value)}
                        placeholder={t('settings.pythonPackagesPlaceholder')}
                        autoComplete="off"
                        aria-label={t('settings.pythonPackagesPlaceholder')}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void handlePythonInstall();
                        }}
                      />
                    </div>
                    <div className="flex flex-wrap gap-1.5 sm:shrink-0">
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => void handlePythonInstall()}
                        disabled={pythonPackagesLoading || pythonEnvBusyId !== null || !pythonInstallSpec.trim()}
                      >
                        {pythonEnvBusyId === 'install' ? '…' : t('settings.pythonPackagesInstall')}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => void loadPythonEnvironment()}
                        disabled={pythonPackagesLoading || pythonEnvBusyId !== null}
                        leftIcon={<RefreshCw className="h-3.5 w-3.5 shrink-0" aria-hidden />}
                      >
                        {t('settings.pythonPackagesRefresh')}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => void handleCheckOutdated()}
                        disabled={pythonPackagesLoading || pythonEnvBusyId !== null || pythonOutdatedLoading}
                        loading={pythonOutdatedLoading}
                      >
                        {t('settings.pythonPackagesCheckOutdated')}
                      </Button>
                      {pythonEnvInfo?.project_mode && (
                        <>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => void handlePythonSync()}
                            disabled={pythonPackagesLoading || pythonEnvBusyId !== null}
                            loading={pythonEnvBusyId === 'sync'}
                          >
                            {t('settings.pythonPackagesSync')}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => void handlePythonTree()}
                            disabled={pythonPackagesLoading || pythonEnvBusyId !== null}
                            leftIcon={<GitBranch className="h-3.5 w-3.5 shrink-0" aria-hidden />}
                            loading={pythonEnvBusyId === 'tree'}
                          >
                            {t('settings.pythonPackagesTree')}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* search + filter bar */}
                  {!pythonPackagesLoading && pythonPackages.length > 0 && (
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                      <div className="relative flex-1 min-w-0">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                        <Input
                          value={pythonSearch}
                          onChange={(e) => setPythonSearch(e.target.value)}
                          placeholder={t('settings.pythonPackagesSearch')}
                          className="pl-8 h-8 text-xs"
                          autoComplete="off"
                        />
                      </div>
                      <div className="flex gap-1 shrink-0">
                        {(['all', 'direct', 'outdated'] as const).map((mode) => (
                          <Button
                            key={mode}
                            type="button"
                            variant={pythonFilter === mode ? 'primary' : 'ghost'}
                            size="sm"
                            className="h-8 px-2.5 text-xs"
                            onClick={() => setPythonFilter(mode)}
                          >
                            {mode === 'all'
                              ? t('settings.pythonPackagesShowAll')
                              : mode === 'direct'
                                ? t('settings.pythonPackagesShowDirect')
                                : t('settings.pythonPackagesShowOutdated')}
                            {mode === 'outdated' && Object.keys(pythonOutdated).length > 0 && (
                              <Badge variant="default" className="ml-1 text-[9px] px-1 py-0 min-w-[1.1rem] justify-center">
                                {Object.keys(pythonOutdated).length}
                              </Badge>
                            )}
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* package list */}
                  {pythonPackagesLoading ? (
                    <div className="flex justify-center py-8">
                      <PageLoader size="sm" message={t('settings.pythonPackagesLoading')} />
                    </div>
                  ) : pythonPackages.length === 0 ? (
                    <p className="text-sm text-muted-foreground">{t('settings.pythonPackagesEmpty')}</p>
                  ) : (
                    <ul className="max-h-[min(520px,55vh)] overflow-y-auto rounded-lg border border-border divide-y divide-border bg-muted/15">
                      {filteredPythonPackages.map((pkg) => {
                        const outdatedVer = pythonOutdated[pkg.name];
                        return (
                          <li
                            key={pkg.name}
                            className="group flex items-center justify-between gap-2 px-3 py-1.5 hover:bg-muted/30 transition-colors"
                          >
                            <div className="min-w-0 flex items-center gap-2">
                              <span className="truncate text-xs font-medium text-foreground">{pkg.name}</span>
                              <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">
                                {pkg.version}
                              </span>
                              {pkg.is_direct && (
                                <Badge variant="outline" className="text-[9px] px-1 py-0 opacity-70">
                                  {t('settings.pythonPackagesDirect')}
                                </Badge>
                              )}
                              {outdatedVer && (
                                <Badge variant="secondary" className="text-[9px] px-1 py-0 text-amber-600 dark:text-amber-400 border-amber-300 dark:border-amber-700">
                                  {t('settings.pythonPackagesLatest', { version: outdatedVer })}
                                </Badge>
                              )}
                            </div>
                            <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                              {outdatedVer && (
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="ghost"
                                  className="h-7 w-7 rounded-md p-0 text-muted-foreground hover:bg-primary/10 hover:text-primary"
                                  loading={pythonEnvBusyId === `upgrade:${pkg.name}`}
                                  leftIcon={<ArrowUpCircle className="h-3.5 w-3.5" aria-hidden />}
                                  aria-label={t('settings.pythonPackagesUpgrade')}
                                  title={t('settings.pythonPackagesUpgrade')}
                                  onClick={() => void handlePythonUpgrade(pkg.name)}
                                  disabled={pythonEnvBusyId !== null}
                                />
                              )}
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                className="h-7 w-7 rounded-md p-0 text-muted-foreground hover:bg-red-500/10 hover:text-red-600 dark:hover:text-red-400"
                                loading={pythonEnvBusyId === pkg.name}
                                leftIcon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}
                                aria-label={t('settings.pythonPackagesUninstall')}
                                title={t('settings.pythonPackagesUninstall')}
                                onClick={() => setPythonConfirmUninstall(pkg.name)}
                                disabled={pythonEnvBusyId !== null}
                              />
                            </div>
                          </li>
                        );
                      })}
                      {filteredPythonPackages.length === 0 && (
                        <li className="px-3 py-6 text-center text-xs text-muted-foreground">
                          {t('settings.pythonPackagesEmpty')}
                        </li>
                      )}
                    </ul>
                  )}
                </CardContent>
              </Card>

              {/* confirm uninstall modal */}
              <Modal isOpen={pythonConfirmUninstall !== null} onClose={() => setPythonConfirmUninstall(null)} size="sm">
                <ModalHeader onClose={() => setPythonConfirmUninstall(null)}>
                  {t('settings.pythonPackagesUninstall')}
                </ModalHeader>
                <ModalBody>
                  <p className="text-sm">
                    {t('settings.pythonPackagesConfirmUninstall', { name: pythonConfirmUninstall ?? '' })}
                  </p>
                </ModalBody>
                <ModalFooter>
                  <Button variant="secondary" size="sm" onClick={() => setPythonConfirmUninstall(null)}>
                    {t('common.cancel')}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => pythonConfirmUninstall && void handlePythonUninstall(pythonConfirmUninstall)}
                    loading={pythonEnvBusyId === pythonConfirmUninstall}
                  >
                    {t('settings.pythonPackagesUninstall')}
                  </Button>
                </ModalFooter>
              </Modal>

              {/* log modal */}
              <Modal isOpen={pythonLogText !== null} onClose={() => setPythonLogText(null)} size="lg">
                <ModalHeader onClose={() => setPythonLogText(null)}>
                  {t('settings.pythonPackagesLog')}
                </ModalHeader>
                <ModalBody>
                  <pre className="max-h-[60vh] overflow-auto rounded-lg bg-muted/30 p-4 text-xs font-mono whitespace-pre-wrap break-all">
                    {pythonLogText}
                  </pre>
                </ModalBody>
              </Modal>

              {/* dep tree modal */}
              <Modal isOpen={pythonTreeText !== null} onClose={() => setPythonTreeText(null)} size="lg">
                <ModalHeader onClose={() => setPythonTreeText(null)}>
                  {t('settings.pythonPackagesTreeTitle')}
                </ModalHeader>
                <ModalBody>
                  <pre className="max-h-[60vh] overflow-auto rounded-lg bg-muted/30 p-4 text-xs font-mono whitespace-pre-wrap break-all">
                    {pythonTreeText}
                  </pre>
                </ModalBody>
              </Modal>
            </>
          )}

          {/* ── About tab ── */}
          {activeTab === 'about' && <AboutTabContent />}
        </div>
      </div>

      {/* ── Schedule modal ── */}
      <Modal isOpen={isScheduleModalOpen} onClose={handleCloseScheduleModal} size="md">
        <ModalHeader onClose={handleCloseScheduleModal}>
          {editingTask ? t('settings.scheduleModalEditTitle') : t('settings.scheduleModalAddTitle')}
        </ModalHeader>
        <ModalBody>
          <div className="space-y-4">
            <div>
              <label htmlFor="task-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                {t('settings.taskNameLabel')}
              </label>
              <Input
                id="task-name"
                value={taskFormName}
                onChange={(e) => setTaskFormName(e.target.value)}
                placeholder={t('settings.taskNamePlaceholder')}
                autoComplete="off"
              />
            </div>
            <div>
              <label htmlFor="task-flow" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                {t('settings.selectWorkflowLabel')}
              </label>
              <Select
                id="task-flow"
                value={taskFormFlowId}
                onChange={(e) => setTaskFormFlowId(e.target.value)}
                className="w-full"
              >
                <option value="">{t('settings.selectWorkflowPlaceholder')}</option>
                {availableFlows.map((flow) => (
                  <option key={flow.id} value={flow.id}>
                    {flow.name}
                  </option>
                ))}
              </Select>
              {availableFlows.length === 0 && (
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-1.5">
                  {t('settings.scheduleNoFlowsHint')}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="task-cron" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                {t('settings.cronLabel')}
              </label>
              <Input
                id="task-cron"
                value={taskFormCron}
                onChange={(e) => setTaskFormCron(e.target.value)}
                placeholder={t('settings.cronPlaceholder')}
                className="font-mono"
                autoComplete="off"
              />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
                {t('settings.cronHint')}
              </p>
            </div>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              {t('settings.scheduleDefaultActiveHint')}
            </p>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={handleCloseScheduleModal}>{t('common.cancel')}</Button>
          <Button
            onClick={() => void handleSaveScheduleTask()}
            loading={createCronJob.isPending || updateCronJob.isPending}
          >
            {editingTask ? t('common.save') : t('common.create')}
          </Button>
        </ModalFooter>
      </Modal>
    </PageShell>
  );
}

/* ── Extracted components (per rerender-memo) ── */

const HealthIcon = memo(function HealthIcon({ status }: { status: boolean | null }) {
  const { t } = useTranslation();
  if (status === true) return <CheckCircle2 className="w-4 h-4 text-mint-500" aria-label={t('settings.healthHealthy')} />;
  if (status === false) return <XCircle className="w-4 h-4 text-red-500 dark:text-red-400" aria-label={t('settings.healthUnhealthy')} />;
  return <Circle className="w-4 h-4 text-gray-300 dark:text-gray-600" aria-label={t('settings.healthUnknown')} />;
});

type ScheduleRowVisualStatus = 'active' | 'paused' | 'error';

function deriveRowStatus(task: CronJobInfo): ScheduleRowVisualStatus {
  if (task.status === 'failed' || task.status === 'disabled') return 'error';
  if (task.status === 'active' || task.status === 'running') return 'active';
  return 'paused';
}

function formatTaskRunTime(iso: string | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

const ScheduleTaskRow = memo(function ScheduleTaskRow({
  task,
  busy,
  onToggle,
  onRun,
  onEdit,
  onDelete,
}: {
  task: CronJobInfo;
  busy: boolean;
  onToggle: (task: CronJobInfo) => void;
  onRun: (task: CronJobInfo) => void;
  onEdit: (task: CronJobInfo) => void;
  onDelete: (task: CronJobInfo) => void;
}) {
  const { t } = useTranslation();
  const statusStyles = {
    active: {
      border: 'border-mint-200 dark:border-mint-900/50 bg-mint-50/40 dark:bg-mint-900/10',
      iconBg: 'bg-mint-100 dark:bg-mint-900/30',
      icon: <Play className="w-4.5 h-4.5 text-mint-600 dark:text-mint-400" aria-hidden="true" />,
      badge: 'success' as const,
      labelKey: 'settings.taskStatusRunning' as const,
    },
    error: {
      border: 'border-red-200 dark:border-red-900/50 bg-red-50/40 dark:bg-red-900/10',
      iconBg: 'bg-red-100 dark:bg-red-900/30',
      icon: <AlertCircle className="w-4.5 h-4.5 text-red-600 dark:text-red-400" aria-hidden="true" />,
      badge: 'error' as const,
      labelKey: 'settings.taskStatusError' as const,
    },
    paused: {
      border: 'border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-surface/40',
      iconBg: 'bg-gray-100 dark:bg-surface',
      icon: <Pause className="w-4.5 h-4.5 text-gray-500 dark:text-gray-400" aria-hidden="true" />,
      badge: 'default' as const,
      labelKey: 'settings.taskStatusPaused' as const,
    },
  };

  const visualStatus = deriveRowStatus(task);
  const s = statusStyles[visualStatus];
  const taskName = task.name;
  const isRunningEnabled = task.status === 'active' || task.status === 'running';

  return (
    <div className={cn('flex items-center justify-between p-4 rounded-xl border transition-colors', s.border)}>
      <div className="flex items-center gap-3.5 min-w-0">
        <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0', s.iconBg)}>
          {s.icon}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{taskName}</p>
            <Badge variant={s.badge} size="sm">{t(s.labelKey)}</Badge>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 flex items-center gap-1.5">
            <span className="font-mono">{task.cron_expression}</span>
            {task.run_count > 0 && (
              <>
                <span className="text-gray-300 dark:text-gray-600">·</span>
                <span>{t('settings.scheduleRunCount', { count: task.run_count })}</span>
              </>
            )}
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            {t('settings.nextRunPrefix')}: {formatTaskRunTime(task.next_run_at)}
            {task.last_run_at && ` · ${t('settings.lastRunPrefix')}: ${formatTaskRunTime(task.last_run_at)}`}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-1 flex-shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onRun(task)}
          disabled={busy}
          aria-label={t('settings.ariaRunTask', { name: taskName })}
          title={t('settings.scheduleRunNow')}
        >
          <Zap className="w-3.5 h-3.5" aria-hidden="true" />
        </Button>
        <Button variant="ghost" size="sm" onClick={() => onEdit(task)} disabled={busy} aria-label={t('settings.ariaEditTask', { name: taskName })}>
          <Edit2 className="w-3.5 h-3.5" aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onToggle(task)}
          disabled={busy}
          aria-label={t('settings.ariaToggleTask', { name: taskName })}
        >
          {isRunningEnabled ? (
            <Pause className="w-3.5 h-3.5" aria-hidden="true" />
          ) : (
            <Play className="w-3.5 h-3.5" aria-hidden="true" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
          onClick={() => onDelete(task)}
          disabled={busy}
          aria-label={t('settings.ariaDeleteTask', { name: taskName })}
        >
          <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
});
