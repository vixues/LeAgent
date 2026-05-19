import { useCallback, useState, useEffect, useRef } from 'react';
import {
  X,
  Settings,
  ChevronDown,
  ChevronRight,
  Trash2,
  Copy,
  Code,
  FileText,
  Globe,
  Database,
  Bot,
  Mail,
  Bell,
  Clock,
  GitBranch,
  Repeat,
  Webhook,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import { Button, Input, Textarea } from '@/components/ui';
import { useFlowStore, FlowNode, FlowNodeData } from '../../../stores/flow';
import { useTranslation } from 'react-i18next';

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  doc: FileText,
  web: Globe,
  data: Database,
  llm: Bot,
  email: Mail,
  notification: Bell,
  delay: Clock,
  condition: GitBranch,
  loop: Repeat,
  webhook: Webhook,
  transform: Code,
  trigger: Zap,
  default: Settings,
};

const CATEGORY_COLORS: Record<string, string> = {
  doc: 'text-orange-600 dark:text-orange-400',
  web: 'text-blue-600 dark:text-blue-400',
  data: 'text-green-600 dark:text-green-400',
  llm: 'text-blue-600 dark:text-blue-400',
  email: 'text-red-600 dark:text-red-400',
  notification: 'text-yellow-600 dark:text-yellow-400',
  delay: 'text-muted-foreground',
  condition: 'text-sky-600 dark:text-sky-400',
  loop: 'text-cyan-600 dark:text-cyan-400',
  webhook: 'text-pink-600 dark:text-pink-400',
  transform: 'text-teal-600 dark:text-teal-400',
  trigger: 'text-amber-600 dark:text-amber-400',
  default: 'text-muted-foreground',
};

interface NodeConfigPanelProps {
  node: FlowNode;
  onClose: () => void;
}

export function NodeConfigPanel({ node, onClose }: NodeConfigPanelProps) {
  const { t } = useTranslation();
  const { updateNode, removeNode } = useFlowStore();
  const [localData, setLocalData] = useState<FlowNodeData>(node.data);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['basic', 'parameters', 'io'])
  );
  const panelRef = useRef<HTMLDivElement>(null);

  const category = localData.category || 'default';
  const IconComponent = (CATEGORY_ICONS[category] || CATEGORY_ICONS.default) as LucideIcon;
  const iconColor = CATEGORY_COLORS[category] || CATEGORY_COLORS.default;

  useEffect(() => {
    setLocalData(node.data);
  }, [node.data]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        const isCanvasClick = (e.target as HTMLElement).closest('.react-flow');
        if (isCanvasClick) {
          onClose();
        }
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  const handleLabelChange = useCallback((value: string) => {
    setLocalData((prev) => ({ ...prev, label: value }));
  }, []);

  const handleDescriptionChange = useCallback((value: string) => {
    setLocalData((prev) => ({ ...prev, description: value }));
  }, []);

  const handleParameterChange = useCallback((key: string, value: unknown) => {
    setLocalData((prev) => ({
      ...prev,
      parameters: { ...prev.parameters, [key]: value },
    }));
  }, []);

  const handleSave = useCallback(() => {
    updateNode(node.id, localData);
  }, [node.id, localData, updateNode]);

  const handleDelete = useCallback(() => {
    removeNode(node.id);
    onClose();
  }, [node.id, removeNode, onClose]);

  const handleDuplicate = useCallback(() => {
    const { addNode, nodes } = useFlowStore.getState();
    const lastNode = nodes[nodes.length - 1];
    const newNode: FlowNode = {
      id: `${node.data.category}-${Date.now()}`,
      type: 'generic',
      position: {
        x: (lastNode?.position.x || 0) + 50,
        y: (lastNode?.position.y || 0) + 50,
      },
      data: { ...localData },
    };
    addNode(newNode);
  }, [node.data.category, localData]);

  const toggleSection = useCallback((section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  }, []);

  const parameters = localData.parameters || {};
  const paramEntries = Object.entries(parameters);

  return (
    <aside
      ref={panelRef}
      className={cn(
        'w-80 flex-shrink-0 border-l border-border',
        'bg-surface flex flex-col',
        'animate-in slide-in-from-right duration-200'
      )}
    >
      <div className="flex items-center justify-between p-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div className={cn('p-2 rounded-lg bg-surface-sunken', iconColor)}>
            <IconComponent className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground text-sm">
              {t('flowEditor.configureNode')}
            </h3>
            <p className="text-xs text-muted-foreground capitalize">
              {category}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-2 rounded-lg text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <ConfigSection
          title={t('flowEditor.panelBasic')}
          id="basic"
          isExpanded={expandedSections.has('basic')}
          onToggle={() => toggleSection('basic')}
        >
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                {t('flowEditor.nodeLabel')}
              </label>
              <Input
                value={localData.label}
                onChange={(e) => handleLabelChange(e.target.value)}
                className="text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                {t('flowEditor.nodeDescription')}
              </label>
              <Textarea
                rows={2}
                value={localData.description || ''}
                onChange={(e) => handleDescriptionChange(e.target.value)}
                className="text-sm resize-none"
                placeholder={t('flowEditor.descOptionalPlaceholder')}
              />
            </div>
          </div>
        </ConfigSection>

        <ConfigSection
          title={t('flowEditor.panelParams')}
          id="parameters"
          isExpanded={expandedSections.has('parameters')}
          onToggle={() => toggleSection('parameters')}
          badge={paramEntries.length}
        >
          {paramEntries.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">
              {t('flowEditor.noParameters')}
            </p>
          ) : (
            <div className="space-y-3">
              {paramEntries.map(([key, value]) => (
                <ParameterInput
                  key={key}
                  name={key}
                  value={value}
                  onChange={(v) => handleParameterChange(key, v)}
                />
              ))}
            </div>
          )}
        </ConfigSection>

        <ConfigSection
          title={t('flowEditor.panelIo')}
          id="io"
          isExpanded={expandedSections.has('io')}
          onToggle={() => toggleSection('io')}
        >
          <div className="space-y-4">
            <div>
              <h4 className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">
                {t('flowEditor.inputsHeading')}
              </h4>
              <div className="flex flex-wrap gap-2">
                {(localData.inputs || ['input']).map((input) => (
                  <span
                    key={input}
                    className="px-2 py-1 text-xs font-mono bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded"
                  >
                    {input}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">
                {t('flowEditor.outputsHeading')}
              </h4>
              <div className="flex flex-wrap gap-2">
                {(localData.outputs || ['output']).map((output) => (
                  <span
                    key={output}
                    className="px-2 py-1 text-xs font-mono bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded"
                  >
                    {output}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </ConfigSection>

        <ConfigSection
          title={t('flowEditor.panelAdvanced')}
          id="advanced"
          isExpanded={expandedSections.has('advanced')}
          onToggle={() => toggleSection('advanced')}
        >
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                {t('flowEditor.nodeId')}
              </label>
              <Input
                value={node.id}
                readOnly
                className="text-sm font-mono bg-surface-sunken text-muted-foreground"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                {t('flowEditor.position')}
              </label>
              <div className="flex gap-2">
                <Input
                  value={t('flowEditor.posX', { x: Math.round(node.position.x) })}
                  readOnly
                  className="flex-1 text-sm font-mono bg-surface-sunken text-muted-foreground"
                />
                <Input
                  value={t('flowEditor.posY', { y: Math.round(node.position.y) })}
                  readOnly
                  className="flex-1 text-sm font-mono bg-surface-sunken text-muted-foreground"
                />
              </div>
            </div>
          </div>
        </ConfigSection>
      </div>

      <div className="p-4 border-t border-border space-y-3">
        <div className="flex gap-2">
          <button
            onClick={handleDuplicate}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-muted-foreground bg-surface-sunken rounded-lg hover:bg-border-subtle transition-colors"
          >
            <Copy className="w-4 h-4" />
            {t('flowEditor.duplicate')}
          </button>
          <button
            onClick={handleDelete}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            {t('flowEditor.delete')}
          </button>
        </div>

        <Button type="button" variant="primary" className="w-full" onClick={handleSave}>
          {t('flowEditor.applyChanges')}
        </Button>
      </div>
    </aside>
  );
}

interface ConfigSectionProps {
  title: string;
  id: string;
  isExpanded: boolean;
  onToggle: () => void;
  badge?: number;
  children: React.ReactNode;
}

function ConfigSection({
  title,
  isExpanded,
  onToggle,
  badge,
  children,
}: ConfigSectionProps) {
  return (
    <div className="border-b border-border">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-foreground hover:bg-surface-sunken/80 transition-colors"
      >
        <span className="flex items-center gap-2">
          {title}
          {badge !== undefined && badge > 0 && (
            <span className="px-1.5 py-0.5 text-xs bg-border rounded">
              {badge}
            </span>
          )}
        </span>
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-muted-foreground-tertiary" />
        ) : (
          <ChevronRight className="w-4 h-4 text-muted-foreground-tertiary" />
        )}
      </button>
      {isExpanded && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

interface ParameterInputProps {
  name: string;
  value: unknown;
  onChange: (value: unknown) => void;
}

function ParameterInput({ name, value, onChange }: ParameterInputProps) {
  const { t } = useTranslation();
  const displayName = name
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (str) => str.toUpperCase())
    .trim();

  const valueType = typeof value;

  if (valueType === 'boolean') {
    return (
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-muted-foreground">
          {displayName}
        </label>
        <button
          onClick={() => onChange(!value)}
          className={cn(
            'relative w-10 h-5 rounded-full transition-colors',
            value
              ? 'bg-primary-600'
              : 'bg-border'
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 w-4 h-4 rounded-full bg-surface shadow transition-transform',
              value ? 'left-5' : 'left-0.5'
            )}
          />
        </button>
      </div>
    );
  }

  if (valueType === 'number') {
    return (
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">
          {displayName}
        </label>
        <Input
          type="number"
          value={value as number}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          className="text-sm"
        />
      </div>
    );
  }

  if (valueType === 'object' && value !== null) {
    return (
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">
          {displayName}
        </label>
        <Textarea
          rows={3}
          value={JSON.stringify(value, null, 2)}
          onChange={(e) => {
            try {
              onChange(JSON.parse(e.target.value));
            } catch {
              // Invalid JSON, ignore
            }
          }}
          className="text-sm font-mono resize-none"
        />
      </div>
    );
  }

  return (
    <div>
      <label className="block text-xs font-medium text-muted-foreground mb-1">
        {displayName}
      </label>
      <Input
        value={String(value)}
        onChange={(e) => onChange(e.target.value)}
        className="text-sm"
        placeholder={t('flowEditor.paramValuePlaceholder', { name: displayName.toLowerCase() })}
      />
    </div>
  );
}

export default NodeConfigPanel;
