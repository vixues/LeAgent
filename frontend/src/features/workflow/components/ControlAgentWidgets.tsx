import { useTranslation } from 'react-i18next';

import { AgentModelSelect } from './AgentModelWidgets';

const FIELD =
  'nodrag w-full rounded border border-border bg-background px-1.5 py-0.5 text-xs text-foreground disabled:opacity-50';

export const CONTROL_AGENT_NODE_TYPE = 'Agent.control_agent';

export function isControlAgentNodeType(nodeType: string): boolean {
  return nodeType === CONTROL_AGENT_NODE_TYPE;
}

const MODE_I18N: Record<string, string> = {
  prompt_generate: 'workflow.controlAgent.modes.promptGenerate',
  param_generate: 'workflow.controlAgent.modes.paramGenerate',
  state_patch: 'workflow.controlAgent.modes.statePatch',
  route_decision: 'workflow.controlAgent.modes.routeDecision',
  custom: 'workflow.controlAgent.modes.custom',
};

/** Mode preset selector for Agent: Control Agent. */
export function ControlAgentModeSelect({
  choices,
  value,
  onChange,
  disabled,
}: {
  choices: string[];
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const current = typeof value === 'string' ? value : 'custom';

  return (
    <select
      className={FIELD}
      value={current}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {choices.map((c) => (
        <option key={c} value={c}>
          {t(MODE_I18N[c] ?? c, { defaultValue: c })}
        </option>
      ))}
    </select>
  );
}

export { AgentModelSelect };
