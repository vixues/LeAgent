import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowRight,
  BookOpen,
  ExternalLink,
  GitBranch,
  MessageSquare,
  Settings,
} from 'lucide-react';
import { Button, Card, CardContent } from '@/components/ui';
import { PageShell, PageSection } from '@/components/layout/PageShell';
import { cn } from '@/lib/utils';

const REPO_FALLBACK = 'https://github.com/your-org/leagent';

const featureRoutes = [
  { key: 'chat' as const, to: '/home', icon: MessageSquare },
  { key: 'workflows' as const, to: '/workflows', icon: GitBranch },
  { key: 'knowledge' as const, to: '/knowledge', icon: BookOpen },
  { key: 'settings' as const, to: '/settings', icon: Settings },
] as const;

const SYSTEM_IMPL_KEYS = [
  'executionTopology',
  'agentRuntime',
  'queryEngine',
  'gatedPrompts',
  'workflows',
  'memory',
  'tools',
  'fileCodeProject',
  'pauseResume',
  'genUiArt',
] as const;

const sectionIds = {
  systemIntro: 'docs-system-intro',
  systemImpl: 'docs-system-impl',
  overview: 'docs-overview',
  features: 'docs-features',
  quickStart: 'docs-quickstart',
  petDesk: 'docs-pet-desk',
} as const;

function DocsToc() {
  const { t } = useTranslation();
  const linkClass =
    'block border-l-2 border-transparent py-0.5 pl-3 text-sm text-muted-foreground transition-colors hover:border-primary-500/50 hover:text-foreground';
  return (
    <nav aria-label={t('docs.tocTitle')} className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground-tertiary">
        {t('docs.tocTitle')}
      </p>
      <ul className="space-y-0.5">
        <li>
          <a href={`#${sectionIds.systemIntro}`} className={linkClass}>
            {t('docs.tocSystemIntro')}
          </a>
        </li>
        <li>
          <a href={`#${sectionIds.systemImpl}`} className={linkClass}>
            {t('docs.tocSystemImpl')}
          </a>
        </li>
        <li>
          <a href={`#${sectionIds.overview}`} className={linkClass}>
            {t('docs.tocOverview')}
          </a>
        </li>
        <li>
          <a href={`#${sectionIds.features}`} className={linkClass}>
            {t('docs.tocFeatures')}
          </a>
        </li>
        <li>
          <a href={`#${sectionIds.quickStart}`} className={linkClass}>
            {t('docs.tocQuickStart')}
          </a>
        </li>
        <li>
          <a href={`#${sectionIds.petDesk}`} className={linkClass}>
            {t('docs.tocPetDesk')}
          </a>
        </li>
      </ul>
    </nav>
  );
}

export default function DocsPage() {
  const { t, i18n } = useTranslation();
  const raw = import.meta.env.VITE_LEAGENT_REPO_URL as string | undefined;
  const repoUrl = raw?.trim() || REPO_FALLBACK;

  const openRepo = () => {
    window.open(repoUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <PageShell
      title={t('docs.title')}
      description={t('docs.tagline')}
      actions={
        <Button
          variant="outline"
          size="sm"
          onClick={openRepo}
          leftIcon={<ExternalLink className="w-4 h-4" />}
        >
          {t('docs.viewOnGithub')}
        </Button>
      }
    >
      <div
        className={cn(
          'flex w-full min-w-0 flex-col',
          'xl:grid xl:grid-cols-12 xl:items-start xl:gap-10',
          'gap-8'
        )}
      >
        <aside
          className="hidden w-full min-w-0 shrink-0 xl:sticky xl:top-4 xl:col-span-3 xl:block"
          lang={i18n.resolvedLanguage}
        >
          <DocsToc />
        </aside>

        <div className="min-w-0 space-y-10 xl:col-span-9" lang={i18n.resolvedLanguage}>
          <div id={sectionIds.systemIntro} className="scroll-mt-20">
            <PageSection title={t('docs.sections.systemIntro.title')}>
              <div className="max-w-3xl space-y-6">
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {t('docs.sections.systemIntro.lead')}
                </p>
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    {t('docs.sections.systemIntro.subPositioningTitle')}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {t('docs.sections.systemIntro.subPositioningBody')}
                  </p>
                </div>
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    {t('docs.sections.systemIntro.subArchitectureTitle')}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {t('docs.sections.systemIntro.subArchitectureBody')}
                  </p>
                </div>
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    {t('docs.sections.systemIntro.subScenariosTitle')}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {t('docs.sections.systemIntro.subScenariosBody')}
                  </p>
                </div>
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    {t('docs.sections.systemIntro.subExtensibilityTitle')}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {t('docs.sections.systemIntro.subExtensibilityBody')}
                  </p>
                </div>
              </div>
            </PageSection>
          </div>

          <div id={sectionIds.systemImpl} className="scroll-mt-20">
            <PageSection title={t('docs.sections.systemImpl.title')}>
              <div className="max-w-3xl space-y-6">
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {t('docs.sections.systemImpl.lead')}
                </p>
                {SYSTEM_IMPL_KEYS.map((key) => (
                  <div key={key}>
                    <h3 className="text-base font-semibold text-foreground">
                      {t(`docs.sections.systemImpl.items.${key}.title`)}
                    </h3>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {t(`docs.sections.systemImpl.items.${key}.body`)}
                    </p>
                    <p className="mt-1.5 font-mono text-xs text-muted-foreground-tertiary">
                      {t(`docs.sections.systemImpl.items.${key}.codeHint`)}
                    </p>
                  </div>
                ))}
              </div>
            </PageSection>
          </div>

          <div id={sectionIds.overview} className="scroll-mt-20">
            <PageSection title={t('docs.sections.overview.title')}>
              <div className="prose prose-sm max-w-3xl dark:prose-invert prose-p:leading-relaxed">
                <p className="text-muted-foreground">{t('docs.sections.overview.p1')}</p>
                <p className="text-muted-foreground">{t('docs.sections.overview.p2')}</p>
                <p className="text-muted-foreground">{t('docs.sections.overview.p3')}</p>
              </div>
            </PageSection>
          </div>

          <div id={sectionIds.features} className="scroll-mt-20">
            <PageSection title={t('docs.sections.features.title')}>
              <div className="grid gap-4 sm:grid-cols-2" role="list">
                {featureRoutes.map(({ key, to, icon: Icon }) => (
                  <div key={key} className="min-w-0" role="listitem">
                    <Link to={to} className="group block h-full outline-none">
                      <Card
                        className={cn(
                          'h-full border-border transition-all duration-200',
                          'hover:border-primary-500/30 hover:shadow-md',
                          'group-focus-visible:ring-2 group-focus-visible:ring-primary-500/30 group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-background'
                        )}
                      >
                        <CardContent className="flex h-full min-h-[8.5rem] flex-col p-5">
                          <div className="mb-3 flex items-start justify-between gap-2">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-50 dark:bg-primary-900/30">
                              <Icon className="h-5 w-5 text-primary-600 dark:text-primary-400" />
                            </div>
                            <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground-tertiary transition-transform group-hover:translate-x-0.5 group-hover:text-primary-500" />
                          </div>
                          <h3 className="text-base font-semibold text-foreground">
                            {t(`docs.features.${key}.title`)}
                          </h3>
                          <p className="mt-1.5 flex-1 text-sm leading-relaxed text-muted-foreground">
                            {t(`docs.features.${key}.description`)}
                          </p>
                          <span className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary-600 dark:text-primary-400">
                            {t(`docs.features.${key}.cta`)}
                            <ArrowRight className="h-3.5 w-3.5" />
                          </span>
                        </CardContent>
                      </Card>
                    </Link>
                  </div>
                ))}
              </div>
            </PageSection>
          </div>

          <div id={sectionIds.quickStart} className="scroll-mt-20">
            <PageSection title={t('docs.sections.quickStart.title')}>
              <div className="rounded-xl border border-border bg-surface-elevated/50 p-6 sm:p-8">
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {t('docs.sections.quickStart.intro')}
                </p>
                <ul className="mt-4 list-inside list-disc space-y-2 text-sm text-muted-foreground marker:text-primary-500/80">
                  <li className="pl-0.5">{t('docs.sections.quickStart.item1')}</li>
                  <li className="pl-0.5">{t('docs.sections.quickStart.item2')}</li>
                  <li className="pl-0.5">{t('docs.sections.quickStart.item3')}</li>
                  <li className="pl-0.5">{t('docs.sections.quickStart.item4')}</li>
                </ul>
                <p className="mt-6 text-xs leading-relaxed text-muted-foreground-tertiary">
                  {t('docs.links.repoHint')}
                </p>
              </div>
            </PageSection>
          </div>

          <div id={sectionIds.petDesk} className="scroll-mt-20">
            <PageSection title={t('docs.sections.petDesk.title')}>
              <div className="max-w-3xl space-y-4">
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {t('docs.sections.petDesk.lead')}
                </p>
                <p className="text-sm leading-relaxed text-muted-foreground whitespace-pre-line">
                  {t('docs.sections.petDesk.spec')}
                </p>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4 pt-1">
                  <Link
                    to="/pet-space"
                    className={cn(
                      'inline-flex w-fit items-center justify-center gap-2 rounded-lg font-medium transition-colors duration-200 text-xs px-3 py-1.5',
                      'focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-background',
                      'border border-border bg-transparent text-foreground hover:bg-surface-sunken dark:hover:bg-surface-elevated',
                    )}
                  >
                    {t('docs.sections.petDesk.cta')}
                  </Link>
                  <p className="text-xs leading-relaxed text-muted-foreground-tertiary">
                    {t('docs.sections.petDesk.ctaHint')}
                  </p>
                </div>
              </div>
            </PageSection>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
