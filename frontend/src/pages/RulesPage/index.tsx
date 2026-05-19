import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Search,
  Edit2,
  Play,
  Check,
  AlertTriangle,
  RefreshCw,
  Scale,
} from 'lucide-react';
import {
  Card,
  CardContent,
  Input,
  Textarea,
  Badge,
  Switch,
} from '@/components/ui';
import { Button } from '@/components/ui/Button';
import { Modal, ModalHeader, ModalBody, ModalFooter } from '@/components/ui/Modal';
import { apiClient } from '@/api/client';
import { PageShell } from '@/components/layout/PageShell';
import { useRulesStore } from '@/stores/rules';
import { useRulesList, useCreateRuleSet, useUpdateRuleSet, useEvaluateRuleSet } from '@/hooks/useRules';
import { cn } from '@/lib/utils';
import { PageLoader } from '@/components/common/PageLoader';
import { EmptyState } from '@/components/common/EmptyState';
import type { RuleSetInfo, RuleEvaluateResponse as RuleEvalResponse } from '@/types/admin';

interface RuleSetFormData {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  tags: string[];
}

const INITIAL_FORM_DATA: RuleSetFormData = {
  id: '',
  name: '',
  description: '',
  enabled: true,
  tags: [],
};

export default function RulesPage() {
  const { t } = useTranslation();
  const {
    search,
    setSearch,
    selectedRule,
    setSelectedRule,
    isEditorOpen,
    setEditorOpen,
    setTestPanelOpen,
  } = useRulesStore();

  const queryClient = useQueryClient();
  const { data: rules, isLoading } = useRulesList();
  const createRuleSet = useCreateRuleSet();
  const updateRuleSet = useUpdateRuleSet();
  const evaluateRuleSet = useEvaluateRuleSet();

  const [formData, setFormData] = useState<RuleSetFormData>(INITIAL_FORM_DATA);
  const [isEditing, setIsEditing] = useState(false);
  const [testData, setTestData] = useState('{\n  "task": {\n    "priority": 8,\n    "status": "pending"\n  }\n}');
  const [testResult, setTestResult] = useState<RuleEvalResponse | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [reloadPending, setReloadPending] = useState(false);
  const [isEvaluateOpen, setEvaluateOpen] = useState(false);
  const [evaluateRule, setEvaluateRule] = useState<RuleSetInfo | null>(null);
  const [evaluateJson, setEvaluateJson] = useState('{\n  "amount": 100\n}');
  const [evaluateResult, setEvaluateResult] = useState<RuleEvalResponse | null>(null);
  const [evaluateError, setEvaluateError] = useState<string | null>(null);
  const [evaluatePending, setEvaluatePending] = useState(false);

  const filteredRules = rules?.filter(
    (rule) =>
      rule.name.toLowerCase().includes(search.toLowerCase()) ||
      (rule.description ?? '').toLowerCase().includes(search.toLowerCase())
  );

  const handleNew = () => {
    setFormData(INITIAL_FORM_DATA);
    setIsEditing(false);
    setEditorOpen(true);
  };

  const handleEdit = (rule: RuleSetInfo) => {
    setFormData({
      id: rule.id,
      name: rule.name,
      description: rule.description ?? '',
      enabled: rule.enabled,
      tags: rule.tags ?? [],
    });
    setSelectedRule(rule as any);
    setIsEditing(true);
    setEditorOpen(true);
  };

  const handleSave = async () => {
    if (isEditing && selectedRule) {
      await updateRuleSet.mutateAsync({
        id: selectedRule.id,
        data: { name: formData.name, description: formData.description, enabled: formData.enabled, tags: formData.tags },
      });
    } else {
      await createRuleSet.mutateAsync({
        id: formData.id,
        name: formData.name,
        description: formData.description,
        enabled: formData.enabled,
        tags: formData.tags,
      });
    }
    setEditorOpen(false);
    queryClient.invalidateQueries({ queryKey: ['rules'] });
  };

  const handleTest = async () => {
    if (!selectedRule) return;

    setTestResult(null);
    setTestError(null);

    try {
      const data = JSON.parse(testData);
      const result = await evaluateRuleSet.mutateAsync({ id: selectedRule.id, data });
      setTestResult(result);
    } catch (err) {
      if (err instanceof SyntaxError) {
        setTestError(t('admin.rule.invalidTestData'));
      } else {
        setTestError(err instanceof Error ? err.message : 'Evaluation failed');
      }
    }
  };

  const handleOpenTest = (rule: RuleSetInfo) => {
    setSelectedRule(rule as any);
    setTestResult(null);
    setTestError(null);
    setTestPanelOpen(true);
  };

  const handleReloadRules = async () => {
    setReloadPending(true);
    try {
      await apiClient.post('/rules/reload');
      await queryClient.invalidateQueries({ queryKey: ['rules', 'list'] });
    } finally {
      setReloadPending(false);
    }
  };

  const handleOpenEvaluate = (rule: RuleSetInfo) => {
    setEvaluateRule(rule);
    setEvaluateJson('{\n  "amount": 100\n}');
    setEvaluateResult(null);
    setEvaluateError(null);
    setEvaluateOpen(true);
  };

  const handleRunEvaluate = async () => {
    if (!evaluateRule) return;
    setEvaluateResult(null);
    setEvaluateError(null);
    setEvaluatePending(true);
    try {
      const data = JSON.parse(evaluateJson) as Record<string, unknown>;
      const result = await apiClient.post<RuleEvalResponse>(
        `/rules/${evaluateRule.id}/evaluate`,
        { data }
      );
      setEvaluateResult(result);
    } catch (err) {
      if (err instanceof SyntaxError) {
        setEvaluateError(t('admin.rule.invalidTestData'));
      } else {
        setEvaluateError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setEvaluatePending(false);
    }
  };

  return (
    <PageShell
      title={t('rules.title')}
      description={t('rules.description')}
      actions={
        <>
          <Input
            placeholder={t('rules.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            leftIcon={<Search className="w-4 h-4" />}
            className="w-64"
          />
          <Button
            variant="secondary"
            onClick={handleReloadRules}
            loading={reloadPending}
            leftIcon={<RefreshCw className="w-4 h-4" />}
          >
            {t('rules.reloadRules')}
          </Button>
          <Button onClick={handleNew} leftIcon={<Plus className="w-4 h-4" />}>
            {t('admin.rule.add')}
          </Button>
        </>
      }
    >

      <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Card>
              <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
                  {t('rules.ruleList')}
                </h2>
              </div>
              <CardContent padding="none">
                {isLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <PageLoader message={t('common.loading')} />
                  </div>
                ) : filteredRules && filteredRules.length > 0 ? (
                  <div className="divide-y divide-gray-200 dark:divide-gray-700">
                    {filteredRules.map((rule) => (
                      <div
                        key={rule.id}
                        className={cn(
                          'p-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors',
                          !rule.enabled && 'opacity-60'
                        )}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <h3 className="font-semibold text-gray-900 dark:text-white">
                                {rule.name}
                              </h3>
                              <Badge variant={rule.enabled ? 'success' : 'default'} size="sm">
                                {rule.enabled ? t('admin.rule.enabled') : t('admin.rule.disabled')}
                              </Badge>
                              <Badge variant="info" size="sm">
                                {rule.rule_count} {t('rules.rulesCount')}
                              </Badge>
                            </div>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                              {rule.description}
                            </p>
                            {rule.tags.length > 0 && (
                              <div className="flex items-center gap-1 flex-wrap">
                                {rule.tags.map((tag) => (
                                  <Badge key={tag} variant="default" size="sm">{tag}</Badge>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleOpenTest(rule)}
                              title={t('admin.rule.testRule')}
                            >
                              <Play className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleOpenEvaluate(rule)}
                              title={t('rules.evaluate')}
                            >
                              <Scale className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleEdit(rule)}
                              title={t('common.edit')}
                            >
                              <Edit2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title={t('admin.rule.empty')}
                    action={{ label: t('admin.rule.add'), onClick: handleNew }}
                    type="file"
                  />
                )}
              </CardContent>
            </Card>
          </div>

          <div>
            <Card className="sticky top-8">
              <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h2 className="font-semibold text-gray-900 dark:text-white">
                  {t('admin.rule.testRule')}
                </h2>
              </div>
              <CardContent>
                {selectedRule ? (
                  <div className="space-y-4">
                    <div>
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('rules.testingRule')}
                      </p>
                      <p className="text-gray-900 dark:text-white font-medium">
                        {selectedRule.name}
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        {t('rules.testData')}
                      </label>
                      <Textarea
                        value={testData}
                        onChange={(e) => {
                          setTestData(e.target.value);
                          setTestError(null);
                        }}
                        rows={8}
                        className="font-mono text-sm"
                        error={testError || undefined}
                      />
                    </div>

                    <Button
                      className="w-full"
                      onClick={handleTest}
                      loading={evaluateRuleSet.isPending}
                      leftIcon={<Play className="w-4 h-4" />}
                    >
                      {t('admin.rule.runTest')}
                    </Button>

                    {testResult && (
                      <div
                        className={cn(
                          'p-3 rounded-lg border',
                          testResult.passed
                            ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                            : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
                        )}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          {testResult.passed ? (
                            <Check className="w-4 h-4 text-green-600 dark:text-green-400" />
                          ) : (
                            <AlertTriangle className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />
                          )}
                          <p
                            className={cn(
                              'text-sm font-medium',
                              testResult.passed
                                ? 'text-green-700 dark:text-green-400'
                                : 'text-yellow-700 dark:text-yellow-400'
                            )}
                          >
                            {testResult.passed ? t('admin.rule.testPassed') : t('admin.rule.testFailed')}
                          </p>
                        </div>
                        <p className="text-xs text-gray-600 dark:text-gray-400">
                          {testResult.total_rules} {t('rules.rulesEvaluated')} · {testResult.execution_time_ms.toFixed(1)}ms
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="py-8 text-center text-gray-500 dark:text-gray-400">
                    <Play className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p>{t('rules.selectToTest')}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        <Modal isOpen={isEditorOpen} onClose={() => setEditorOpen(false)} size="lg">
          <ModalHeader onClose={() => setEditorOpen(false)}>
            {isEditing ? t('admin.rule.edit') : t('admin.rule.add')}
          </ModalHeader>
          <ModalBody>
            <div className="space-y-4">
              {!isEditing && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                    ID <span className="text-red-500">*</span>
                  </label>
                  <Input
                    value={formData.id}
                    onChange={(e) => setFormData({ ...formData, id: e.target.value })}
                    placeholder={t('admin.rule.ruleSetIdPlaceholder')}
                    className="font-mono text-sm"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  {t('admin.rule.name')} <span className="text-red-500">*</span>
                </label>
                <Input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder={t('admin.rule.namePlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  {t('admin.rule.descriptionLabel')}
                </label>
                <Textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder={t('admin.rule.descriptionPlaceholder')}
                  rows={2}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  {t('rules.tags')}
                </label>
                <Input
                  value={formData.tags.join(', ')}
                  onChange={(e) => setFormData({ ...formData, tags: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                  placeholder={t('admin.rule.tagsPlaceholder')}
                />
              </div>

              <div className="flex items-center gap-2">
                <Switch
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  {t('admin.rule.enableRule')}
                </span>
              </div>
            </div>
          </ModalBody>
          <ModalFooter>
            <Button variant="secondary" onClick={() => setEditorOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleSave}
              loading={createRuleSet.isPending || updateRuleSet.isPending}
              disabled={!formData.name || (!isEditing && !formData.id)}
            >
              {t('common.save')}
            </Button>
          </ModalFooter>
        </Modal>

        <Modal isOpen={isEvaluateOpen} onClose={() => setEvaluateOpen(false)} size="lg">
          <ModalHeader onClose={() => setEvaluateOpen(false)}>
            {evaluateRule
              ? `${t('rules.evaluate')}: ${evaluateRule.name}`
              : t('rules.evaluate')}
          </ModalHeader>
          <ModalBody>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  {t('rules.testData')}
                </label>
                <Textarea
                  value={evaluateJson}
                  onChange={(e) => {
                    setEvaluateJson(e.target.value);
                    setEvaluateError(null);
                  }}
                  rows={10}
                  className="font-mono text-sm"
                  error={evaluateError || undefined}
                />
              </div>
              {evaluateResult && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    {evaluateResult.passed ? (
                      <Check className="w-4 h-4 text-green-600 dark:text-green-400" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />
                    )}
                    <span
                      className={cn(
                        'text-sm font-medium',
                        evaluateResult.passed
                          ? 'text-green-700 dark:text-green-400'
                          : 'text-yellow-700 dark:text-yellow-400'
                      )}
                    >
                      {evaluateResult.passed ? t('admin.rule.testPassed') : t('admin.rule.testFailed')}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {evaluateResult.total_rules} {t('rules.rulesEvaluated')} ·{' '}
                      {evaluateResult.execution_time_ms.toFixed(1)} ms
                    </span>
                  </div>
                  <pre className="text-xs font-mono p-3 rounded-lg bg-gray-50 dark:bg-surface border border-gray-200 dark:border-gray-700 overflow-auto max-h-64 text-gray-800 dark:text-gray-200">
                    {JSON.stringify(evaluateResult, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </ModalBody>
          <ModalFooter>
            <Button variant="secondary" onClick={() => setEvaluateOpen(false)}>
              {t('common.close')}
            </Button>
            <Button onClick={handleRunEvaluate} loading={evaluatePending} leftIcon={<Scale className="w-4 h-4" />}>
              {t('rules.evaluate')}
            </Button>
          </ModalFooter>
        </Modal>
    </PageShell>
  );
}
