import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Search,
  Globe,
  FileText,
  Database,
  Sparkles,
  Plug,
  Wrench,
  Settings,
  Code,
  Clock,
  RotateCcw,
  Cpu,
  X,
  LayoutGrid,
  Workflow,
  BookOpen,
} from 'lucide-react';
import {
  Card,
  CardContent,
  Button,
  Input,
  Badge,
  Switch,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Textarea,
} from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import { useToolsStore } from '@/stores/tools';
import { useToolsList, useToolDetail, useToggleTool, useUpdateToolConfig } from '@/hooks/useTools';
import { cn } from '@/lib/utils';
import { PageLoader } from '@/components/common/PageLoader';
import type { ToolCategory } from '@/types/admin';

const CATEGORY_ICONS: Record<ToolCategory, typeof Globe> = {
  doc: FileText,
  web: Globe,
  data: Database,
  gen: Sparkles,
  integration: Plug,
  util: Wrench,
  canvas: LayoutGrid,
  workflow: Workflow,
  code: Code,
  skills: BookOpen,
};

const CATEGORY_COLORS: Record<ToolCategory, string> = {
  doc: 'bg-peach-100 dark:bg-peach-900/30 text-peach-600 dark:text-peach-400',
  web: 'bg-sky-100 dark:bg-sky-900/30 text-sky-600 dark:text-sky-400',
  data: 'bg-peach-100 dark:bg-peach-900/30 text-peach-600 dark:text-peach-400',
  gen: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
  integration: 'bg-mint-100 dark:bg-mint-900/30 text-mint-600 dark:text-mint-400',
  util: 'bg-gray-100 dark:bg-surface text-gray-600 dark:text-gray-400',
  canvas: 'bg-violet-100 dark:bg-violet-900/30 text-violet-600 dark:text-violet-400',
  workflow: 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400',
  code: 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300',
  skills: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400',
};

export default function ToolsPage() {
  const { t } = useTranslation();
  const {
    search,
    setSearch,
    selectedCategory,
    setSelectedCategory,
    selectedTool,
    setSelectedTool,
    isConfigModalOpen,
    setConfigModalOpen,
  } = useToolsStore();

  const { data: toolsData, isLoading } = useToolsList();
  const toggleTool = useToggleTool();
  const updateConfig = useUpdateToolConfig();

  const tools = toolsData?.tools;
  const backendCategories = toolsData?.categories;

  const { data: toolDetail } = useToolDetail(selectedTool?.name ?? null);

  const labelOf = (name: string) =>
    t(`tools.names.${name}`, { defaultValue: name.replace(/_/g, ' ') });
  const descOf = (name: string, fallback: string) =>
    t(`tools.descriptions.${name}`, { defaultValue: fallback });

  const [configJson, setConfigJson] = useState('');
  const [configError, setConfigError] = useState<string | null>(null);

  const categories: { value: ToolCategory | 'all'; label: string }[] = [
    { value: 'all', label: t('tools.allCategories') },
    { value: 'doc', label: t('tools.categories.doc') },
    { value: 'web', label: t('tools.categories.web') },
    { value: 'data', label: t('tools.categories.data') },
    { value: 'gen', label: t('tools.categories.gen') },
    { value: 'integration', label: t('tools.categories.integration') },
    { value: 'util', label: t('tools.categories.util') },
    { value: 'canvas', label: t('tools.categories.canvas') },
    { value: 'workflow', label: t('tools.categories.workflow') },
    { value: 'code', label: t('tools.categories.code') },
    { value: 'skills', label: t('tools.categories.skills') },
  ];

  const filteredTools = tools?.filter((tool) => {
    const q = search.toLowerCase();
    const matchesSearch =
      tool.name.toLowerCase().includes(q) ||
      tool.description.toLowerCase().includes(q) ||
      labelOf(tool.name).toLowerCase().includes(q) ||
      descOf(tool.name, tool.description).toLowerCase().includes(q);
    const matchesCategory = selectedCategory === 'all' || tool.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const handleToggle = async (id: string, enabled: boolean) => {
    await toggleTool.mutateAsync({ id, enabled });
  };

  const handleOpenConfig = (tool: typeof selectedTool) => {
    setSelectedTool(tool);
    setConfigJson(JSON.stringify(tool?.config || {}, null, 2));
    setConfigError(null);
    setConfigModalOpen(true);
  };

  const handleSaveConfig = async () => {
    if (!selectedTool) return;

    try {
      const config = JSON.parse(configJson);
      await updateConfig.mutateAsync({ id: selectedTool.id, config });
      setConfigModalOpen(false);
    } catch {
      setConfigError(t('admin.tool.invalidJson'));
    }
  };

  return (
    <PageShell
      title={t('tools.title')}
      description={t('tools.description')}
    >
      <div className="grid gap-6 lg:grid-cols-4">
        {/* Sidebar */}
        <div className="lg:col-span-1">
          <Card className="sticky top-8">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
              <h2 className="font-semibold text-gray-900 dark:text-white">
                {t('tools.categories.title')}
              </h2>
            </div>
            <CardContent padding="sm">
              <nav className="space-y-1">
                {categories.map((category) => {
                  const Icon =
                    category.value !== 'all' ? (CATEGORY_ICONS[category.value] ?? Wrench) : null;
                  const count =
                    category.value === 'all'
                      ? toolsData?.total ?? 0
                      : backendCategories?.[category.value] ?? 0;
                  const isActive = selectedCategory === category.value;

                  return (
                    <button
                      key={category.value}
                      onClick={() => setSelectedCategory(category.value)}
                      className={cn(
                        'w-full flex items-center justify-between px-3 py-2 rounded-lg text-left transition-colors',
                        isActive
                          ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                          : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                      )}
                    >
                      <div className="flex items-center gap-2">
                        {Icon && <Icon className="w-4 h-4" />}
                        <span className="text-sm">{category.label}</span>
                      </div>
                      <Badge variant={isActive ? 'primary' : 'default'} size="sm">
                        {count}
                      </Badge>
                    </button>
                  );
                })}
              </nav>
            </CardContent>
          </Card>
        </div>

        {/* Main content */}
        <div className="lg:col-span-3 space-y-4">
          <Input
            placeholder={t('tools.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            leftIcon={<Search className="w-4 h-4" />}
            className="w-full max-w-md"
          />

          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <PageLoader size="md" message={t('common.loading')} />
            </div>
          ) : filteredTools && filteredTools.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {filteredTools.map((tool) => {
                const Icon = CATEGORY_ICONS[tool.category] ?? Wrench;
                const colorClass = CATEGORY_COLORS[tool.category] ?? CATEGORY_COLORS.util;

                return (
                  <Card
                    key={tool.id}
                    className={cn(
                      'hover:shadow-md transition-[color,background-color,border-color,box-shadow,opacity,transform] cursor-pointer',
                      !tool.enabled && 'opacity-60',
                      selectedTool?.id === tool.id && 'ring-2 ring-primary-400 dark:ring-primary-600'
                    )}
                    onClick={() => setSelectedTool(tool)}
                  >
                    <CardContent>
                      <div className="flex items-start gap-3">
                        <div className={cn('p-2.5 rounded-xl', colorClass)}>
                          <Icon className="w-5 h-5" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                              {labelOf(tool.name)}
                            </h3>
                            <Switch
                              checked={tool.enabled}
                              onChange={(e) => {
                                e.stopPropagation();
                                handleToggle(tool.id, !tool.enabled);
                              }}
                            />
                          </div>
                          <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-2">
                            {descOf(tool.name, tool.description)}
                          </p>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <Badge variant="default" size="sm">
                              {t(`tools.categories.${tool.category}`)}
                            </Badge>
                            <Badge variant="default" size="sm" className="font-mono">
                              v{tool.version}
                            </Badge>
                            {tool.requires_gpu && (
                              <Badge variant="primary" size="sm" className="gap-0.5">
                                <Cpu className="w-2.5 h-2.5" />
                                GPU
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          ) : (
            <div className="p-12 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-surface flex items-center justify-center">
                <Code className="w-8 h-8 text-gray-400" />
              </div>
              <p className="text-gray-500 dark:text-gray-400">
                {search ? t('tools.noSearchResults') : t('admin.tool.empty')}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Tool detail panel */}
      {selectedTool && !isConfigModalOpen && (
        <div className="fixed bottom-8 right-8 left-8 lg:left-auto lg:w-[420px] z-30">
          <Card variant="elevated" className="shadow-lg border border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2 min-w-0">
                <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                  {labelOf(selectedTool.name)}
                </h3>
                <Badge variant="default" size="sm" className="font-mono flex-shrink-0">
                  v{selectedTool.version}
                </Badge>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setSelectedTool(null)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <CardContent className="max-h-80 overflow-auto space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {descOf(selectedTool.name, selectedTool.description)}
              </p>

              {/* Metadata grid */}
              <div className="grid grid-cols-3 gap-2">
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gray-50 dark:bg-surface">
                  <Clock className="w-3.5 h-3.5 text-gray-400" />
                  <span className="text-xs text-gray-600 dark:text-gray-400">{selectedTool.timeout_sec}s</span>
                </div>
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gray-50 dark:bg-surface">
                  <RotateCcw className="w-3.5 h-3.5 text-gray-400" />
                  <span className="text-xs text-gray-600 dark:text-gray-400">{selectedTool.max_retries} retries</span>
                </div>
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gray-50 dark:bg-surface">
                  <Cpu className="w-3.5 h-3.5 text-gray-400" />
                  <span className="text-xs text-gray-600 dark:text-gray-400">
                    {selectedTool.requires_gpu ? 'GPU' : 'CPU'}
                  </span>
                </div>
              </div>

              {/* Parameters schema from detail endpoint */}
              {toolDetail?.parameters && Object.keys(toolDetail.parameters).length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      {t('tools.schema')}
                    </p>
                    <Button
                      variant="ghost"
                      size="sm"
                      leftIcon={<Settings className="w-3 h-3" />}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenConfig(selectedTool);
                      }}
                    >
                      {t('admin.tool.configure')}
                    </Button>
                  </div>
                  <ParametersDisplay params={toolDetail.parameters} />
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <Modal isOpen={isConfigModalOpen} onClose={() => setConfigModalOpen(false)} size="lg">
        <ModalHeader onClose={() => setConfigModalOpen(false)}>
          {t('admin.tool.configureTitle', {
            name: selectedTool ? labelOf(selectedTool.name) : '',
          })}
        </ModalHeader>
        <ModalBody>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                {t('admin.tool.configJson')}
              </label>
              <Textarea
                value={configJson}
                onChange={(e) => {
                  setConfigJson(e.target.value);
                  setConfigError(null);
                }}
                rows={12}
                className="font-mono text-sm"
                error={configError || undefined}
              />
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setConfigModalOpen(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSaveConfig} loading={updateConfig.isPending}>
            {t('common.save')}
          </Button>
        </ModalFooter>
      </Modal>
    </PageShell>
  );
}

function ParametersDisplay({ params }: { params: Record<string, unknown> }) {
  const properties = (params.properties ?? {}) as Record<string, { type?: string; description?: string }>;
  const required = (params.required ?? []) as string[];
  const entries = Object.entries(properties);

  if (entries.length === 0) {
    return (
      <div className="p-3 rounded-lg bg-gray-50 dark:bg-surface">
        <pre className="text-xs text-gray-700 dark:text-gray-300 overflow-auto whitespace-pre-wrap">
          {JSON.stringify(params, null, 2)}
        </pre>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {entries.map(([name, prop]) => (
        <div
          key={name}
          className="flex items-start gap-2 px-3 py-2 rounded-lg bg-gray-50 dark:bg-surface"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <code className="text-xs font-semibold text-gray-800 dark:text-gray-200">{name}</code>
              {prop.type && (
                <span className="text-[10px] font-mono px-1 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
                  {prop.type}
                </span>
              )}
              {required.includes(name) && (
                <span className="text-[10px] font-medium text-rose-500">required</span>
              )}
            </div>
            {prop.description && (
              <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">
                {prop.description}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
