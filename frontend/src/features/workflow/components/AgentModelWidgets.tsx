import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { useAvailableModels } from '@/hooks/useAdmin';
import { formatModelDisplayLabel } from '@/lib/modelSelection';

const FIELD =
  'nodrag w-full rounded border border-border bg-background px-1.5 py-0.5 text-xs text-foreground disabled:opacity-50';

/** Node types that expose the shared agent ``model`` input. */
export const AGENT_MODEL_NODE_TYPES = new Set([
  'ScriptAgentNode',
  'CodingAgentNode',
]);

export function isAgentModelNodeType(nodeType: string): boolean {
  if (nodeType === 'Agent.control_agent') return false;
  return AGENT_MODEL_NODE_TYPES.has(nodeType) || nodeType.startsWith('Agent.');
}

/**
 * Chat model picker for agent workflow nodes. Values are stored as
 * ``provider/model``; empty means the agent definition default.
 */
export function AgentModelSelect({
  value,
  onChange,
  disabled,
}: {
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const { data: availableModels } = useAvailableModels();
  const current = typeof value === 'string' ? value : '';

  const options = useMemo(() => {
    const chat = (availableModels ?? []).filter((m) => m.kind === 'chat');
    return chat.map((m) => ({
      id: `${m.provider_name}/${m.model_name}`,
      label: formatModelDisplayLabel(
        `${m.provider_name}/${m.model_name}`,
        m.model_name,
        m.provider_label,
      ),
    }));
  }, [availableModels]);

  const hasCurrent = current && options.some((o) => o.id === current);

  return (
    <select
      className={FIELD}
      value={current}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{t('workflow.agentModel.default')}</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
      {current && !hasCurrent ? <option value={current}>{current}</option> : null}
    </select>
  );
}
