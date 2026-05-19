import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Search, Sparkles, Send, Edit2, Trash2, Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { useSnippetsStore, type PromptSnippet } from '@/stores/snippets';
import { useChatDraftStore } from '@/stores/chatDraft';

export function SnippetsTab() {
  const { t } = useTranslation();
  const snippets = useSnippetsStore((s) => s.snippets);
  const addSnippet = useSnippetsStore((s) => s.addSnippet);
  const updateSnippet = useSnippetsStore((s) => s.updateSnippet);
  const deleteSnippet = useSnippetsStore((s) => s.deleteSnippet);
  const seedDefaults = useSnippetsStore((s) => s.seedDefaults);
  const pushInsert = useChatDraftStore((s) => s.pushInsert);

  const [query, setQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editBody, setEditBody] = useState('');
  const [creating, setCreating] = useState(false);

  // One-time seed: the defaults are translated via i18n so they land in the
  // user's preferred language on first load.
  useEffect(() => {
    seedDefaults([
      {
        title: t('chat.workspace.snippets.defaults.summarize.title', {
          defaultValue: 'Summarize document',
        }),
        body: t('chat.workspace.snippets.defaults.summarize.body', {
          defaultValue:
            'Please read the attached document carefully and produce a concise summary covering the key points, decisions, and open questions.',
        }),
      },
      {
        title: t('chat.workspace.snippets.defaults.debug.title', {
          defaultValue: 'Debug error',
        }),
        body: t('chat.workspace.snippets.defaults.debug.body', {
          defaultValue:
            'I hit the following error. Walk me through the likely root causes and suggest the next debugging step:\n\n',
        }),
      },
      {
        title: t('chat.workspace.snippets.defaults.refactor.title', {
          defaultValue: 'Refactor snippet',
        }),
        body: t('chat.workspace.snippets.defaults.refactor.body', {
          defaultValue:
            'Refactor the snippet below for readability and correctness. Explain the rationale for each change:\n\n```\n\n```',
        }),
      },
    ]);
  }, [seedDefaults, t]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return snippets;
    return snippets.filter(
      (s) =>
        s.title.toLowerCase().includes(q) || s.body.toLowerCase().includes(q)
    );
  }, [snippets, query]);

  const startEdit = (snippet: PromptSnippet) => {
    setEditingId(snippet.id);
    setEditTitle(snippet.title);
    setEditBody(snippet.body);
  };

  const saveEdit = () => {
    if (!editingId) return;
    updateSnippet(editingId, { title: editTitle, body: editBody });
    setEditingId(null);
  };

  const saveNew = () => {
    if (!editTitle.trim() && !editBody.trim()) {
      setCreating(false);
      return;
    }
    addSnippet({ title: editTitle, body: editBody });
    setCreating(false);
    setEditTitle('');
    setEditBody('');
  };

  return (
    <div className="flex flex-col h-full min-h-0 gap-3 px-3 pb-3 overflow-y-auto">
      {/* Search + add */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground-tertiary" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('chat.workspace.snippets.searchPlaceholder', {
              defaultValue: 'Search snippets',
            })}
            className="w-full pl-8 pr-2 py-1.5 text-xs rounded-lg bg-surface-sunken border border-transparent focus:border-primary-400 focus:outline-none text-foreground placeholder:text-muted-foreground-tertiary"
          />
        </div>
        <Button
          type="button"
          size="sm"
          variant="primary"
          leftIcon={<Plus className="w-3.5 h-3.5" />}
          onClick={() => {
            setCreating(true);
            setEditTitle('');
            setEditBody('');
          }}
        >
          {t('chat.workspace.snippets.newAction', { defaultValue: 'New' })}
        </Button>
      </div>

      {creating && (
        <SnippetEditor
          title={editTitle}
          body={editBody}
          onTitleChange={setEditTitle}
          onBodyChange={setEditBody}
          onCancel={() => setCreating(false)}
          onSave={saveNew}
          autoFocus
        />
      )}

      {/* List */}
      {filtered.length === 0 && !creating ? (
        <div className="text-center py-10">
          <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-surface-sunken flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-muted-foreground-tertiary" />
          </div>
          <p className="text-xs text-muted-foreground">
            {query
              ? t('chat.workspace.snippets.emptySearch', {
                  defaultValue: 'No snippets match your search.',
                })
              : t('chat.workspace.snippets.empty', {
                  defaultValue: 'No snippets yet. Create one to reuse prompts quickly.',
                })}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((snippet) =>
            editingId === snippet.id ? (
              <SnippetEditor
                key={snippet.id}
                title={editTitle}
                body={editBody}
                onTitleChange={setEditTitle}
                onBodyChange={setEditBody}
                onCancel={() => setEditingId(null)}
                onSave={saveEdit}
                autoFocus
              />
            ) : (
              <div
                key={snippet.id}
                className="group flex flex-col gap-1.5 p-3 rounded-xl border border-border-subtle bg-surface-sunken/40 hover:border-border hover:bg-surface-sunken transition-colors"
              >
                <div className="flex items-start justify-between gap-2">
                  <h4 className="text-xs font-semibold text-foreground truncate flex-1">
                    {snippet.title}
                  </h4>
                  <div className="flex shrink-0 items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                    <button
                      type="button"
                      onClick={() => pushInsert(snippet.body)}
                      className="p-1 rounded-md text-primary-700 dark:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-900/30 transition-colors"
                      title={t('chat.workspace.snippets.insertAction', {
                        defaultValue: 'Insert into composer',
                      })}
                      aria-label={t('chat.workspace.snippets.insertAction', {
                        defaultValue: 'Insert into composer',
                      })}
                    >
                      <Send className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => startEdit(snippet)}
                      className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface transition-colors"
                      aria-label={t('chat.workspace.snippets.editAction', {
                        defaultValue: 'Edit',
                      })}
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteSnippet(snippet.id)}
                      className="p-1 rounded-md text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-surface transition-colors"
                      aria-label={t('chat.workspace.snippets.deleteAction', {
                        defaultValue: 'Delete',
                      })}
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
                <p className="text-[11px] text-muted-foreground whitespace-pre-wrap line-clamp-3">
                  {snippet.body}
                </p>
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}

interface SnippetEditorProps {
  title: string;
  body: string;
  onTitleChange: (value: string) => void;
  onBodyChange: (value: string) => void;
  onCancel: () => void;
  onSave: () => void;
  autoFocus?: boolean;
}

function SnippetEditor({
  title,
  body,
  onTitleChange,
  onBodyChange,
  onCancel,
  onSave,
  autoFocus,
}: SnippetEditorProps) {
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        'flex flex-col gap-2 p-3 rounded-xl border border-primary-300 dark:border-primary-600 bg-surface'
      )}
    >
      <input
        type="text"
        value={title}
        onChange={(e) => onTitleChange(e.target.value)}
        placeholder={t('chat.workspace.snippets.titlePlaceholder', {
          defaultValue: 'Snippet title',
        })}
        className="w-full px-2 py-1.5 text-xs font-semibold rounded-md bg-surface-sunken border border-transparent focus:border-primary-400 focus:outline-none text-foreground placeholder:text-muted-foreground-tertiary"
        autoFocus={autoFocus}
      />
      <textarea
        value={body}
        onChange={(e) => onBodyChange(e.target.value)}
        placeholder={t('chat.workspace.snippets.bodyPlaceholder', {
          defaultValue: 'Prompt body',
        })}
        rows={4}
        className="w-full px-2 py-1.5 text-xs rounded-md bg-surface-sunken border border-transparent focus:border-primary-400 focus:outline-none text-foreground placeholder:text-muted-foreground-tertiary resize-y"
      />
      <div className="flex items-center justify-end gap-1">
        <button
          type="button"
          onClick={onCancel}
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
          aria-label={t('common.cancel', { defaultValue: 'Cancel' })}
        >
          <X className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={onSave}
          className="p-1.5 rounded-md text-mint-600 dark:text-mint-400 hover:bg-mint-50 dark:hover:bg-mint-900/20 transition-colors"
          aria-label={t('common.save', { defaultValue: 'Save' })}
        >
          <Check className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
