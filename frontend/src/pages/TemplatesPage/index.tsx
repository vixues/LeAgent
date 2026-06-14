import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  LayoutTemplate,
  Search,
  ArrowRight,
  Tag,
  GitBranch,
  Sparkles,
  Grid3x3,
  List,
  RefreshCw,
  ChevronRight,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { PageShell } from '@/components/layout/PageShell';
import { Input } from '@/components/ui';
import { EmptyState } from '@/components/common/EmptyState';
import { CategoryFilter } from '@/components/common/CategoryFilter';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toaster';
import {
  CategoryIconBadge,
  CategoryInlineIcon,
} from '@/lib/categoryIcons';
import {
  useTemplates,
  useTemplateCategories,
  useApplyTemplate,
  type TemplateCategory,
  type TemplateListItem,
} from '@/controllers/API/queries/templates';
import { WorkflowMiniGraphPreview } from '@/features/workflow/components/WorkflowMiniGraphPreview';
import type { FlowEdge, FlowNode } from '@/stores/flow';

const CATEGORY_COLORS: Record<string, string> = {
  finance: 'bg-peach-50 dark:bg-peach-900/20 text-peach-700 dark:text-peach-300 border-peach-200 dark:border-peach-800',
  productivity: 'bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800',
  hr: 'bg-blue-50 dark:bg-blue-900/20 text-blue-800 dark:text-blue-300 border-blue-200 dark:border-blue-800',
  procurement: 'bg-mint-50 dark:bg-mint-900/20 text-mint-700 dark:text-mint-300 border-mint-200 dark:border-mint-800',
  compliance: 'bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
  customer: 'bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800',
  customer_service: 'bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800',
  data: 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300 border-primary-200 dark:border-primary-800',
  data_management: 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300 border-primary-200 dark:border-primary-800',
  approval: 'bg-mint-50 dark:bg-mint-900/20 text-mint-700 dark:text-mint-300 border-mint-200 dark:border-mint-800',
  document: 'bg-peach-50 dark:bg-peach-900/20 text-peach-700 dark:text-peach-300 border-peach-200 dark:border-peach-800',
  document_management: 'bg-peach-50 dark:bg-peach-900/20 text-peach-700 dark:text-peach-300 border-peach-200 dark:border-peach-800',
  communication: 'bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800',
  legal: 'bg-surface-sunken text-muted-foreground border-border',
  analytics: 'bg-sky-100 dark:bg-sky-900/30 text-sky-900 dark:text-sky-200 border-sky-300 dark:border-sky-700',
  quality: 'bg-mint-50 dark:bg-mint-900/20 text-mint-700 dark:text-mint-300 border-mint-200 dark:border-mint-800',
  inventory: 'bg-mint-100 dark:bg-mint-900/30 text-mint-800 dark:text-mint-200 border-mint-300 dark:border-mint-700',
  audit: 'bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
  general: 'bg-surface-sunken text-muted-foreground border-border',
  game: 'bg-violet-50 dark:bg-violet-900/20 text-violet-700 dark:text-violet-300 border-violet-200 dark:border-violet-800',
};

function TemplateCard({
  template,
  onApply,
  isApplying,
}: {
  template: TemplateListItem;
  onApply: (t: TemplateListItem) => void;
  isApplying: boolean;
}) {
  const { t } = useTranslation();
  const colorClass = CATEGORY_COLORS[template.category] || CATEGORY_COLORS.general;

  return (
    <div className="group relative bg-surface rounded-xl border border-border hover:border-primary-300 dark:hover:border-primary-700 hover:shadow-lg transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-200 overflow-hidden flex flex-col">
      <div className="p-5 flex-1 flex flex-col">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <CategoryIconBadge categoryId={template.category} size="md" />
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-foreground truncate">
                {template.name}
              </h3>
              <span className={cn('inline-flex items-center text-[11px] font-medium px-1.5 py-0.5 rounded-full border mt-1', colorClass)}>
                {template.category_label}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground-tertiary flex-shrink-0">
            <GitBranch className="w-3 h-3" />
            <span>{template.node_count}</span>
          </div>
        </div>

        <WorkflowMiniGraphPreview
          previewUi={
            template.preview_ui
              ? {
                  nodes: template.preview_ui.nodes as FlowNode[] | undefined,
                  edges: template.preview_ui.edges as FlowEdge[] | undefined,
                }
              : null
          }
          variant="card"
          className="mb-3"
        />

        <p className="text-xs text-muted-foreground line-clamp-2 mb-4 flex-1">
          {template.description || t('templates.noDescription')}
        </p>

        {template.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-4">
            {template.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-0.5 text-[11px] px-1.5 py-0.5 rounded bg-surface-sunken text-muted-foreground"
              >
                <Tag className="w-2.5 h-2.5" />
                {tag}
              </span>
            ))}
            {template.tags.length > 3 && (
              <span className="text-[11px] text-muted-foreground-tertiary">
                +{template.tags.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="px-5 pb-4">
        <button
          onClick={() => onApply(template)}
          disabled={isApplying}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium rounded-lg bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors disabled:opacity-50"
        >
          {isApplying ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              {t('templates.creating')}
            </>
          ) : (
            <>
              <Sparkles className="w-3.5 h-3.5" />
              {t('templates.useTemplate')}
              <ArrowRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function TemplateRow({
  template,
  onApply,
  isApplying,
}: {
  template: TemplateListItem;
  onApply: (t: TemplateListItem) => void;
  isApplying: boolean;
}) {
  const { t } = useTranslation();
  const colorClass = CATEGORY_COLORS[template.category] || CATEGORY_COLORS.general;

  return (
    <div className="group flex items-center gap-4 p-4 bg-surface rounded-lg border border-border hover:border-primary-300 dark:hover:border-primary-700 hover:shadow-md transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-200">
      <CategoryIconBadge categoryId={template.category} size="md" />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <h3 className="text-base font-semibold text-foreground truncate">
            {template.name}
          </h3>
          <span className={cn('inline-flex items-center text-[11px] font-medium px-1.5 py-0.5 rounded-full border', colorClass)}>
            {template.category_label}
          </span>
        </div>
        <p className="text-xs text-muted-foreground truncate">
          {template.description}
        </p>
      </div>

      <div className="flex items-center gap-4 flex-shrink-0">
        <div className="flex items-center gap-1 text-xs text-muted-foreground-tertiary">
          <GitBranch className="w-3 h-3" />
          <span>{t('templates.nodesCount', { count: template.node_count })}</span>
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground-tertiary">
          <Tag className="w-3 h-3" />
          <span>{t('templates.tagsCount', { count: template.tags.length })}</span>
        </div>
        <button
          onClick={() => onApply(template)}
          disabled={isApplying}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors disabled:opacity-50"
        >
          {isApplying ? (
            <RefreshCw className="w-3 h-3 animate-spin" />
          ) : (
            <>
              <Sparkles className="w-3 h-3" />
              {t('templates.use')}
              <ChevronRight className="w-3 h-3" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <div className="p-5 pb-3">
        <div className="flex items-start gap-2.5 mb-3">
          <Skeleton className="w-8 h-8 rounded-lg" />
          <div className="flex-1">
            <Skeleton className="w-3/4 h-4 mb-1.5" />
            <Skeleton className="w-16 h-4 rounded-full" />
          </div>
        </div>
        <Skeleton className="w-full h-[148px] rounded-lg mb-3" />
        <Skeleton className="w-full h-3 mb-1.5" />
        <Skeleton className="w-2/3 h-3 mb-4" />
        <div className="flex gap-1">
          <Skeleton className="w-12 h-4 rounded" />
          <Skeleton className="w-14 h-4 rounded" />
        </div>
      </div>
      <div className="px-5 pb-4">
        <Skeleton className="w-full h-9 rounded-lg" />
      </div>
    </div>
  );
}

export default function TemplatesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>();
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [applyingId, setApplyingId] = useState<string | null>(null);

  const { data: templatesData, isLoading: templatesLoading, error: templatesError } = useTemplates(
    selectedCategory,
    search || undefined,
  );
  const { data: categoriesData } = useTemplateCategories();
  const applyMutation = useApplyTemplate();

  const templates: TemplateListItem[] = templatesData?.templates ?? [];
  const categories: TemplateCategory[] = categoriesData?.categories ?? [];
  const totalCount = templatesData?.total ?? 0;

  const handleApply = async (template: TemplateListItem) => {
    setApplyingId(template.id);
    try {
      const result = await applyMutation.mutateAsync({
        templateId: template.id,
        body: {},
      });
      toast({
        variant: 'success',
        title: t('templates.toastCreated'),
        description: result.message,
      });
      const flowId =
        typeof result.flow_id === 'string' ? result.flow_id : String(result.flow_id ?? '');
      if (flowId) {
        navigate(`/workflows/${flowId}`);
      }
    } catch {
      toast({
        variant: 'error',
        title: t('templates.toastFailedTitle'),
        description: t('templates.toastFailedDesc'),
      });
    } finally {
      setApplyingId(null);
    }
  };

  return (
    <PageShell
      title={t('templates.pageTitle')}
      description={t('templates.pageDescription', { count: totalCount })}
      icon={<LayoutTemplate className="w-5 h-5" />}
    >
        <p className="text-xs text-muted-foreground -mt-4 mb-2 max-w-3xl">
          {t('templates.galleryHint')}
        </p>

        {/* Category pills + Search */}
        <div className="flex items-center gap-3">
          <CategoryFilter
            aria-label={t('templates.allCategories')}
            value={selectedCategory}
            onChange={setSelectedCategory}
            allItem={{
              label: t('templates.allCategories'),
              count: categories.reduce((sum, c) => sum + (c.count ?? 0), 0) || totalCount,
            }}
            items={categories.map((cat) => ({
              id: cat.id,
              label: cat.label,
              icon: <CategoryInlineIcon categoryId={cat.id} />,
              count: cat.count,
            }))}
          />

          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="relative">
              <Input
                type="text"
                placeholder={t('templates.searchPlaceholder')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                leftIcon={<Search className="w-3.5 h-3.5" />}
                className="w-48 text-xs py-1.5"
              />
              {search && (
                <button
                  onClick={() => setSearch('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground-tertiary hover:text-foreground"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
            <div className="flex items-center bg-surface-sunken rounded-lg p-0.5">
              <button
                onClick={() => setViewMode('grid')}
                className={cn(
                  'p-1.5 rounded-md transition-colors',
                  viewMode === 'grid'
                    ? 'bg-surface-elevated shadow-sm text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <Grid3x3 className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={cn(
                  'p-1.5 rounded-md transition-colors',
                  viewMode === 'list'
                    ? 'bg-surface-elevated shadow-sm text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <List className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

      {templatesLoading ? (
          viewMode === 'grid' ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {Array.from({ length: 8 }).map((_, i) => (
                <CardSkeleton key={i} />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="w-full h-16 rounded-lg" />
              ))}
            </div>
          )
        ) : templatesError ? (
          <EmptyState
            type="error"
            title={t('templates.loadErrorTitle')}
            description={t('templates.loadErrorDesc')}
          />
        ) : templates.length === 0 ? (
          <EmptyState
            type={search || selectedCategory ? 'search' : 'default'}
            title={
              search || selectedCategory
                ? t('templates.emptyNoMatch')
                : t('templates.emptyNone')
            }
            description={
              search || selectedCategory
                ? t('templates.emptyNoMatchHint')
                : t('templates.emptyNoneHint')
            }
            action={
              (search || selectedCategory)
                ? {
                    label: t('templates.clearFilters'),
                    onClick: () => {
                      setSearch('');
                      setSelectedCategory(undefined);
                    },
                  }
                : undefined
            }
          />
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {templates.map((t) => (
              <TemplateCard
                key={t.id}
                template={t}
                onApply={handleApply}
                isApplying={applyingId === t.id}
              />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {templates.map((t) => (
              <TemplateRow
                key={t.id}
                template={t}
                onApply={handleApply}
                isApplying={applyingId === t.id}
              />
            ))}
          </div>
        )}
    </PageShell>
  );
}
