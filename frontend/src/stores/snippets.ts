import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { generateId } from '@/lib/utils';

export interface PromptSnippet {
  id: string;
  title: string;
  body: string;
  createdAt: string;
  updatedAt: string;
}

interface SnippetsStore {
  snippets: PromptSnippet[];
  seeded: boolean;
  addSnippet: (input: { title: string; body: string }) => PromptSnippet;
  updateSnippet: (id: string, input: Partial<Pick<PromptSnippet, 'title' | 'body'>>) => void;
  deleteSnippet: (id: string) => void;
  seedDefaults: (defaults: Array<{ title: string; body: string }>) => void;
}

/**
 * Local prompt-snippet library. Persisted in localStorage; backend sync is
 * intentionally deferred until real cross-device persistence is needed.
 *
 * Snippets are user-curated reusable prompt fragments surfaced in the chat
 * Workspace panel ("Snippets" tab). Selecting one pushes its `body` into the
 * composer via `useChatDraftStore`.
 */
export const useSnippetsStore = create<SnippetsStore>()(
  persist(
    (set, get) => ({
      snippets: [],
      seeded: false,
      addSnippet: ({ title, body }) => {
        const now = new Date().toISOString();
        const snippet: PromptSnippet = {
          id: generateId(),
          title: title.trim() || 'Untitled',
          body,
          createdAt: now,
          updatedAt: now,
        };
        set((state) => ({ snippets: [snippet, ...state.snippets] }));
        return snippet;
      },
      updateSnippet: (id, input) =>
        set((state) => ({
          snippets: state.snippets.map((s) =>
            s.id === id
              ? {
                  ...s,
                  ...input,
                  updatedAt: new Date().toISOString(),
                }
              : s
          ),
        })),
      deleteSnippet: (id) =>
        set((state) => ({
          snippets: state.snippets.filter((s) => s.id !== id),
        })),
      seedDefaults: (defaults) => {
        if (get().seeded) return;
        const now = new Date().toISOString();
        set({
          seeded: true,
          snippets: defaults.map((d) => ({
            id: generateId(),
            title: d.title,
            body: d.body,
            createdAt: now,
            updatedAt: now,
          })),
        });
      },
    }),
    {
      name: 'leagent-snippets',
      partialize: (state) => ({
        snippets: state.snippets,
        seeded: state.seeded,
      }),
    }
  )
);
