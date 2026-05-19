import { beforeEach, describe, expect, it } from 'vitest';
import { isWorkspaceTab, useLayoutStore } from './layout';

describe('useLayoutStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useLayoutStore.setState({
      sidebarCollapsed: false,
      chatHistoryOpen: false,
      workspaceOpen: false,
      workspaceTab: 'files',
      focusMode: false,
    });
  });

  it('validates workspace tab ids', () => {
    expect(isWorkspaceTab('agent')).toBe(true);
    expect(isWorkspaceTab('folders')).toBe(false);
    expect(isWorkspaceTab(null)).toBe(false);
  });

  it('toggles workspace and focus mode independently', () => {
    const store = useLayoutStore.getState();

    store.toggleWorkspace();
    store.toggleFocusMode();

    expect(useLayoutStore.getState().workspaceOpen).toBe(true);
    expect(useLayoutStore.getState().focusMode).toBe(true);
  });
});
