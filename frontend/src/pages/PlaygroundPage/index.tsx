import { useTranslation } from 'react-i18next';
import {
  Card,
  CardContent,
  Select,
  Badge,
} from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import { usePlaygroundStore } from '@/stores/playground';
import { useFlows } from '@/hooks/usePlayground';
import { useExecutionStream } from '@/features/workflow/api/useExecutionStream';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { WorkflowRunPanel } from '@/features/workflow/components/WorkflowRunPanel';
import type { WorkflowInputSpec } from '@/features/workflow/genui/inputsToGenUiTree';
import type { WorkflowOutputSpec } from '@/features/workflow/genui/outputsToGenUiTree';

/**
 * Workflow playground: pick a flow, submit parameters through the generated
 * GenUI form, interact with pauses/reviews, and read structured results —
 * the same I/O surface as the graph editor's Run panel.
 */
export default function PlaygroundPage() {
  const { t } = useTranslation();
  const { selectedFlowId, setSelectedFlowId } = usePlaygroundStore();

  const { data: flows, isLoading: flowsLoading } = useFlows();
  const selectedFlow = flows?.find((f) => f.id === selectedFlowId);

  // Live execution events feed the shared overlay store the panel renders.
  const promptId = useExecutionOverlay((s) => s.promptId);
  const resetOverlay = useExecutionOverlay((s) => s.reset);
  useExecutionStream(promptId);

  return (
    <PageShell
      title={t('playground.title')}
      description={t('playground.description')}
    >
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <Card>
          <div className="border-b border-gray-200 p-4 dark:border-gray-700">
            <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
              {t('playground.flowSelector')}
            </h2>
          </div>
          <CardContent>
            <Select
              value={selectedFlowId || ''}
              onChange={(e) => {
                setSelectedFlowId(e.target.value || null);
                resetOverlay();
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
              <div className="mt-4 rounded-lg bg-gray-50 p-3 dark:bg-surface">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {selectedFlow.description || t('playground.noDescription')}
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <Badge variant="info">
                    {selectedFlow.nodeCount} {t('workflow.nodes')}
                  </Badge>
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

        {selectedFlowId ? (
          <Card>
            <WorkflowRunPanel
              flowId={selectedFlowId}
              inputs={(selectedFlow?.inputs ?? []) as WorkflowInputSpec[]}
              outputs={(selectedFlow?.outputs ?? []) as WorkflowOutputSpec[]}
            />
          </Card>
        ) : (
          <Card>
            <CardContent>
              <div className="py-12 text-center text-gray-500 dark:text-gray-400">
                {t('playground.selectFlowFirst')}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </PageShell>
  );
}
