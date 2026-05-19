import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Select } from '@/components/ui/Select';
import { Switch } from '@/components/ui/Switch';
import { cn } from '@/lib/utils';

export interface NodeParameter {
  key: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'textarea' | 'json';
  value: unknown;
  required?: boolean;
  options?: { value: string; label: string }[];
  placeholder?: string;
  description?: string;
}

export interface NodeIO {
  id: string;
  name: string;
  type: string;
  required?: boolean;
  description?: string;
}

export interface NodeData {
  id: string;
  type: string;
  label: string;
  description?: string;
  parameters: NodeParameter[];
  inputs: NodeIO[];
  outputs: NodeIO[];
}

interface EditNodeModalProps {
  isOpen: boolean;
  onClose: () => void;
  node: NodeData | null;
  onSave: (node: NodeData) => void;
}

type TabType = 'parameters' | 'inputs' | 'outputs';

export const EditNodeModal = ({
  isOpen,
  onClose,
  node,
  onSave,
}: EditNodeModalProps) => {
  const { t } = useTranslation();
  const [nodeData, setNodeData] = useState<NodeData | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('parameters');
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (node) {
      setNodeData({ ...node });
    }
    setActiveTab('parameters');
    setErrors({});
  }, [node, isOpen]);

  if (!nodeData) return null;

  const updateParameter = (key: string, value: unknown) => {
    setNodeData({
      ...nodeData,
      parameters: nodeData.parameters.map((p) =>
        p.key === key ? { ...p, value } : p
      ),
    });
  };

  const addInput = () => {
    const newInput: NodeIO = {
      id: `input-${Date.now()}`,
      name: '',
      type: 'string',
    };
    setNodeData({
      ...nodeData,
      inputs: [...nodeData.inputs, newInput],
    });
  };

  const updateInput = (id: string, field: keyof NodeIO, value: string | boolean) => {
    setNodeData({
      ...nodeData,
      inputs: nodeData.inputs.map((input) =>
        input.id === id ? { ...input, [field]: value } : input
      ),
    });
  };

  const removeInput = (id: string) => {
    setNodeData({
      ...nodeData,
      inputs: nodeData.inputs.filter((input) => input.id !== id),
    });
  };

  const addOutput = () => {
    const newOutput: NodeIO = {
      id: `output-${Date.now()}`,
      name: '',
      type: 'string',
    };
    setNodeData({
      ...nodeData,
      outputs: [...nodeData.outputs, newOutput],
    });
  };

  const updateOutput = (id: string, field: keyof NodeIO, value: string | boolean) => {
    setNodeData({
      ...nodeData,
      outputs: nodeData.outputs.map((output) =>
        output.id === id ? { ...output, [field]: value } : output
      ),
    });
  };

  const removeOutput = (id: string) => {
    setNodeData({
      ...nodeData,
      outputs: nodeData.outputs.filter((output) => output.id !== id),
    });
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    nodeData.parameters.forEach((param) => {
      if (param.required && !param.value) {
        newErrors[param.key] = t('modals.editNode.errors.required');
      }
    });
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = () => {
    if (!validate()) return;
    onSave(nodeData);
    onClose();
  };

  const renderParameterInput = (param: NodeParameter) => {
    switch (param.type) {
      case 'boolean':
        return (
          <Switch
            checked={param.value as boolean}
            onCheckedChange={(checked) => updateParameter(param.key, checked)}
          />
        );
      case 'select':
        return (
          <Select
            value={param.value as string}
            onChange={(e) => updateParameter(param.key, e.target.value)}
          >
            <option value="">{t('modals.editNode.selectOption')}</option>
            {param.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        );
      case 'textarea':
      case 'json':
        return (
          <Textarea
            value={
              param.type === 'json'
                ? JSON.stringify(param.value, null, 2)
                : (param.value as string)
            }
            onChange={(e) =>
              updateParameter(
                param.key,
                param.type === 'json' ? JSON.parse(e.target.value || '{}') : e.target.value
              )
            }
            placeholder={param.placeholder}
            rows={4}
            className={param.type === 'json' ? 'font-mono text-sm' : undefined}
          />
        );
      case 'number':
        return (
          <Input
            type="number"
            value={param.value as number}
            onChange={(e) => updateParameter(param.key, Number(e.target.value))}
            placeholder={param.placeholder}
          />
        );
      default:
        return (
          <Input
            value={param.value as string}
            onChange={(e) => updateParameter(param.key, e.target.value)}
            placeholder={param.placeholder}
            error={errors[param.key]}
          />
        );
    }
  };

  const tabs = [
    { key: 'parameters', label: t('modals.editNode.tabs.parameters') },
    { key: 'inputs', label: t('modals.editNode.tabs.inputs') },
    { key: 'outputs', label: t('modals.editNode.tabs.outputs') },
  ] as const;

  const footer = (
    <>
      <Button variant="outline" onClick={onClose}>
        {t('common.cancel')}
      </Button>
      <Button onClick={handleSave}>{t('common.save')}</Button>
    </>
  );

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={t('modals.editNode.title', { type: nodeData.label })}
      size="lg"
      footer={footer}
    >
      <div className="space-y-6">
        <div className="flex gap-2 p-1 bg-surface-sunken rounded-lg">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'flex-1 px-4 py-2 text-sm font-medium rounded-md transition-[color,background-color,border-color,box-shadow,opacity]',
                activeTab === tab.key
                  ? 'bg-surface-elevated text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {tab.label}
              {tab.key === 'inputs' && (
                <span className="ml-2 px-1.5 py-0.5 text-xs bg-border rounded">
                  {nodeData.inputs.length}
                </span>
              )}
              {tab.key === 'outputs' && (
                <span className="ml-2 px-1.5 py-0.5 text-xs bg-border rounded">
                  {nodeData.outputs.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {activeTab === 'parameters' && (
          <div className="space-y-5">
            {nodeData.parameters.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                {t('modals.editNode.noParameters')}
              </div>
            ) : (
              nodeData.parameters.map((param) => (
                <div key={param.key} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-foreground">
                      {param.label}
                      {param.required && <span className="text-red-500 ml-1">*</span>}
                    </label>
                    {param.type === 'boolean' && renderParameterInput(param)}
                  </div>
                  {param.description && (
                    <p className="text-xs text-muted-foreground">
                      {param.description}
                    </p>
                  )}
                  {param.type !== 'boolean' && renderParameterInput(param)}
                </div>
              ))
            )}
          </div>
        )}

        {activeTab === 'inputs' && (
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={addInput}>
                {t('modals.editNode.addInput')}
              </Button>
            </div>
            {nodeData.inputs.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                {t('modals.editNode.noInputs')}
              </div>
            ) : (
              <div className="space-y-3">
                {nodeData.inputs.map((input) => (
                  <div
                    key={input.id}
                    className="p-4 rounded-lg border border-border bg-surface-sunken/50"
                  >
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('modals.editNode.ioName')}
                        </label>
                        <Input
                          value={input.name}
                          onChange={(e) => updateInput(input.id, 'name', e.target.value)}
                          placeholder={t('modals.editNode.ioNamePlaceholder')}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('modals.editNode.ioType')}
                        </label>
                        <Select
                          value={input.type}
                          onChange={(e) => updateInput(input.id, 'type', e.target.value)}
                        >
                          <option value="string">String</option>
                          <option value="number">Number</option>
                          <option value="boolean">Boolean</option>
                          <option value="object">Object</option>
                          <option value="array">Array</option>
                          <option value="any">Any</option>
                        </Select>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={input.required ?? false}
                          onCheckedChange={(checked) =>
                            updateInput(input.id, 'required', checked)
                          }
                        />
                        <span className="text-sm text-muted-foreground">
                          {t('modals.editNode.required')}
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeInput(input.id)}
                        className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                      >
                        {t('common.delete')}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'outputs' && (
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={addOutput}>
                {t('modals.editNode.addOutput')}
              </Button>
            </div>
            {nodeData.outputs.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                {t('modals.editNode.noOutputs')}
              </div>
            ) : (
              <div className="space-y-3">
                {nodeData.outputs.map((output) => (
                  <div
                    key={output.id}
                    className="p-4 rounded-lg border border-border bg-surface-sunken/50"
                  >
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('modals.editNode.ioName')}
                        </label>
                        <Input
                          value={output.name}
                          onChange={(e) => updateOutput(output.id, 'name', e.target.value)}
                          placeholder={t('modals.editNode.ioNamePlaceholder')}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('modals.editNode.ioType')}
                        </label>
                        <Select
                          value={output.type}
                          onChange={(e) => updateOutput(output.id, 'type', e.target.value)}
                        >
                          <option value="string">String</option>
                          <option value="number">Number</option>
                          <option value="boolean">Boolean</option>
                          <option value="object">Object</option>
                          <option value="array">Array</option>
                          <option value="any">Any</option>
                        </Select>
                      </div>
                    </div>
                    <div className="mt-3 flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeOutput(output.id)}
                        className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                      >
                        {t('common.delete')}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </BaseModal>
  );
};

export default EditNodeModal;
