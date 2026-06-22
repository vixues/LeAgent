import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getChatProjectHeaders, useChatProjectStore } from './chatProjects';

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('chat project unlock headers', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    useChatProjectStore.setState({
      projects: [],
      currentProjectId: null,
      isLoading: false,
      error: null,
    });
  });

  it('returns an unlock header for a non-expired token', () => {
    sessionStorage.setItem(
      'leagent-chat-project-unlocks',
      JSON.stringify({
        p1: { token: 'tok', expiresAt: Math.floor(Date.now() / 1000) + 60 },
      }),
    );

    expect(getChatProjectHeaders('p1')).toEqual({ 'X-Chat-Project-Token': 'tok' });
  });

  it('drops expired tokens', () => {
    sessionStorage.setItem(
      'leagent-chat-project-unlocks',
      JSON.stringify({
        p1: { token: 'tok', expiresAt: Math.floor(Date.now() / 1000) - 1 },
      }),
    );

    expect(getChatProjectHeaders('p1')).toBeUndefined();
    expect(sessionStorage.getItem('leagent-chat-project-unlocks')).toBe('{}');
  });
});
