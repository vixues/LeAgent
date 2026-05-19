import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Globe,
  FileText,
  Database,
  Sparkles,
  Plug,
  Wrench,
  Clock,
  RotateCcw,
  Cpu,
  Code,
  LayoutGrid,
  Workflow,
  BookOpen,
} from 'lucide-react';
import {
  Card,
  Button,
  Select,
  Switch,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Badge,
  Textarea,
} from '@/components/ui';
import { useAdminStore } from '@/stores/admin';
import { useTools, useToggleTool, useUpdateToolConfig } from '@/hooks/useAdmin';
import type { Tool, ToolCategory } from '@/types/admin';

const CATEGORY_LABELS: Record<ToolCategory, string> = {
  doc: 'Document',
  web: 'Web',
  data: 'Data',
  gen: 'Generation',
  integration: 'Integration',
  util: 'Utility',
  canvas: 'Canvas',
  workflow: 'Workflow',
  code: 'Code',
  skills: 'Skills',
};

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

export function ToolManagement() {
  const { t } = useTranslation();
  const { data: tools, isLoading } = useTools();
  const toggleTool = useToggleTool();
  const updateConfig = useUpdateToolConfig();

  const {
    selectedTool,
    setSelectedTool,
    isToolConfigModalOpen,
    setToolConfigModalOpen,
  } = useAdminStore();

  const [configJson, setConfigJson] = useState('');
  const [configError, setConfigError] = useState('');
  const [filter, setFilter] = useState<ToolCategory | 'all'>('all');

  const handleToggle = async (tool: Tool) => {
    await toggleTool.mutateAsync({ id: tool.id, enabled: !tool.enabled });
  };

  const handleOpenConfig = (tool: Tool) => {
    setSelectedTool(tool);
    setConfigJson(JSON.stringify(tool.config, null, 2));
    setConfigError('');
    setToolConfigModalOpen(true);
  };

  const handleCloseConfig = () => {
    setToolConfigModalOpen(false);
    setSelectedTool(null);
    setConfigJson('');
    setConfigError('');
  };

  const handleSaveConfig = async () => {
    if (!selectedTool) return;
    try {
      const config = JSON.parse(configJson);
      await updateConfig.mutateAsync({ id: selectedTool.id, config });
      handleCloseConfig();
    } catch (e) {
      setConfigError(t('admin.tool.invalidJson'));
    }
  };

  const groupedTools = tools?.reduce<Record<ToolCategory, Tool[]>>((acc, tool) => {
    if (!acc[tool.category]) {
      acc[tool.category] = [];
    }
    acc[tool.category].push(tool);
    return acc;
  }, {} as Record<ToolCategory, Tool[]>);

  const filteredCategories =
    filter === 'all'
      ? (Object.keys(groupedTools || {}) as ToolCategory[])
      : [filter];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-gray-500 dark:text-gray-400">{t('common.loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {t('admin.tool.title')}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('admin.tool.description')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {t('admin.tool.filter')}:
          </span>
          <Select
            value={filter}
            onChange={(e) => setFilter(e.target.value as ToolCategory | 'all')}
            className="w-auto"
          >
            <option value="all">{t('common.all')}</option>
            {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {filteredCategories.map((category) => {
        const categoryTools = groupedTools?.[category] || [];
        if (categoryTools.length === 0) return null;
        const Icon = CATEGORY_ICONS[category];

        return (
          <div key={category}>
            <div className="flex items-center gap-2 mb-4">
              <div className="p-2 rounded-lg bg-gray-100 dark:bg-surface text-gray-600 dark:text-gray-400">
                {Icon ? <Icon className="w-5 h-5" /> : null}
              </div>
              <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                {CATEGORY_LABELS[category] ?? category}
              </h3>
              <Badge variant="default">{categoryTools.length}</Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {categoryTools.map((tool) => (
                <Card key={tool.id} padding="sm" className="hover:shadow-md transition-shadow">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="font-medium text-gray-900 dark:text-white truncate">
                          {tool.name}
                        </h4>
                        <Badge variant="default" size="sm" className="font-mono">
                          v{tool.version}
                        </Badge>
                        {tool.requires_gpu && (
                          <Badge variant="primary" size="sm">
                            <Cpu className="w-2.5 h-2.5 mr-0.5" />GPU
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                        {tool.description}
                      </p>
                      <div className="flex items-center gap-3 mt-2 text-xs text-gray-400 dark:text-gray-500">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />{tool.timeout_sec}s
                        </span>
                        <span className="flex items-center gap-1">
                          <RotateCcw className="w-3 h-3" />{tool.max_retries} retries
                        </span>
                      </div>
                    </div>
                    <Switch
                      checked={tool.enabled}
                      onChange={() => handleToggle(tool)}
                      size="sm"
                    />
                  </div>
                  <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleOpenConfig(tool)}
                    >
                      {t('admin.tool.configure')}
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        );
      })}

      {(!tools || tools.length === 0) && (
        <Card className="text-center py-12">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-surface flex items-center justify-center">
            <Wrench className="w-8 h-8 text-gray-400" />
          </div>
          <p className="text-gray-500 dark:text-gray-400">{t('admin.tool.empty')}</p>
        </Card>
      )}

      <Modal isOpen={isToolConfigModalOpen} onClose={handleCloseConfig} size="lg">
        <ModalHeader onClose={handleCloseConfig}>
          {t('admin.tool.configureTitle', { name: selectedTool?.name })}
        </ModalHeader>
        <ModalBody>
          <div className="space-y-4">
            {selectedTool && (
              <div className="p-3 rounded-lg bg-gray-50 dark:bg-surface">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {selectedTool.description}
                </p>
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('admin.tool.configJson')}
              </label>
              <Textarea
                value={configJson}
                onChange={(e) => setConfigJson(e.target.value)}
                className="font-mono text-sm min-h-[200px]"
                error={configError}
              />
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={handleCloseConfig}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={handleSaveConfig}
            loading={updateConfig.isPending}
          >
            {t('common.save')}
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
