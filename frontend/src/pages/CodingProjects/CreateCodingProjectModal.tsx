/**
 * Create-project modal — layout aligned with {@link CronJobModal}
 * (overlay, max-w-2xl, rounded-2xl, header/footer chrome).
 * Uses {@link Modal} so the overlay portals above the nav rail (z-stacking).
 */
import { useTranslation } from 'react-i18next';
import { Save, X } from 'lucide-react';
import { Button, Input, Modal, Select, Textarea } from '@/components/ui';
import { cn } from '@/lib/utils';
import type { TemplateInfo } from '@/hooks/useCodingProjects';

export interface CreateCodingProjectModalProps {
  open: boolean;
  onClose: () => void;
  templates: TemplateInfo[];
  name: string;
  onNameChange: (value: string) => void;
  description: string;
  onDescriptionChange: (value: string) => void;
  template: string;
  onTemplateChange: (value: string) => void;
  onSubmit: () => void | Promise<void>;
  isSubmitting: boolean;
}

export function CreateCodingProjectModal({
  open,
  onClose,
  templates,
  name,
  onNameChange,
  description,
  onDescriptionChange,
  template,
  onTemplateChange,
  onSubmit,
  isSubmitting,
}: CreateCodingProjectModalProps) {
  const { t } = useTranslation();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await Promise.resolve(onSubmit());
  };

  const canSubmit = Boolean(name.trim() && template);

  return (
    <Modal
      isOpen={open}
      onClose={onClose}
      size="md"
      className={cn(
        'flex max-h-[90vh] max-w-2xl flex-col overflow-hidden border-0 p-0 shadow-2xl',
        'rounded-2xl bg-surface'
      )}
    >
      <div className="flex min-h-0 flex-col">
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {t('codingProjects.createTitle')}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-5">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('codingProjects.fields.name')}{' '}
                <span className="text-red-500">*</span>
              </label>
              <Input
                required
                value={name}
                onChange={(e) => onNameChange(e.target.value)}
                placeholder={t('codingProjects.fields.namePlaceholder')}
                autoFocus
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('codingProjects.fields.template')}{' '}
                <span className="text-red-500">*</span>
              </label>
              <Select
                value={template}
                onChange={(e) => onTemplateChange(e.target.value)}
                required
              >
                <option value="" disabled>
                  {t('codingProjects.fields.templatePlaceholder')}
                </option>
                {templates.map((tmpl) => (
                  <option key={tmpl.name} value={tmpl.name}>
                    {tmpl.title} — {tmpl.description}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('codingProjects.fields.description')}
              </label>
              <Textarea
                value={description}
                onChange={(e) => onDescriptionChange(e.target.value)}
                rows={3}
              />
            </div>
          </div>

          <div className="flex shrink-0 items-center justify-end gap-3 border-t border-gray-200 px-6 py-4 dark:border-gray-700">
            <Button type="button" variant="secondary" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={!canSubmit || isSubmitting}
              loading={isSubmitting}
              leftIcon={<Save className="h-4 w-4" />}
            >
              {t('codingProjects.create')}
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  );
}
