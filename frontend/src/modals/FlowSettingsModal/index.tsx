import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Select } from '@/components/ui/Select';
import { Switch } from '@/components/ui/Switch';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

export interface FlowSettings {
  id?: string;
  name: string;
  description: string;
  endpoint: string;
  tags: string[];
  isPublic: boolean;
  permissions: {
    canView: string[];
    canEdit: string[];
    canRun: string[];
  };
  webhook?: {
    enabled: boolean;
    url: string;
    secret: string;
  };
}

interface FlowSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings?: Partial<FlowSettings>;
  onSave: (settings: FlowSettings) => void;
}

const defaultSettings: FlowSettings = {
  name: '',
  description: '',
  endpoint: '',
  tags: [],
  isPublic: false,
  permissions: {
    canView: ['all'],
    canEdit: ['admin'],
    canRun: ['all'],
  },
  webhook: {
    enabled: false,
    url: '',
    secret: '',
  },
};

export const FlowSettingsModal = ({
  isOpen,
  onClose,
  settings,
  onSave,
}: FlowSettingsModalProps) => {
  const { t } = useTranslation();
  const [formData, setFormData] = useState<FlowSettings>(defaultSettings);
  const [tagInput, setTagInput] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [activeSection, setActiveSection] = useState<'basic' | 'permissions' | 'webhook'>('basic');

  useEffect(() => {
    if (settings) {
      setFormData({ ...defaultSettings, ...settings });
    } else {
      setFormData(defaultSettings);
    }
    setErrors({});
    setActiveSection('basic');
  }, [settings, isOpen]);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (!formData.name.trim()) {
      newErrors.name = t('modals.flowSettings.errors.nameRequired');
    }
    if (!formData.endpoint.trim()) {
      newErrors.endpoint = t('modals.flowSettings.errors.endpointRequired');
    } else if (!/^[a-z0-9-]+$/.test(formData.endpoint)) {
      newErrors.endpoint = t('modals.flowSettings.errors.endpointInvalid');
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleAddTag = () => {
    if (tagInput.trim() && !formData.tags.includes(tagInput.trim())) {
      setFormData({
        ...formData,
        tags: [...formData.tags, tagInput.trim()],
      });
      setTagInput('');
    }
  };

  const handleRemoveTag = (tag: string) => {
    setFormData({
      ...formData,
      tags: formData.tags.filter((t) => t !== tag),
    });
  };

  const handleSave = () => {
    if (!validate()) return;
    onSave(formData);
    onClose();
  };

  const sectionTabs = [
    { key: 'basic', label: t('modals.flowSettings.sections.basic') },
    { key: 'permissions', label: t('modals.flowSettings.sections.permissions') },
    { key: 'webhook', label: t('modals.flowSettings.sections.webhook') },
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
      title={t('modals.flowSettings.title')}
      size="lg"
      footer={footer}
    >
      <div className="space-y-6">
        <div className="flex gap-2 p-1 bg-surface-sunken rounded-lg">
          {sectionTabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveSection(tab.key)}
              className={cn(
                'flex-1 px-4 py-2 text-sm font-medium rounded-md transition-[color,background-color,border-color,box-shadow,opacity]',
                activeSection === tab.key
                  ? 'bg-surface-elevated text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeSection === 'basic' && (
          <div className="space-y-5">
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                {t('modals.flowSettings.name')} <span className="text-red-500">*</span>
              </label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder={t('modals.flowSettings.namePlaceholder')}
                error={errors.name}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                {t('modals.flowSettings.description')}
              </label>
              <Textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder={t('modals.flowSettings.descriptionPlaceholder')}
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                {t('modals.flowSettings.endpoint')} <span className="text-red-500">*</span>
              </label>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">/api/flows/</span>
                <Input
                  value={formData.endpoint}
                  onChange={(e) => setFormData({ ...formData, endpoint: e.target.value })}
                  placeholder="my-flow"
                  error={errors.endpoint}
                  className="flex-1"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                {t('modals.flowSettings.endpointHelp')}
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                {t('modals.flowSettings.tags')}
              </label>
              <div className="flex gap-2">
                <Input
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddTag())}
                  placeholder={t('modals.flowSettings.tagPlaceholder')}
                  className="flex-1"
                />
                <Button variant="outline" onClick={handleAddTag}>
                  {t('modals.flowSettings.addTag')}
                </Button>
              </div>
              {formData.tags.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {formData.tags.map((tag) => (
                    <Badge
                      key={tag}
                      variant="secondary"
                      className="cursor-pointer hover:bg-red-100 dark:hover:bg-red-900/30"
                      onClick={() => handleRemoveTag(tag)}
                    >
                      {tag}
                      <svg className="w-3 h-3 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeSection === 'permissions' && (
          <div className="space-y-5">
            <div className="flex items-center justify-between py-3 border-b border-border">
              <div>
                <p className="font-medium text-foreground">
                  {t('modals.flowSettings.isPublic')}
                </p>
                <p className="text-sm text-muted-foreground">
                  {t('modals.flowSettings.isPublicDescription')}
                </p>
              </div>
              <Switch
                checked={formData.isPublic}
                onCheckedChange={(checked) => setFormData({ ...formData, isPublic: checked })}
              />
            </div>

            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  {t('modals.flowSettings.canView')}
                </label>
                <Select
                  value={formData.permissions.canView[0] || 'all'}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      permissions: { ...formData.permissions, canView: [e.target.value] },
                    })
                  }
                >
                  <option value="all">{t('modals.flowSettings.permissionOptions.all')}</option>
                  <option value="admin">{t('modals.flowSettings.permissionOptions.admin')}</option>
                  <option value="owner">{t('modals.flowSettings.permissionOptions.owner')}</option>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  {t('modals.flowSettings.canEdit')}
                </label>
                <Select
                  value={formData.permissions.canEdit[0] || 'admin'}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      permissions: { ...formData.permissions, canEdit: [e.target.value] },
                    })
                  }
                >
                  <option value="all">{t('modals.flowSettings.permissionOptions.all')}</option>
                  <option value="admin">{t('modals.flowSettings.permissionOptions.admin')}</option>
                  <option value="owner">{t('modals.flowSettings.permissionOptions.owner')}</option>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  {t('modals.flowSettings.canRun')}
                </label>
                <Select
                  value={formData.permissions.canRun[0] || 'all'}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      permissions: { ...formData.permissions, canRun: [e.target.value] },
                    })
                  }
                >
                  <option value="all">{t('modals.flowSettings.permissionOptions.all')}</option>
                  <option value="admin">{t('modals.flowSettings.permissionOptions.admin')}</option>
                  <option value="owner">{t('modals.flowSettings.permissionOptions.owner')}</option>
                </Select>
              </div>
            </div>
          </div>
        )}

        {activeSection === 'webhook' && (
          <div className="space-y-5">
            <div className="flex items-center justify-between py-3 border-b border-border">
              <div>
                <p className="font-medium text-foreground">
                  {t('modals.flowSettings.webhookEnabled')}
                </p>
                <p className="text-sm text-muted-foreground">
                  {t('modals.flowSettings.webhookEnabledDescription')}
                </p>
              </div>
              <Switch
                checked={formData.webhook?.enabled ?? false}
                onCheckedChange={(checked) =>
                  setFormData({
                    ...formData,
                    webhook: { ...formData.webhook!, enabled: checked },
                  })
                }
              />
            </div>

            {formData.webhook?.enabled && (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">
                    Webhook URL
                  </label>
                  <Input
                    value={formData.webhook?.url || ''}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        webhook: { ...formData.webhook!, url: e.target.value },
                      })
                    }
                    placeholder={t('integrations.placeholderUrl')}
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">
                    {t('modals.flowSettings.webhookSecret')}
                  </label>
                  <Input
                    type="password"
                    value={formData.webhook?.secret || ''}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        webhook: { ...formData.webhook!, secret: e.target.value },
                      })
                    }
                    placeholder={t('modals.flowSettings.webhookSecretPlaceholder')}
                  />
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </BaseModal>
  );
};

export default FlowSettingsModal;
