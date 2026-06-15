const HUB_TABS = ['workflows', 'templates'] as const;
export type WorkflowsHubTab = (typeof HUB_TABS)[number];

/** Query value for the playbooks hub tab (`/workflows?tab=playbooks`). */
export const WORKFLOWS_HUB_PLAYBOOKS_TAB = 'playbooks';

export function resolveWorkflowsHubTab(pathname: string, search = ''): WorkflowsHubTab {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  const tabParam = new URLSearchParams(raw).get('tab');
  if (tabParam === WORKFLOWS_HUB_PLAYBOOKS_TAB || tabParam === 'templates') {
    return 'templates';
  }
  if (pathname.replace(/\/+$/, '') === '/workflows/templates') {
    return 'templates';
  }
  return 'workflows';
}

export { HUB_TABS };
