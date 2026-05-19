import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Play, RotateCcw, Copy, Check } from 'lucide-react';
import {
  Card,
  CardContent,
  Button,
  Input,
  Select,
  Textarea,
  Switch,
  Badge,
} from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import { usePlaygroundStore } from '@/stores/playground';
import { useFlows, useRunFlow } from '@/hooks/usePlayground';
import { cn } from '@/lib/utils';
import { PageLoader } from '@/components/common/PageLoader';

export default function PlaygroundPage() {
  const { t } = useTranslation();
  const {
    selectedFlowId,
    setSelectedFlowId,
    inputs,
    setInputs,
    output,
    setOutput,
    isRunning,
    setIsRunning,
  } = usePlaygroundStore();

  const { data: flows, isLoading: flowsLoading } = useFlows();
  const runFlow = useRunFlow();
  const [copied, setCopied] = useState(false);

  const selectedFlow = flows?.find((f) => f.id === selectedFlowId);

  const handleRun = async () => {
    if (!selectedFlowId) return;

    setIsRunning(true);
    setOutput(null);

    try {
      const result = await runFlow.mutateAsync({
        flowId: selectedFlowId,
        inputs,
      });
      setOutput(result);
    } catch (error) {
      setOutput({
        success: false,
        error: error instanceof Error ? error.message : t('playground.failed'),
      });
    } finally {
      setIsRunning(false);
    }
  };

  const handleReset = () => {
    setInputs({});
    setOutput(null);
  };

  const handleCopyOutput = async () => {
    if (!output) return;
    await navigator.clipboard.writeText(JSON.stringify(output, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <PageShell
      title={t('playground.title')}
      description={t('playground.description')}
    >
      <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-6">
            <Card>
              <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
                  {t('playground.flowSelector')}
                </h2>
              </div>
              <CardContent>
                <Select
                  value={selectedFlowId || ''}
                  onChange={(e) => {
                    setSelectedFlowId(e.target.value || null);
                    setInputs({});
                    setOutput(null);
                  }}
                  className="w-full"
                  disabled={flowsLoading}
                >
                  <option value="">{t('playground.selectFlow')}</option>
                  {flows?.map((flow) => (
                    <option key={flow.id} value={flow.id}>
                      {flow.name}
                    </option>
                  ))}
                </Select>

                {selectedFlow && (
                  <div className="mt-4 p-3 rounded-lg bg-gray-50 dark:bg-surface">
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {selectedFlow.description || t('playground.noDescription')}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <Badge variant="info">{selectedFlow.nodeCount} {t('workflow.nodes')}</Badge>
                      <Badge
                        variant={selectedFlow.status === 'active' ? 'success' : 'default'}
                      >
                        {t(`workflow.status.${selectedFlow.status}`)}
                      </Badge>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
                  {t('playground.inputs')}
                </h2>
              </div>
              <CardContent className="space-y-4">
                {selectedFlow?.inputSchema ? (
                  Object.entries(selectedFlow.inputSchema).map(([key, schema]: [string, any]) => (
                    <div key={key}>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        {schema.title || key}
                        {schema.required && <span className="text-red-500 ml-1">*</span>}
                      </label>
                      {schema.type === 'string' && schema.multiline ? (
                        <Textarea
                          value={typeof inputs[key] === 'string' ? inputs[key] : ''}
                          onChange={(e) =>
                            setInputs({ ...inputs, [key]: e.target.value })
                          }
                          placeholder={schema.placeholder || t('playground.inputPlaceholderForKey', { key })}
                          rows={4}
                        />
                      ) : schema.type === 'number' ? (
                        <Input
                          type="number"
                          value={inputs[key] !== undefined && inputs[key] !== null ? String(inputs[key]) : ''}
                          onChange={(e) => {
                            const v = e.target.value;
                            setInputs({ ...inputs, [key]: v === '' ? undefined : parseFloat(v) });
                          }}
                          placeholder={schema.placeholder}
                        />
                      ) : schema.type === 'boolean' ? (
                        <Switch
                          size="sm"
                          label={schema.description}
                          checked={inputs[key] === true}
                          onChange={(e) =>
                            setInputs({ ...inputs, [key]: e.target.checked })
                          }
                        />
                      ) : (
                        <Input
                          type="text"
                          value={typeof inputs[key] === 'string' || typeof inputs[key] === 'number' ? String(inputs[key]) : ''}
                          onChange={(e) =>
                            setInputs({ ...inputs, [key]: e.target.value })
                          }
                          placeholder={schema.placeholder || t('playground.inputPlaceholderForKey', { key })}
                        />
                      )}
                      {schema.description && schema.type !== 'boolean' && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          {schema.description}
                        </p>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                    {selectedFlowId
                      ? t('playground.noInputs')
                      : t('playground.selectFlowFirst')}
                  </div>
                )}
              </CardContent>
            </Card>

            <div className="flex items-center gap-3">
              <Button
                className="flex-1"
                onClick={handleRun}
                loading={isRunning}
                disabled={!selectedFlowId}
                leftIcon={isRunning ? undefined : <Play className="w-4 h-4" />}
                responsive="sm"
              >
                {isRunning ? t('playground.running') : t('playground.run')}
              </Button>
              <Button
                variant="outline"
                onClick={handleReset}
                responsive="sm"
                leftIcon={<RotateCcw className="w-4 h-4" />}
              >
                {t('common.reset')}
              </Button>
            </div>
          </div>

          <div className="space-y-6">
            <Card className="h-full">
              <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
                  {t('playground.output')}
                </h2>
                {output && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCopyOutput}
                    responsive="sm"
                    leftIcon={
                      copied ? (
                        <Check className="w-4 h-4" />
                      ) : (
                        <Copy className="w-4 h-4" />
                      )
                    }
                  >
                    {copied ? t('common.copied') : t('common.copy')}
                  </Button>
                )}
              </div>
              <CardContent>
                {isRunning ? (
                  <div className="flex flex-col items-center justify-center py-16">
                    <PageLoader size="md" message={t('playground.executing')} />
                  </div>
                ) : output ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <Badge variant={output.success ? 'success' : 'error'}>
                        {output.success ? t('playground.success') : t('playground.failed')}
                      </Badge>
                      {output.duration && (
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {t('playground.duration', { time: output.duration })}
                        </span>
                      )}
                    </div>
                    
                    {output.error && (
                      <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
                        <p className="text-sm text-red-600 dark:text-red-400 font-mono">
                          {output.error}
                        </p>
                      </div>
                    )}

                    {output.result != null && (
                      <div className="relative">
                        <pre className="p-4 rounded-lg bg-gray-900 dark:bg-gray-950 text-gray-100 text-sm overflow-auto max-h-96 font-mono">
                          {typeof output.result === 'string'
                            ? output.result
                            : JSON.stringify(output.result as unknown, null, 2)}
                        </pre>
                      </div>
                    )}

                    {output.logs && output.logs.length > 0 && (
                      <div>
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          {t('playground.logs')}
                        </p>
                        <div className="p-3 rounded-lg bg-gray-50 dark:bg-surface max-h-48 overflow-auto">
                          {output.logs.map((log: { timestamp?: string; level?: string; message?: unknown }, index: number) => (
                            <div key={index} className="text-xs font-mono mb-1">
                              <span className="text-gray-500">[{log.timestamp ?? ''}]</span>{' '}
                              <span
                                className={cn(
                                  log.level === 'error' && 'text-red-500',
                                  log.level === 'warn' && 'text-yellow-500',
                                  log.level === 'info' && 'text-blue-500'
                                )}
                              >
                                [{log.level ?? 'info'}]
                              </span>{' '}
                              <span className="text-gray-700 dark:text-gray-300">
                                {typeof log.message === 'string' ? log.message : JSON.stringify(log.message ?? '')}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-16 text-gray-500 dark:text-gray-400">
                    <svg
                      className="w-16 h-16 mb-4 opacity-50"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    <p>{t('playground.noOutput')}</p>
                    <p className="text-sm">{t('playground.runToSeeOutput')}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
      </div>
    </PageShell>
  );
}
