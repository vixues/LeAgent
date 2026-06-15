import { describe, expect, it } from 'vitest';
import { resolveWorkflowsHubTab } from './workflowsHubTab';

describe('resolveWorkflowsHubTab', () => {
  it('selects playbooks tab from query param', () => {
    expect(resolveWorkflowsHubTab('/workflows', '?tab=playbooks')).toBe('templates');
    expect(resolveWorkflowsHubTab('/workflows', 'tab=playbooks')).toBe('templates');
  });

  it('selects playbooks tab on legacy static route', () => {
    expect(resolveWorkflowsHubTab('/workflows/templates')).toBe('templates');
    expect(resolveWorkflowsHubTab('/workflows/templates/')).toBe('templates');
  });

  it('selects saved flows tab on the hub root', () => {
    expect(resolveWorkflowsHubTab('/workflows')).toBe('workflows');
    expect(resolveWorkflowsHubTab('/workflows/')).toBe('workflows');
    expect(resolveWorkflowsHubTab('/workflows', '')).toBe('workflows');
  });
});
