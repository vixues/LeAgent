import { describe, it, expect, beforeEach } from 'vitest';
import {
  namespacedPersistName,
  registerNamespacedStore,
  setPersistIdentity,
  clearNamespacedStores,
  __resetForTests,
} from '@/lib/persistNamespace';

describe('persistNamespace', () => {
  beforeEach(() => {
    __resetForTests();
    localStorage.clear();
  });

  it('falls back to anon/none before an identity is set', () => {
    expect(namespacedPersistName('leagent-chat')).toBe('leagent-chat:anon:none');
  });

  it('combines the userId and workspaceId into the suffix', () => {
    setPersistIdentity('user-1', 'ws-42');
    expect(namespacedPersistName('leagent-chat')).toBe('leagent-chat:user-1:ws-42');
  });

  it('clears only registered stores for the current suffix', () => {
    registerNamespacedStore('chat');
    registerNamespacedStore('todos');
    setPersistIdentity('u', 'w');
    localStorage.setItem('chat:u:w', 'A');
    localStorage.setItem('todos:u:w', 'B');
    localStorage.setItem('unrelated', 'C');
    localStorage.setItem('chat:other:suffix', 'D');

    clearNamespacedStores();

    expect(localStorage.getItem('chat:u:w')).toBeNull();
    expect(localStorage.getItem('todos:u:w')).toBeNull();
    expect(localStorage.getItem('unrelated')).toBe('C');
    // Data belonging to a different identity survives — it will be purged
    // when that identity becomes active and clearNamespacedStores runs again.
    expect(localStorage.getItem('chat:other:suffix')).toBe('D');
  });

  it('setPersistIdentity(null, null) removes the suffix keys', () => {
    setPersistIdentity('u', 'w');
    setPersistIdentity(null, null);
    expect(namespacedPersistName('x')).toBe('x:anon:none');
  });
});
