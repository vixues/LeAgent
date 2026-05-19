import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Check,
  Download,
  ExternalLink,
  FileText,
  Link2,
  Package,
  Puzzle,
  Pencil,
  RefreshCw,
  Store,
} from 'lucide-react';
import { PageShell } from '@/components/layout/PageShell';
import { PageLoader } from '@/components/common/PageLoader';
import { EmptyState } from '@/components/common/EmptyState';
import { SearchInput } from '@/components/common/SearchInput';
import { Markdown } from '@/components/chat/markdown/Markdown';
import {
  Badge,
  Button,
  Card,
  CardContent,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Switch,
  Input,
} from '@/components/ui';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { useToast } from '@/components/ui/Toaster';
import {
  useActivateSkill,
  useDeactivateSkill,
  useInstallSkill,
  useInstallSkillFromUrl,
  useSkillBody,
  useSkillDetail,
  useSkillFile,
  useSkillHubSearch,
  useSkillResourceContent,
  useSkillsList,
  useUpdateSkillFile,
  type SkillDetail,
  type SkillHubCatalogParams,
  type SkillHubItem,
  type SkillInfo,
} from '@/hooks/useSkills';
import { parseGitHubSkillsRepoUrl, type ParsedGitHubSkillsRepo } from '@/lib/parseGitHubRepoUrl';
import { cn } from '@/lib/utils';

const SKILLS_HUB_CATALOG_STORAGE_KEY = 'leagent.skills.hubCatalogRepoUrl';
const DEFAULT_SKILLS_CATALOG_REPO_URL = 'https://github.com/anthropics/skills';

function toHubCatalogParams(p: ParsedGitHubSkillsRepo): SkillHubCatalogParams {
  return {
    gh_owner: p.owner,
    gh_repo: p.repo,
    gh_ref: p.ref,
    gh_skills_path: p.skillsPath,
  };
}

type DetailTab = 'overview' | 'content' | 'resources' | 'edit';

function SkillDetailModalContent({
  detailName,
  skillDetail,
  detailLoading,
  detailTab,
  onTabChange,
}: {
  detailName: string;
  skillDetail: SkillDetail | undefined;
  detailLoading: boolean;
  detailTab: DetailTab;
  onTabChange: (t: DetailTab) => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();

  const { data: bodyData, isLoading: bodyLoading } = useSkillBody(detailName);
  const {
    data: fileData,
    isLoading: fileLoading,
    refetch: refetchFile,
  } = useSkillFile(detailTab === 'edit' ? detailName : undefined);
  const updateFile = useUpdateSkillFile();

  const [editDraft, setEditDraft] = useState('');
  const [editDirty, setEditDirty] = useState(false);
  const [resourcePreview, setResourcePreview] = useState<string | null>(null);

  const { data: resPayload, isLoading: resLoading } = useSkillResourceContent(
    resourcePreview ? detailName : undefined,
    resourcePreview ?? undefined
  );

  useEffect(() => {
    if (detailTab === 'edit' && fileData?.content != null && !editDirty) {
      setEditDraft(fileData.content);
    }
  }, [detailTab, fileData, editDirty, detailName]);

  const handleSaveEdit = async () => {
    try {
      await updateFile.mutateAsync({ name: detailName, content: editDraft });
      setEditDirty(false);
      await refetchFile();
      toast({
        variant: 'success',
        title: t('skills.saveSuccess'),
        description: detailName,
      });
    } catch (e) {
      toast({
        variant: 'error',
        title: t('common.error'),
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const handleDiscardEdit = useCallback(() => {
    if (fileData?.content != null) {
      setEditDraft(fileData.content);
      setEditDirty(false);
    }
  }, [fileData?.content]);

  if (detailLoading) {
    return (
      <div className="flex justify-center py-8">
        <PageLoader size="sm" message={t('common.loading')} />
      </div>
    );
  }

  if (!skillDetail) {
    return <p className="text-sm text-muted-foreground">{t('skills.detailEmpty')}</p>;
  }

  const editable = Boolean(skillDetail.is_editable);

  return (
    <>
      <div className="border-b border-border -mx-6 -mt-1 px-1 pb-3 mb-5">
        <div className="flex flex-wrap gap-2 min-h-[2.25rem] items-center">
          {(['overview', 'content', 'resources', 'edit'] as const).map((tab) => {
            if (tab === 'edit' && !editable) return null;
            const icons = {
              overview: Package,
              content: FileText,
              resources: Puzzle,
              edit: Pencil,
            } as const;
            const Icon = icons[tab];
            return (
              <button
                key={tab}
                type="button"
                onClick={() => onTabChange(tab)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
                  detailTab === tab
                    ? 'bg-primary-500/15 text-foreground'
                    : 'text-muted-foreground hover:bg-surface-sunken hover:text-foreground'
                )}
              >
                <Icon className="w-4 h-4 shrink-0" aria-hidden />
                {tab === 'overview' && t('skills.tabOverview')}
                {tab === 'content' && t('skills.tabContent')}
                {tab === 'resources' && t('skills.tabResources')}
                {tab === 'edit' && t('skills.tabEdit')}
              </button>
            );
          })}
        </div>
      </div>

      {detailTab === 'overview' && (
        <div className="space-y-5 text-sm max-h-[min(60vh,560px)] overflow-y-auto pr-2 leading-relaxed">
          <div className="flex flex-wrap gap-2">
            <Badge variant={skillDetail.is_active ? 'success' : 'default'} size="sm">
              {skillDetail.is_active ? t('skills.statusActive') : t('skills.statusInactive')}
            </Badge>
            <Badge variant="default" size="sm">
              v{skillDetail.version}
            </Badge>
            <Badge variant="primary" size="sm">
              {skillDetail.category}
            </Badge>
            {skillDetail.display_name && skillDetail.display_name !== skillDetail.name && (
              <span className="text-muted-foreground w-full sm:w-auto sm:ml-1">
                {skillDetail.display_name}
              </span>
            )}
          </div>
          <p className="text-muted-foreground whitespace-pre-wrap">
            {skillDetail.description || '—'}
          </p>
          {skillDetail.author && (
            <p className="text-xs text-muted-foreground">
              {t('skills.author')}: {skillDetail.author}
            </p>
          )}
          {skillDetail.license && (
            <p className="text-xs text-muted-foreground">
              {t('skills.license')}: {skillDetail.license}
            </p>
          )}
          {skillDetail.compatibility && (
            <p className="text-xs text-muted-foreground">
              {t('skills.compatibility')}: {skillDetail.compatibility}
            </p>
          )}
          {skillDetail.allowed_tools && skillDetail.allowed_tools.length > 0 && (
            <div>
              <p className="text-sm font-medium text-foreground mb-1.5">{t('skills.allowedTools')}</p>
              <ul className="list-disc list-inside text-muted-foreground space-y-0.5">
                {skillDetail.allowed_tools.map((tool) => (
                  <li key={tool}>{tool}</li>
                ))}
              </ul>
            </div>
          )}
          {skillDetail.metadata && Object.keys(skillDetail.metadata).length > 0 && (
            <div>
              <p className="text-sm font-medium text-foreground mb-1.5">{t('skills.metadata')}</p>
              <pre className="text-xs bg-surface-sunken dark:bg-surface-elevated rounded-lg p-3 overflow-x-auto text-muted-foreground max-h-48 overflow-y-auto">
                {JSON.stringify(skillDetail.metadata, null, 2)}
              </pre>
            </div>
          )}
          {!editable && <p className="text-xs text-amber-600 dark:text-amber-400">{t('skills.readOnlyHint')}</p>}
          {skillDetail.error && (
            <p className="text-sm text-red-600 dark:text-red-400">{skillDetail.error}</p>
          )}
        </div>
      )}

      {detailTab === 'content' && (
        <div className="min-h-[160px] max-h-[min(62vh,600px)] overflow-y-auto overflow-x-hidden rounded-xl border border-border/55 bg-gradient-to-b from-surface/90 to-surface/55 shadow-[inset_0_1px_0_0_hsla(0,0%,100%,0.06)] dark:from-surface/50 dark:to-surface/25 dark:shadow-none [scrollbar-gutter:stable] scroll-smooth">
          <div className="px-5 py-7 sm:px-10 sm:py-9">
            {bodyLoading ? (
              <div className="flex justify-center py-8">
                <PageLoader size="sm" message={t('common.loading')} />
              </div>
            ) : (
              <>
                {bodyData?.truncated ? (
                  <p className="mb-5 text-xs font-medium text-amber-700 dark:text-amber-400/95">
                    {t('skills.truncatedWarning')}
                  </p>
                ) : null}
                {bodyData?.body != null && bodyData.body !== '' ? (
                  <Markdown
                    content={bodyData.body}
                    variant="article"
                    className="skill-detail-markdown mx-auto max-w-[70ch] text-[15px] sm:text-base leading-relaxed"
                  />
                ) : !bodyLoading ? (
                  <p className="text-sm text-muted-foreground">{t('skills.noInstructionBody')}</p>
                ) : null}
              </>
            )}
          </div>
        </div>
      )}

      {detailTab === 'resources' && (
        <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1 text-sm">
          {skillDetail.resources && skillDetail.resources.length > 0 && (
            <div>
              <p className="text-sm font-medium text-foreground mb-2">{t('skills.bundledResources')}</p>
              <ul className="space-y-1.5">
                {skillDetail.resources.map((r) => (
                  <li key={r.path}>
                    <button
                      type="button"
                      className="text-left text-primary-600 dark:text-primary-400 hover:underline w-full"
                      onClick={() => setResourcePreview(r.path)}
                    >
                      {r.path}
                      <span className="text-muted-foreground text-xs ml-2">
                        ({r.kind}, {r.size} B)
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {skillDetail.scripts && skillDetail.scripts.length > 0 && (
            <div>
              <p className="text-sm font-medium text-foreground mb-2">{t('skills.bundledScripts')}</p>
              <ul className="list-disc list-inside text-muted-foreground space-y-1">
                {skillDetail.scripts.map((s) => (
                  <li key={s.path}>
                    <span className="font-mono text-xs">{s.path}</span>
                    {s.interpreter ? ` — ${s.interpreter}` : ''} ({s.size} B)
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(!skillDetail.resources?.length && !skillDetail.scripts?.length) && (
            <p className="text-muted-foreground">{t('skills.noBundledFiles')}</p>
          )}
        </div>
      )}

      {detailTab === 'edit' && editable && (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">{t('skills.skillFileEditorHint')}</p>
          {fileLoading ? (
            <div className="flex justify-center py-8">
              <PageLoader size="sm" message={t('common.loading')} />
            </div>
          ) : (
            <>
              {fileData?.truncated && (
                <p className="text-xs text-amber-600 dark:text-amber-400">{t('skills.truncatedFileWarning')}</p>
              )}
              <textarea
                value={editDraft}
                onChange={(e) => {
                  setEditDraft(e.target.value);
                  setEditDirty(true);
                }}
                spellCheck={false}
                className="w-full min-h-[min(50vh,28rem)] font-mono text-sm rounded-lg border border-border bg-background p-3 text-foreground focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  loading={updateFile.isPending}
                  disabled={!editDirty}
                  onClick={handleSaveEdit}
                >
                  {t('skills.saveSkill')}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={!editDirty}
                  onClick={handleDiscardEdit}
                >
                  {t('skills.discardEdits')}
                </Button>
              </div>
            </>
          )}
        </div>
      )}

      <Modal isOpen={resourcePreview != null} onClose={() => setResourcePreview(null)} size="lg">
        <ModalHeader onClose={() => setResourcePreview(null)}>{t('skills.previewResource')}</ModalHeader>
        <ModalBody>
          {resourcePreview && (
            <p className="text-xs font-mono text-muted-foreground mb-3 break-all">{resourcePreview}</p>
          )}
          {resLoading ? (
            <PageLoader size="sm" message={t('common.loading')} />
          ) : resPayload?.content != null && resPayload.content !== '' ? (
            <div className="max-h-[50vh] overflow-y-auto overflow-x-hidden rounded-xl border border-border/55 bg-gradient-to-b from-surface/90 to-surface/55 px-5 py-6 sm:px-8 dark:from-surface/45 dark:to-surface/20 [scrollbar-gutter:stable] scroll-smooth">
              <Markdown
                content={resPayload.content}
                variant="article"
                className="skill-detail-markdown mx-auto max-w-[70ch] text-[15px] sm:text-base leading-relaxed"
              />
            </div>
          ) : resPayload?.content_base64 ? (
            <p className="text-sm text-muted-foreground">{t('skills.binaryNoPreview')}</p>
          ) : (
            <p className="text-sm text-muted-foreground">{t('skills.previewEmpty')}</p>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="primary" onClick={() => setResourcePreview(null)}>
            {t('common.close')}
          </Button>
        </ModalFooter>
      </Modal>
    </>
  );
}

export default function SkillsPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<'installed' | 'hub' | 'installUrl'>('installed');
  const [hubQuery, setHubQuery] = useState('');
  const [hubSearchTerm, setHubSearchTerm] = useState('');
  const [catalogRepoUrlInput, setCatalogRepoUrlInput] = useState(() => {
    try {
      return localStorage.getItem(SKILLS_HUB_CATALOG_STORAGE_KEY) ?? DEFAULT_SKILLS_CATALOG_REPO_URL;
    } catch {
      return DEFAULT_SKILLS_CATALOG_REPO_URL;
    }
  });
  const [hubCatalogParams, setHubCatalogParams] = useState<SkillHubCatalogParams | null>(() => {
    try {
      const raw =
        localStorage.getItem(SKILLS_HUB_CATALOG_STORAGE_KEY) ?? DEFAULT_SKILLS_CATALOG_REPO_URL;
      const p = parseGitHubSkillsRepoUrl(raw);
      return p ? toHubCatalogParams(p) : null;
    } catch {
      return null;
    }
  });
  const [installUrl, setInstallUrl] = useState('');
  const [installSha, setInstallSha] = useState('');

  const [detailName, setDetailName] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>('overview');
  const detailOpen = detailName !== null;

  const { data: listData, isLoading: listLoading } = useSkillsList();
  const { data: hubData, isLoading: hubLoading } = useSkillHubSearch(
    hubSearchTerm,
    undefined,
    1,
    20,
    hubCatalogParams
  );

  const { data: skillDetail, isLoading: detailLoading } = useSkillDetail(detailName ?? undefined);

  const activateSkill = useActivateSkill();
  const deactivateSkill = useDeactivateSkill();
  const installSkill = useInstallSkill();
  const installFromUrl = useInstallSkillFromUrl();

  const busySkill = activateSkill.isPending
    ? activateSkill.variables?.name ?? null
    : deactivateSkill.isPending
      ? deactivateSkill.variables ?? null
      : installSkill.isPending
        ? installSkill.variables?.name ?? null
        : installFromUrl.isPending
          ? '__from_url__'
          : null;

  useEffect(() => {
    if (!detailName) {
      setDetailTab('overview');
    }
  }, [detailName]);

  const handleToggle = async (skill: SkillInfo, next: boolean) => {
    try {
      if (next) {
        await activateSkill.mutateAsync({ name: skill.name });
      } else {
        await deactivateSkill.mutateAsync(skill.name);
      }
    } catch (e) {
      toast({
        variant: 'error',
        title: t('common.error'),
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const handleInstall = async (item: SkillHubItem) => {
    try {
      await installSkill.mutateAsync({ name: item.name, catalog: hubCatalogParams });
      toast({
        variant: 'success',
        title: t('skills.installSuccess'),
        description: item.name,
      });
    } catch (e) {
      toast({
        variant: 'error',
        title: t('skills.installFailed'),
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const handleInstallFromUrl = async () => {
    const u = installUrl.trim();
    if (!u) {
      return;
    }
    try {
      const detail = await installFromUrl.mutateAsync({
        url: u,
        sha256: installSha.trim() || undefined,
      });
      setInstallUrl('');
      setInstallSha('');
      toast({
        variant: 'success',
        title: t('skills.installFromUrlSuccess'),
        description: detail.name,
      });
    } catch (e) {
      toast({
        variant: 'error',
        title: t('skills.installFromUrlFailed'),
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const installedSkills = listData?.skills ?? [];
  const installedSkillNames = useMemo(
    () => new Set(installedSkills.map((s) => s.name)),
    [installedSkills]
  );

  const handleApplyHubCatalog = useCallback(() => {
    const p = parseGitHubSkillsRepoUrl(catalogRepoUrlInput);
    if (!p) {
      toast({
        variant: 'error',
        title: t('common.error'),
        description: t('skills.hubCatalogInvalidUrl'),
      });
      return;
    }
    try {
      localStorage.setItem(SKILLS_HUB_CATALOG_STORAGE_KEY, catalogRepoUrlInput.trim());
    } catch {
      /* ignore */
    }
    setHubCatalogParams(toHubCatalogParams(p));
    void queryClient.invalidateQueries({ queryKey: ['skills', 'hub', 'search'] });
  }, [catalogRepoUrlInput, queryClient, t, toast]);

  return (
    <PageShell
      icon={<Puzzle className="w-5 h-5" aria-hidden />}
      title={t('skills.pageTitle')}
      description={t('skills.pageDescription')}
    >
      <Tabs
        defaultValue="installed"
        value={tab}
        onValueChange={(v) => setTab(v as 'installed' | 'hub' | 'installUrl')}
      >
        <TabsList className="mb-6">
            <TabsTrigger value="installed" className="gap-1.5">
              <Puzzle className="w-4 h-4" />
              {t('skills.tabInstalled')}
            </TabsTrigger>
            <TabsTrigger value="hub" className="gap-1.5">
              <Store className="w-4 h-4" />
              {t('skills.tabHub')}
            </TabsTrigger>
            <TabsTrigger value="installUrl" className="gap-1.5">
              <Link2 className="w-4 h-4" aria-hidden />
              {t('skills.tabInstallUrl')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="installed" className="mt-0">
            {listLoading ? (
              <div className="flex items-center justify-center py-16">
                <PageLoader size="md" message={t('common.loading')} />
              </div>
            ) : installedSkills.length === 0 ? (
              <EmptyState
                type="data"
                title={t('skills.emptyInstalled')}
                description={t('skills.emptyInstalledHint')}
              />
            ) : (
              <div className="grid auto-rows-fr gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {installedSkills.map((skill) => (
                  <Card
                    key={skill.name}
                    padding="none"
                    className={cn(
                      'flex h-full min-h-[12rem] flex-col overflow-hidden rounded-xl border border-border/70 bg-surface/95 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary-300/50 hover:shadow-md',
                      !skill.is_active && 'opacity-90'
                    )}
                  >
                    <CardContent padding="none" className="flex flex-1 flex-col gap-2.5 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="line-clamp-1 text-sm font-semibold text-foreground">
                          {skill.name}
                        </h3>
                        <Switch
                          size="sm"
                          checked={skill.is_active}
                          disabled={busySkill === skill.name}
                          onChange={(e) => handleToggle(skill, e.target.checked)}
                          aria-label={t('skills.toggleActive')}
                        />
                      </div>
                      <Badge
                        variant={skill.is_active ? 'success' : 'default'}
                        size="sm"
                        className="w-fit"
                      >
                        {skill.is_active
                          ? t('skills.statusActive')
                          : t('skills.statusInactive')}
                      </Badge>
                      <p className="line-clamp-2 min-h-10 flex-1 text-sm leading-5 text-muted-foreground">
                        {skill.description || '—'}
                      </p>
                      <div className="flex min-h-6 flex-wrap items-center gap-1.5">
                        <Badge variant="default" size="sm">
                          v{skill.version}
                        </Badge>
                        <Badge variant="primary" size="sm">
                          {skill.category}
                        </Badge>
                      </div>
                      {skill.tags && skill.tags.length > 0 && (
                        <div className="flex min-h-6 flex-wrap gap-1">
                          {skill.tags.slice(0, 4).map((tag) => (
                            <Badge key={tag} variant="default" size="sm">
                              {tag}
                            </Badge>
                          ))}
                          {skill.tags.length > 4 && (
                            <Badge variant="outline" size="sm">
                              +{skill.tags.length - 4}
                            </Badge>
                          )}
                        </div>
                      )}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="mt-auto h-8 w-full justify-center gap-1"
                        leftIcon={<ExternalLink className="w-4 h-4" />}
                        onClick={() => {
                          setDetailTab('overview');
                          setDetailName(skill.name);
                        }}
                      >
                        {t('skills.viewDetail')}
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="hub" className="mt-0 space-y-4">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:gap-4">
              <div className="min-w-0 flex-1 xl:max-w-md">
                <SearchInput
                  value={hubQuery}
                  onChange={setHubQuery}
                  onSearch={setHubSearchTerm}
                  debounceMs={300}
                  placeholder={t('skills.hubSearchPlaceholder')}
                  className="w-full"
                />
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-1.5 sm:flex-row sm:items-center xl:max-w-2xl">
                <label className="sr-only" htmlFor="skills-hub-catalog-url">
                  {t('skills.hubCatalogUrlLabel')}
                </label>
                <Input
                  id="skills-hub-catalog-url"
                  type="url"
                  autoComplete="off"
                  value={catalogRepoUrlInput}
                  onChange={(e) => setCatalogRepoUrlInput(e.target.value)}
                  placeholder={DEFAULT_SKILLS_CATALOG_REPO_URL}
                  className="h-10 w-full min-w-0 font-mono text-xs sm:flex-1"
                  aria-label={t('skills.hubCatalogUrlLabel')}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleApplyHubCatalog();
                    }
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-10 shrink-0 whitespace-nowrap border-primary-300 bg-primary-50 px-4 font-medium text-primary-700 hover:bg-primary-100 dark:border-primary-700 dark:bg-primary-900/25 dark:text-primary-300 dark:hover:bg-primary-900/40"
                  leftIcon={<RefreshCw className="h-4 w-4" aria-hidden />}
                  onClick={handleApplyHubCatalog}
                >
                  {t('skills.hubLoadCatalog')}
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground max-w-4xl">{t('skills.hubCatalogHint')}</p>

            {hubLoading ? (
              <div className="flex items-center justify-center py-16">
                <PageLoader size="md" message={t('common.loading')} />
              </div>
            ) : !hubData?.skills?.length ? (
              <EmptyState
                type="search"
                title={t('skills.hubEmpty')}
                description={t('skills.hubEmptyHint')}
              />
            ) : (
              <div className="grid auto-rows-fr gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {hubData.skills.map((item) => {
                  const alreadyInstalled = installedSkillNames.has(item.name);
                  return (
                    <Card
                      key={item.name}
                      padding="none"
                      className="flex h-full min-h-[12rem] flex-col overflow-hidden rounded-xl border border-border/70 bg-surface/95 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary-300/50 hover:shadow-md"
                    >
                      <CardContent padding="none" className="flex flex-1 flex-col gap-2.5 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <h3 className="line-clamp-1 text-sm font-semibold text-foreground">
                            {item.name}
                          </h3>
                          <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-1">
                            {alreadyInstalled && (
                              <Badge variant="success" size="sm">
                                {t('skills.hubInstalledBadge')}
                              </Badge>
                            )}
                            <Badge variant="primary" size="sm">
                              {item.category}
                            </Badge>
                          </div>
                        </div>
                        <p className="line-clamp-2 min-h-10 flex-1 text-sm leading-5 text-muted-foreground">
                          {item.description || '—'}
                        </p>
                        <div className="flex min-h-5 items-center gap-2 text-xs text-muted-foreground">
                          <span>v{item.version}</span>
                          {item.author != null && item.author !== '' && (
                            <span className="max-w-[10rem] truncate">{item.author}</span>
                          )}
                        </div>
                        <div className="flex min-h-6 flex-wrap gap-1 overflow-hidden">
                          {item.tags && item.tags.length > 0 && (
                            <>
                              {item.tags.slice(0, 4).map((tag) => (
                                <Badge key={tag} variant="default" size="sm">
                                  {tag}
                                </Badge>
                              ))}
                              {item.tags.length > 4 && (
                                <Badge variant="outline" size="sm">
                                  +{item.tags.length - 4}
                                </Badge>
                              )}
                            </>
                          )}
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className={cn(
                            'mt-auto h-8 w-full justify-center gap-2 px-3 font-medium transition-colors',
                            'focus:outline-none focus:ring-2 focus:ring-primary-500/25 focus:ring-offset-2 focus:ring-offset-background',
                            alreadyInstalled
                              ? 'cursor-default border border-border bg-muted/50 text-muted-foreground hover:bg-muted/50'
                              : 'border border-primary-200/70 bg-primary-50 text-primary-700 hover:bg-primary-100 dark:border-primary-800/50 dark:bg-primary-900/20 dark:text-primary-300 dark:hover:bg-primary-900/35'
                          )}
                          leftIcon={
                            alreadyInstalled ? (
                              <Check
                                className="h-4 w-4 text-emerald-600 dark:text-emerald-400"
                                aria-hidden
                              />
                            ) : (
                              <Download className="h-4 w-4" aria-hidden />
                            )
                          }
                          loading={busySkill === item.name && installSkill.isPending}
                          disabled={
                            alreadyInstalled ||
                            (busySkill !== null &&
                              busySkill !== item.name &&
                              busySkill !== '__from_url__') ||
                            installFromUrl.isPending
                          }
                          onClick={() => {
                            if (!alreadyInstalled) {
                              void handleInstall(item);
                            }
                          }}
                        >
                          {alreadyInstalled ? t('skills.hubInstalledBadge') : t('skills.install')}
                        </Button>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>

          <TabsContent value="installUrl" className="mt-0">
            <div className="rounded-xl border border-border/80 bg-surface/50 p-4 space-y-3 max-w-3xl">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Link2 className="w-4 h-4" aria-hidden />
                {t('skills.installFromUrlTitle')}
              </div>
              <p className="text-xs text-muted-foreground">{t('skills.installFromUrlHint')}</p>
              <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
                <div className="flex-1 min-w-0 space-y-2">
                  <Input
                    type="url"
                    autoComplete="off"
                    placeholder={t('skills.installFromUrlUrlPlaceholder')}
                    value={installUrl}
                    onChange={(e) => setInstallUrl(e.target.value)}
                    className="w-full"
                  />
                  <Input
                    type="text"
                    autoComplete="off"
                    placeholder={t('skills.installFromUrlShaPlaceholder')}
                    value={installSha}
                    onChange={(e) => setInstallSha(e.target.value)}
                    className="w-full font-mono text-sm"
                  />
                </div>
                <Button
                  type="button"
                  className="shrink-0"
                  leftIcon={<Link2 className="w-4 h-4" />}
                  loading={installFromUrl.isPending}
                  disabled={
                    !installUrl.trim() ||
                    (busySkill !== null && busySkill !== '__from_url__' && !installFromUrl.isPending)
                  }
                  onClick={handleInstallFromUrl}
                >
                  {t('skills.installFromUrlAction')}
                </Button>
              </div>
            </div>
          </TabsContent>
        </Tabs>

      <Modal
        isOpen={detailOpen}
        onClose={() => setDetailName(null)}
        size="2xl"
      >
        <ModalHeader onClose={() => setDetailName(null)}>
          {skillDetail?.display_name ?? detailName ?? t('skills.detailTitle')}
        </ModalHeader>
        <ModalBody className="space-y-0 px-6 py-5 sm:px-8 sm:py-6">
          {detailName && (
            <SkillDetailModalContent
              key={detailName}
              detailName={detailName}
              skillDetail={skillDetail}
              detailLoading={detailLoading}
              detailTab={detailTab}
              onTabChange={setDetailTab}
            />
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="primary" onClick={() => setDetailName(null)}>
            {t('common.close')}
          </Button>
        </ModalFooter>
      </Modal>
    </PageShell>
  );
}
