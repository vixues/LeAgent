import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import Fuse from 'fuse.js';
import {
  Search,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
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
  GripVertical,
  X,
  Keyboard,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import {
  TOOL_COMPONENTS,
  COMPONENT_CATEGORIES,
  ComponentDefinition,
  getComponentsByCategory,
} from '../../../hooks/flows/useAddComponent';
import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui';

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
  trigger: Zap,
};

const CATEGORY_COLORS: Record<string, string> = {
  doc: 'text-orange-500 bg-orange-50 dark:bg-orange-950/30',
  web: 'text-blue-500 bg-blue-50 dark:bg-blue-950/30',
  data: 'text-green-500 bg-green-50 dark:bg-green-950/30',
  llm: 'text-blue-600 bg-blue-50 dark:bg-blue-950/30',
  email: 'text-red-500 bg-red-50 dark:bg-red-950/30',
  notification: 'text-yellow-500 bg-yellow-50 dark:bg-yellow-950/30',
  delay: 'text-muted-foreground bg-surface-sunken/50',
  condition: 'text-sky-600 bg-sky-50 dark:bg-sky-950/30',
  loop: 'text-cyan-500 bg-cyan-50 dark:bg-cyan-950/30',
  webhook: 'text-pink-500 bg-pink-50 dark:bg-pink-950/30',
  trigger: 'text-amber-500 bg-amber-50 dark:bg-amber-950/30',
};

interface FlowSidebarProps {
  className?: string;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function FlowSidebar({
  className,
  collapsed = false,
  onToggleCollapse,
}: FlowSidebarProps) {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set(COMPONENT_CATEGORIES.map((c) => c.id))
  );
  const [draggedComponent, setDraggedComponent] = useState<ComponentDefinition | null>(null);
  const [showKeyboardHelp, setShowKeyboardHelp] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const fuse = useMemo(
    () =>
      new Fuse(TOOL_COMPONENTS, {
        keys: [
          { name: 'label', weight: 2 },
          { name: 'description', weight: 1 },
          { name: 'category', weight: 1.5 },
          { name: 'type', weight: 0.5 },
        ],
        threshold: 0.3,
        includeScore: true,
        ignoreLocation: true,
      }),
    []
  );

  const filteredComponents = useMemo(() => {
    if (!searchQuery.trim()) {
      return null;
    }
    return fuse.search(searchQuery).map((result) => result.item);
  }, [fuse, searchQuery]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
      if (e.key === 'Escape' && document.activeElement === searchInputRef.current) {
        setSearchQuery('');
        searchInputRef.current?.blur();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const toggleCategory = useCallback((categoryId: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) {
        next.delete(categoryId);
      } else {
        next.add(categoryId);
      }
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    setExpandedCategories(new Set(COMPONENT_CATEGORIES.map((c) => c.id)));
  }, []);

  const collapseAll = useCallback(() => {
    setExpandedCategories(new Set());
  }, []);

  const handleDragStart = useCallback(
    (event: React.DragEvent, component: ComponentDefinition) => {
      event.dataTransfer.setData('application/json', JSON.stringify(component));
      event.dataTransfer.effectAllowed = 'move';
      setDraggedComponent(component);

      const dragImage = document.createElement('div');
      dragImage.className = 'px-3 py-2 bg-surface rounded-lg shadow-lg border border-border text-sm font-medium';
      dragImage.textContent = component.label;
      dragImage.style.position = 'absolute';
      dragImage.style.top = '-1000px';
      document.body.appendChild(dragImage);
      event.dataTransfer.setDragImage(dragImage, 0, 0);
      setTimeout(() => document.body.removeChild(dragImage), 0);
    },
    []
  );

  const handleDragEnd = useCallback(() => {
    setDraggedComponent(null);
  }, []);

  if (collapsed) {
    return (
      <aside
        className={cn(
          'w-12 flex-shrink-0 border-r border-border',
          'bg-surface flex flex-col items-center py-4',
          className
        )}
      >
        <button
          onClick={onToggleCollapse}
          className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
          title={t('flowEditor.expandSidebar')}
        >
          <ChevronRight className="w-5 h-5" />
        </button>

        <div className="flex-1 flex flex-col items-center gap-2 mt-4 overflow-y-auto">
          {COMPONENT_CATEGORIES.slice(0, 8).map((category) => {
            const IconComponent = CATEGORY_ICONS[category.id] || FileText;
            const colorClass = CATEGORY_COLORS[category.id] || 'text-muted-foreground bg-surface-sunken';
            return (
              <button
                key={category.id}
                className={cn(
                  'p-2 rounded-lg transition-colors',
                  colorClass.split(' ')[0],
                  'hover:bg-surface-sunken'
                )}
                title={category.label}
              >
                <IconComponent className="w-4 h-4" />
              </button>
            );
          })}
        </div>
      </aside>
    );
  }

  return (
    <aside
      className={cn(
        'w-72 flex-shrink-0 border-r border-border',
        'bg-surface flex flex-col',
        'animate-in slide-in-from-left duration-200',
        className
      )}
    >
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-foreground">
            {t('flowEditor.componentsTitle')}
          </h2>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowKeyboardHelp(!showKeyboardHelp)}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                showKeyboardHelp
                  ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400'
                  : 'text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken'
              )}
              title={t('flowEditor.shortcuts')}
            >
              <Keyboard className="w-4 h-4" />
            </button>
            <button
              onClick={onToggleCollapse}
              className="p-1.5 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors"
              title={t('flowEditor.collapseSidebar')}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          </div>
        </div>

        <Input
          ref={searchInputRef}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t('flowEditor.searchComponents')}
          className="pr-16"
          leftIcon={<Search className="w-4 h-4" />}
          rightIcon={
            searchQuery ? (
              <button
                onClick={() => setSearchQuery('')}
                className="p-1 rounded text-muted-foreground-tertiary hover:text-foreground"
              >
                <X className="w-3 h-3" />
              </button>
            ) : (
              <kbd className="px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground-tertiary bg-surface-sunken rounded">
                ⌘K
              </kbd>
            )
          }
        />
      </div>

      {showKeyboardHelp && (
        <div className="px-4 py-3 bg-surface-sunken/50 border-b border-border">
          <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
            {t('flowEditor.shortcutsSection')}
          </h3>
          <div className="space-y-1 text-xs">
            <div className="flex items-center justify-between text-muted-foreground">
              <span>{t('flowEditor.shortcutSearch')}</span>
              <kbd className="px-1.5 py-0.5 bg-border rounded">⌘K</kbd>
            </div>
            <div className="flex items-center justify-between text-muted-foreground">
              <span>{t('flowEditor.shortcutToggleSidebar')}</span>
              <kbd className="px-1.5 py-0.5 bg-border rounded">⌘B</kbd>
            </div>
            <div className="flex items-center justify-between text-muted-foreground">
              <span>{t('flowEditor.shortcutUndo')}</span>
              <kbd className="px-1.5 py-0.5 bg-border rounded">⌘Z</kbd>
            </div>
            <div className="flex items-center justify-between text-muted-foreground">
              <span>{t('flowEditor.shortcutRedo')}</span>
              <kbd className="px-1.5 py-0.5 bg-border rounded">⌘⇧Z</kbd>
            </div>
            <div className="flex items-center justify-between text-muted-foreground">
              <span>{t('flowEditor.shortcutSave')}</span>
              <kbd className="px-1.5 py-0.5 bg-border rounded">⌘S</kbd>
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {filteredComponents ? (
          <div className="p-2 space-y-1">
            <div className="flex items-center justify-between px-2 py-1">
              <p className="text-xs text-muted-foreground">
                {t('flowEditor.searchResultsFound', { count: filteredComponents.length })}
              </p>
            </div>
            {filteredComponents.map((component) => (
              <ComponentItem
                key={component.type}
                component={component}
                onDragStart={handleDragStart}
                onDragEnd={handleDragEnd}
                isDragging={draggedComponent?.type === component.type}
              />
            ))}
            {filteredComponents.length === 0 && (
              <div className="text-center py-8">
                <Search className="w-8 h-8 text-muted-foreground-tertiary mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">
                  {t('flowEditor.noComponentsFound')}
                </p>
                <p className="text-xs text-muted-foreground-tertiary mt-1">
                  {t('flowEditor.tryDifferentSearch')}
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="p-2">
            <div className="flex items-center justify-between px-2 py-1 mb-1">
              <p className="text-xs text-muted-foreground">
                {t('flowEditor.componentLibraryCount', { count: TOOL_COMPONENTS.length })}
              </p>
              <div className="flex items-center gap-1">
                <button
                  onClick={expandAll}
                  className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                >
                  {t('flowEditor.expandAll')}
                </button>
                <span className="text-muted-foreground-tertiary">|</span>
                <button
                  onClick={collapseAll}
                  className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                >
                  {t('flowEditor.collapseAll')}
                </button>
              </div>
            </div>
            <div className="space-y-1">
              {COMPONENT_CATEGORIES.map((category) => (
                <CategorySection
                  key={category.id}
                  category={category}
                  isExpanded={expandedCategories.has(category.id)}
                  onToggle={() => toggleCategory(category.id)}
                  onDragStart={handleDragStart}
                  onDragEnd={handleDragEnd}
                  draggedComponent={draggedComponent}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="p-3 border-t border-border bg-surface-sunken/50">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <GripVertical className="w-3 h-3" />
          <span>{t('flowEditor.dragOntoCanvas')}</span>
        </div>
      </div>
    </aside>
  );
}

interface CategorySectionProps {
  category: { id: string; label: string };
  isExpanded: boolean;
  onToggle: () => void;
  onDragStart: (event: React.DragEvent, component: ComponentDefinition) => void;
  onDragEnd: () => void;
  draggedComponent: ComponentDefinition | null;
}

function CategorySection({
  category,
  isExpanded,
  onToggle,
  onDragStart,
  onDragEnd,
  draggedComponent,
}: CategorySectionProps) {
  const components = getComponentsByCategory(category.id);
  const IconComponent = CATEGORY_ICONS[category.id] || FileText;
  const colorClass = CATEGORY_COLORS[category.id] || 'text-muted-foreground bg-surface-sunken';
  const [iconColor, bgColor] = colorClass.split(' ');

  if (components.length === 0) return null;

  return (
    <div className="mb-0.5">
      <button
        onClick={onToggle}
        className={cn(
          'w-full flex items-center gap-2 px-2 py-2 rounded-lg',
          'text-left text-sm font-medium transition-colors',
          'text-muted-foreground',
          'hover:bg-surface-sunken'
        )}
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-muted-foreground-tertiary flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-muted-foreground-tertiary flex-shrink-0" />
        )}
        <div className={cn('p-1.5 rounded-md', bgColor)}>
          <IconComponent className={cn('w-3.5 h-3.5', iconColor)} />
        </div>
        <span className="flex-1 truncate">{category.label}</span>
        <span className="text-xs text-muted-foreground-tertiary tabular-nums">
          {components.length}
        </span>
      </button>

      {isExpanded && (
        <div className="ml-6 mt-0.5 space-y-0.5 pb-1">
          {components.map((component) => (
            <ComponentItem
              key={component.type}
              component={component}
              onDragStart={onDragStart}
              onDragEnd={onDragEnd}
              isDragging={draggedComponent?.type === component.type}
              compact
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface ComponentItemProps {
  component: ComponentDefinition;
  onDragStart: (event: React.DragEvent, component: ComponentDefinition) => void;
  onDragEnd: () => void;
  isDragging?: boolean;
  compact?: boolean;
}

function ComponentItem({
  component,
  onDragStart,
  onDragEnd,
  isDragging = false,
  compact = false,
}: ComponentItemProps) {
  const IconComponent = CATEGORY_ICONS[component.category] || FileText;
  const colorClass = CATEGORY_COLORS[component.category] || 'text-muted-foreground bg-surface-sunken';
  const [iconColor, bgColor] = colorClass.split(' ');

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, component)}
      onDragEnd={onDragEnd}
      className={cn(
        'group flex items-center gap-2 rounded-lg cursor-grab active:cursor-grabbing',
        'border border-transparent transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-150',
        'hover:bg-surface-sunken',
        'hover:border-border',
        'hover:shadow-sm',
        compact ? 'px-2 py-1.5' : 'px-3 py-2',
        isDragging && 'opacity-50 ring-2 ring-primary-500'
      )}
    >
      <GripVertical className="w-3 h-3 text-muted-foreground-tertiary opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />

      <div
        className={cn(
          'flex-shrink-0 rounded-md flex items-center justify-center',
          compact ? 'w-6 h-6' : 'w-8 h-8',
          bgColor
        )}
      >
        <IconComponent
          className={cn(compact ? 'w-3.5 h-3.5' : 'w-4 h-4', iconColor)}
        />
      </div>

      <div className="flex-1 min-w-0">
        <p
          className={cn(
            'font-medium text-foreground truncate',
            compact ? 'text-xs' : 'text-sm'
          )}
        >
          {component.label}
        </p>
        {!compact && component.description && (
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {component.description}
          </p>
        )}
      </div>

      {!compact && (
        <div className="opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="text-[10px] text-muted-foreground-tertiary uppercase tracking-wider">
            {component.category}
          </span>
        </div>
      )}
    </div>
  );
}

export default FlowSidebar;
