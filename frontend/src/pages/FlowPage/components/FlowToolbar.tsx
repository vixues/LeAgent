import { useCallback, useState } from 'react';
import {
  Save,
  Play,
  Download,
  Upload,
  Undo2,
  Redo2,
  Settings,
  MoreHorizontal,
  Loader2,
  Check,
  ChevronDown,
  Trash2,
  Copy,
  FileJson,
  Image as ImageIcon,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '../../../lib/utils';
import { PRIMARY_SOFT_CTA_CLASSNAME } from '@/components/ui/Button';
import { useFlowStore } from '../../../stores/flow';
import { useSaveFlow } from '../../../hooks/flows/useSaveFlow';

interface FlowToolbarProps {
  className?: string;
  onRun?: () => void;
  onSettings?: () => void;
  isRunning?: boolean;
  extraActions?: React.ReactNode;
}

export function FlowToolbar({ className, onRun, onSettings, isRunning = false, extraActions }: FlowToolbarProps) {
  const { t } = useTranslation();
  const {
    flowName,
    setFlowName,
    isDirty,
    undo,
    redo,
    canUndo,
    canRedo,
    getFlowData,
    resetFlow,
  } = useFlowStore();

  const { saveFlow, isSaving } = useSaveFlow({
    onSuccess: () => {
      setShowSaved(true);
      setTimeout(() => setShowSaved(false), 2000);
    },
  });

  const [showSaved, setShowSaved] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  const handleSave = useCallback(async () => {
    try {
      await saveFlow();
    } catch (error) {
      console.error('Failed to save:', error);
    }
  }, [saveFlow]);

  const handleExportJSON = useCallback(() => {
    const flowData = getFlowData();
    const dataStr = JSON.stringify(flowData, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${flowData.name || 'flow'}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setShowExportMenu(false);
  }, [getFlowData]);

  const handleImport = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;

      try {
        const text = await file.text();
        const data = JSON.parse(text);
        if (data.nodes && data.edges) {
          useFlowStore.getState().loadFlow({
            id: data.id || null,
            name: data.name || file.name.replace('.json', ''),
            nodes: data.nodes,
            edges: data.edges,
          });
        }
      } catch (error) {
        console.error('Failed to import:', error);
      }
    };
    input.click();
  }, []);

  const handleNameChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setFlowName(e.target.value);
    },
    [setFlowName]
  );

  const handleNameBlur = useCallback(() => {
    setIsEditing(false);
    if (!flowName.trim()) {
      setFlowName(t('flowEditor.untitledFlow'));
    }
  }, [flowName, setFlowName, t]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleNameBlur();
      }
      if (e.key === 'Escape') {
        setIsEditing(false);
      }
    },
    [handleNameBlur]
  );

  return (
    <header
      className={cn(
        'h-14 flex-shrink-0 border-b border-border',
        'bg-surface flex items-center justify-between gap-3 px-4',
        className
      )}
    >
      <div className="flex items-center gap-4 min-w-0 flex-shrink">
        {isEditing ? (
          <input
            type="text"
            value={flowName}
            onChange={handleNameChange}
            onBlur={handleNameBlur}
            onKeyDown={handleKeyDown}
            autoFocus
            className="text-lg font-semibold bg-transparent border-b-2 border-primary-500 outline-none text-foreground px-1"
          />
        ) : (
          <button
            onClick={() => setIsEditing(true)}
            className="text-lg font-semibold text-foreground hover:text-primary-600 dark:hover:text-primary-400 transition-colors truncate whitespace-nowrap min-w-0 max-w-[40vw]"
            title={flowName}
          >
            {flowName}
            {isDirty && <span className="ml-1 text-primary-500">*</span>}
          </button>
        )}
      </div>

      <div className="flex items-center gap-1 flex-shrink-0 overflow-x-auto no-scrollbar">
        <ToolbarButton
          icon={Undo2}
          label={t('common.undo') || 'Undo'}
          onClick={undo}
          disabled={!canUndo()}
          shortcut="⌘Z"
        />
        <ToolbarButton
          icon={Redo2}
          label={t('common.redo') || 'Redo'}
          onClick={redo}
          disabled={!canRedo()}
          shortcut="⌘⇧Z"
        />

        <div className="w-px h-6 bg-border mx-2" />

        <ToolbarButton
          icon={isSaving ? Loader2 : showSaved ? Check : Save}
          label={t('common.save')}
          onClick={handleSave}
          disabled={isSaving || !isDirty}
          loading={isSaving}
          success={showSaved}
          shortcut="⌘S"
          dataAction="save"
        />

        <ToolbarButton
          icon={isRunning ? Loader2 : Play}
          label={isRunning ? t('flowEditor.running') : t('workflow.run')}
          onClick={onRun}
          disabled={isRunning}
          loading={isRunning}
          variant="primary"
        />

        <div className="w-px h-6 bg-border mx-2" />

        <div className="relative">
          <ToolbarButton
            icon={Download}
            label={t('workflow.export')}
            onClick={() => setShowExportMenu(!showExportMenu)}
            trailing={<ChevronDown className="w-3 h-3 ml-1" />}
          />
          
          {showExportMenu && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowExportMenu(false)}
              />
              <div className="absolute right-0 top-full mt-1 w-48 bg-surface rounded-lg shadow-lg border border-border py-1 z-20">
                <button
                  onClick={handleExportJSON}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:bg-surface-sunken whitespace-nowrap"
                >
                  <FileJson className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{t('flowEditor.exportAsJson')}</span>
                </button>
                <button
                  onClick={() => {
                    setShowExportMenu(false);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:bg-surface-sunken whitespace-nowrap"
                >
                  <ImageIcon className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{t('flowEditor.exportAsPng')}</span>
                </button>
                <button
                  onClick={() => {
                    setShowExportMenu(false);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:bg-surface-sunken whitespace-nowrap"
                >
                  <Copy className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{t('flowEditor.copyToClipboard')}</span>
                </button>
              </div>
            </>
          )}
        </div>

        <ToolbarButton
          icon={Upload}
          label={t('workflow.import')}
          onClick={handleImport}
        />

        <div className="w-px h-6 bg-border mx-2" />

        <ToolbarButton
          icon={Trash2}
          label={t('flowEditor.clear')}
          onClick={resetFlow}
          variant="danger"
        />

        <ToolbarButton
          icon={Settings}
          label={t('settings.title')}
          onClick={onSettings}
        />

        <ToolbarButton icon={MoreHorizontal} label={t('flowEditor.more')} />

        {extraActions && (
          <>
            <div className="w-px h-6 bg-border mx-1" />
            {extraActions}
          </>
        )}
      </div>
    </header>
  );
}

interface ToolbarButtonProps {
  icon: React.ElementType;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  success?: boolean;
  variant?: 'default' | 'primary' | 'danger';
  shortcut?: string;
  trailing?: React.ReactNode;
  dataAction?: string;
}

function ToolbarButton({
  icon: Icon,
  label,
  onClick,
  disabled = false,
  loading = false,
  success = false,
  variant = 'default',
  shortcut,
  trailing,
  dataAction,
}: ToolbarButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={shortcut ? `${label} (${shortcut})` : label}
      data-action={dataAction}
      className={cn(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-200',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        variant === 'default' && [
          'text-muted-foreground',
          'hover:bg-surface-sunken',
        ],
        variant === 'primary' && [PRIMARY_SOFT_CTA_CLASSNAME, 'disabled:opacity-50'],
        variant === 'danger' && [
          'text-red-600 dark:text-red-400',
          'hover:bg-red-50 dark:hover:bg-red-900/30',
        ],
        success && 'text-green-600 dark:text-green-400'
      )}
    >
      <Icon className={cn('w-4 h-4 flex-shrink-0', loading && 'animate-spin')} />
      <span className="hidden sm:inline whitespace-nowrap">{label}</span>
      {trailing}
    </button>
  );
}

export default FlowToolbar;
