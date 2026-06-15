import { Fragment, memo, useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import {
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Wrench,
  Loader2,
  Sparkles,
  AlertCircle,
  RotateCcw,
  GitFork,
  MessageCircleQuestion,
  ThumbsUp,
  ThumbsDown,
  Pin,
} from 'lucide-react';
import { cn, formatDate } from '@/lib/utils';
import { redactLargeRawToolArguments } from '@/lib/toolCallArgsDisplay';
import { isProjectFamilyTool } from '@/lib/projectToolEnvelope';
import { apiClient } from '@/api/client';
import { queryClient } from '@/lib/queryClient';
import { useChatStore } from '@/stores/chat';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { ChatAgentRolePet } from '@/components/chat/ChatAgentRolePet';
import { PetSpeechBubble } from '@/components/chat/PetSpeechBubble';
import { TypingIndicator } from './TypingIndicator';
import { TodoListBlock } from './TodoListBlock';
import { findLatestTodoAnchorMessageId, messageHasTodoActivity } from './todoAnchorUtils';
import { ArtifactCard } from './ArtifactCard';
import { AttachmentCard } from './AttachmentCard';
import { Markdown } from './markdown/Markdown';
import { useArtifactStore } from '@/stores/artifact';
import type { TFunction } from 'i18next';
import type {
  Attachment,
  Message,
  MessageUsage,
  PetBubblePayload,
  TaskProgressStep,
  ToolCall,
} from '@/types/chat';
import { ChatWorkflowCard } from './workflow/ChatWorkflowCard';
import { mergeWorkflowIntoTodos } from './workflow/workflowTodoSync';

const EMPTY_TODO_STEPS: TaskProgressStep[] = [];
import { GenUiInline } from '@/components/canvas/GenUiInline';
import {
  CanvasGenUiToolCall,
  isGenerativeCanvasTool,
} from '@/components/chat/CanvasGenUiToolCall';
import {
  ProjectToolCallBlock,
} from '@/components/chat/ProjectToolCallBlock';
import { useGenUiStore, genUiTreeKey } from '@/stores/genUi';
import { regenerateAssistantReply } from '@/lib/regenerateAssistantReply';

interface AgentMessageProps {
  message: Message;
  className?: string;
  /** Required to run workflow step actions from the card. */
  sessionId?: string | null;
  /** From parent thread list — avoids every row subscribing to the full message array on each SSE token. */
  precedingUserForRegenerate?: Message;
  /** Global `/chat/stream` busy — passed from parent so memoized rows still update at stream start/end. */
  streamActive: boolean;
}

/**
 * Memoized Markdown renderer — keyed by content so stable messages don't
 * re-parse while a sibling is streaming. Every `appendToMessage` would otherwise
 * re-run the full remark/rehype pipeline for every message on screen.
 */
function attachmentImageResolveKey(atts: Attachment[] | undefined): string {
  if (!atts?.length) return '';
  return atts
    .map((a) => `${a.id}\0${a.name}\0${a.previewUrl ?? ''}\0${a.downloadUrl ?? ''}\0${a.url ?? ''}`)
    .join('\n');
}

const RenderedMarkdown = memo(
  ({ content, attachments }: { content: string; attachments?: Attachment[] }) => (
    <Markdown content={content} imageAttachments={attachments} />
  ),
  (prev, next) =>
    prev.content === next.content &&
    attachmentImageResolveKey(prev.attachments) === attachmentImageResolveKey(next.attachments),
);
RenderedMarkdown.displayName = 'RenderedMarkdown';

const PET_AGENT_BUBBLE_MS = 9000;
const PET_CLICK_BUBBLE_MS = 6000;

const PET_CLICK_GREETING_KEYS = [
  'chat.petBubble.clickGreeting1',
  'chat.petBubble.clickGreeting2',
  'chat.petBubble.clickGreeting3',
  'chat.petBubble.clickGreeting4',
  'chat.petBubble.clickGreeting5',
  'chat.petBubble.clickGreeting6',
] as const;

function AssistantPetRailLink({
  className,
  agentBubble,
  onPickClickGreeting,
}: {
  className?: string;
  agentBubble?: Message['petBubble'];
  onPickClickGreeting: () => PetBubblePayload;
}) {
  const [clickBubble, setClickBubble] = useState<PetBubblePayload | null>(null);
  const [agentBubbleHidden, setAgentBubbleHidden] = useState(false);

  useEffect(() => {
    if (!agentBubble?.text) {
      setAgentBubbleHidden(false);
      return;
    }
    setAgentBubbleHidden(false);
    const id = window.setTimeout(() => setAgentBubbleHidden(true), PET_AGENT_BUBBLE_MS);
    return () => window.clearTimeout(id);
  }, [agentBubble?.text, agentBubble?.emoji]);

  useEffect(() => {
    if (!clickBubble) return;
    const id = window.setTimeout(() => setClickBubble(null), PET_CLICK_BUBBLE_MS);
    return () => window.clearTimeout(id);
  }, [clickBubble]);

  const onPetGreeting = useCallback(() => {
    setClickBubble(onPickClickGreeting());
  }, [onPickClickGreeting]);

  const showAgentBubble = Boolean(agentBubble?.text && !agentBubbleHidden);
  const displayBubble = clickBubble ?? (showAgentBubble ? agentBubble : null);

  return (
    <div className={cn('relative inline-block shrink-0 overflow-visible', className)}>
      {displayBubble?.text ? (
        <PetSpeechBubble
          text={displayBubble.text}
          emoji={displayBubble.emoji}
          layout="above-left"
          className="absolute bottom-full right-0 z-[2] mb-px -translate-y-px"
        />
      ) : null}
      <div className="chat-agent-pet-rail pointer-events-auto z-[1] overflow-visible">
        <span className={cn('chat-agent-pet-nest inline-flex overflow-visible rounded-lg')}>
          <ChatAgentRolePet variant="rail" onShowGreeting={onPetGreeting} />
        </span>
      </div>
    </div>
  );
}

function AgentMessageInner({
  message,
  className,
  sessionId,
  precedingUserForRegenerate,
  streamActive,
}: AgentMessageProps) {
  const { t } = useTranslation();

  const pickClickPetGreeting = useCallback((): PetBubblePayload => {
    const key =
      PET_CLICK_GREETING_KEYS[Math.floor(Math.random() * PET_CLICK_GREETING_KEYS.length)]!;
    return { text: t(key) };
  }, [t]);
  /** Per-message flag can stay true if an SSE event was skipped; gate on global stream too. */
  const assistantStreamingLive = Boolean(message.isStreaming && streamActive);
  const [copied, setCopied] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const feedbackLock = useRef(false);
  const artifacts = useArtifactStore((s) => s.artifacts);

  const messageArtifacts = Object.values(artifacts).filter(
    (a) => a.messageId === message.id,
  );
  const sortedTaskProgress = useMemo(() => {
    if (!message.taskProgress?.length) {
      return [];
    }
    return [...message.taskProgress].sort((a, b) => {
      const aOrder = a.order ?? Number.MAX_SAFE_INTEGER;
      const bOrder = b.order ?? Number.MAX_SAFE_INTEGER;
      if (aOrder !== bOrder) {
        return aOrder - bOrder;
      }
      return a.label.localeCompare(b.label);
    });
  }, [message.taskProgress]);

  const sessionTodos = useChatStore(
    useShallow((state) => {
      if (!sessionId) return EMPTY_TODO_STEPS;
      return state.sessions.find((s) => s.id === sessionId)?.todos ?? EMPTY_TODO_STEPS;
    }),
  );
  const todoPinned = useChatStore(
    (state) => Boolean(sessionId && state.sessionTodoUi[sessionId]?.pinned),
  );
  const setSessionTodoPinned = useChatStore((s) => s.setSessionTodoPinned);
  const patchSessionTodoStatus = useChatStore((s) => s.patchSessionTodoStatus);

  const latestTodoAnchorId = useChatStore((state) => {
    if (!sessionId) return null;
    return findLatestTodoAnchorMessageId(state.messages[sessionId] ?? []);
  });

  const isTodoAnchorMessage = message.id === latestTodoAnchorId;

  const workflowOverlayRevision = useExecutionOverlay(
    useShallow((state) => {
      const stepRuns = message.workflow?.stepRuns;
      if (!stepRuns) return 0;
      let rev = 0;
      for (const run of Object.values(stepRuns)) {
        const promptId = run.prompt_id;
        if (!promptId) continue;
        const overlay = state.overlays[promptId];
        if (!overlay) continue;
        rev += (overlay.running ? 1 : 0) + overlay.errors.length * 3 + (overlay.blocked ? 5 : 0);
      }
      return rev;
    }),
  );

  const inlineTodoSteps = useMemo(() => {
    if (!isTodoAnchorMessage || !messageHasTodoActivity(message)) {
      return [];
    }
    const base = sessionTodos.length > 0 ? sessionTodos : sortedTaskProgress;
    if (message.workflow?.spec.steps.length) {
      return mergeWorkflowIntoTodos(
        message.workflow.spec.steps,
        message.workflow.stepRuns,
        base,
      );
    }
    return base;
  }, [
    isTodoAnchorMessage,
    message,
    sessionTodos,
    sortedTaskProgress,
    workflowOverlayRevision,
  ]);

  const todoInteractive = Boolean(
    sessionId &&
      isTodoAnchorMessage &&
      messageHasTodoActivity(message) &&
      inlineTodoSteps.length > 0,
  );

  const handleTodoStatusChange = useCallback(
    (taskId: string, status: TaskProgressStep['status']) => {
      if (!sessionId) return Promise.resolve();
      return patchSessionTodoStatus(sessionId, taskId, status);
    },
    [patchSessionTodoStatus, sessionId],
  );

  const genUiSourceToolCallId = useGenUiStore((s) =>
    sessionId ? s.sourceToolCallByMessage[genUiTreeKey(sessionId, message.id)] : undefined,
  );

  const lastSuccessfulEmitUiTreeIndex = useMemo(() => {
    const tcs = message.toolCalls;
    if (!Array.isArray(tcs) || tcs.length === 0) return -1;
    let idx = -1;
    tcs.forEach((tc, i) => {
      if (tc.name === 'emit_ui_tree' && tc.status === 'success') idx = i;
    });
    return idx;
  }, [message.toolCalls]);

  const showAnchoredGenUi =
    Boolean(sessionId) &&
    lastSuccessfulEmitUiTreeIndex >= 0 &&
    message.toolCalls?.some((tc, i) => {
      if (tc.name !== 'emit_ui_tree' || tc.status !== 'success') return false;
      if (genUiSourceToolCallId) return tc.id === genUiSourceToolCallId;
      return i === lastSuccessfulEmitUiTreeIndex;
    });

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [message.content]);

  const patchRating = useCallback(
    async (next: number | null) => {
      if (!sessionId || feedbackLock.current) return;
      feedbackLock.current = true;
      setFeedbackBusy(true);
      try {
        await apiClient.patch<{ ok?: boolean }>(
          `/chat/sessions/${sessionId}/messages/${message.id}/feedback`,
          { rating: next },
        );
        useChatStore.getState().updateMessage(sessionId, message.id, {
          rating: next === null ? undefined : next,
        });
        void queryClient.invalidateQueries({ queryKey: ['agent-memory', sessionId] });
        void queryClient.invalidateQueries({ queryKey: ['prompt-preview', sessionId] });
      } finally {
        feedbackLock.current = false;
        setFeedbackBusy(false);
      }
    },
    [sessionId, message.id],
  );

  const onThumbsUp = useCallback(() => {
    void patchRating(message.rating === 5 ? null : 5);
  }, [message.rating, patchRating]);

  const onThumbsDown = useCallback(() => {
    void patchRating(message.rating === 1 ? null : 1);
  }, [message.rating, patchRating]);

  const canRegenerate = Boolean(
    sessionId &&
      !assistantStreamingLive &&
      precedingUserForRegenerate &&
      (precedingUserForRegenerate.content?.trim() ||
        precedingUserForRegenerate.attachments?.length),
  );

  const handleRegenerate = useCallback(async () => {
    if (!canRegenerate) return;
    await regenerateAssistantReply({ assistantMessageId: message.id, t });
  }, [canRegenerate, message.id, t]);

  const hasAssistantActions = Boolean(
    !assistantStreamingLive &&
      (message.content?.trim() ||
        message.toolCalls?.length ||
        inlineTodoSteps.length ||
        message.workflow ||
        message.workflowEmbed ||
        messageArtifacts.length ||
        message.attachments?.length),
  );

  /** Pet rail must stay mounted whenever the row shows other assistant UI; otherwise tool-only turns hide the mascot and bubbles. */
  const showAssistantPetRail = Boolean(
    assistantStreamingLive ||
      message.isStreaming ||
      Boolean(message.content) ||
      Boolean(message.petBubble?.text) ||
      inlineTodoSteps.length > 0 ||
      Boolean(message.toolCalls?.length) ||
      Boolean(message.thinking?.trim()) ||
      Boolean(message.workflow || message.workflowEmbed) ||
      Boolean(message.genUiReplay) ||
      messageArtifacts.length > 0 ||
      (message.attachments?.length ?? 0) > 0,
  );

  return (
    <article
      data-message-id={message.id}
      className={cn('group relative', className)}
      aria-label={t('chat.roleAssistantAria', { defaultValue: 'Assistant message' })}
    >
      {showAssistantPetRail && (
        <AssistantPetRailLink
          className="absolute -left-20 top-0"
          agentBubble={message.petBubble}
          onPickClickGreeting={pickClickPetGreeting}
        />
      )}

      {/* Role label + timestamp (time moved out of action row) */}
      <div className="chat-role-label relative z-[2]">
        <span className="chat-role-dot" aria-hidden />
        <span>{t('chat.roleAssistantShort', { defaultValue: 'Assistant' })}</span>
        <span
          className="chat-msg-time normal-case font-normal tracking-normal tabular-nums"
          title={formatDate(message.createdAt)}
        >
          {formatDate(message.createdAt)}
        </span>
      </div>

      {/* Thinking block — show when reasoning arrived, or while waiting for any first output */}
      {(message.thinking ||
        (assistantStreamingLive && !message.content)) && (
        <ThinkingBlock
          thought={message.thinking}
          isStreaming={assistantStreamingLive}
          reasoningTokens={message.usage?.reasoning_tokens}
          className="mb-3"
        />
      )}

      {/* Tool calls — hide emit_pet_bubble (pet caption is shown beside the mascot only). */}
      {Array.isArray(message.toolCalls) &&
        message.toolCalls.some((tc) => tc.name !== 'emit_pet_bubble') && (
        <div className="space-y-1.5 mb-3">
          {buildToolCallSegments(message.toolCalls).map((seg, segIdx) =>
            seg.kind === 'tool_strip' ? (
              <ToolCallStrip
                key={`tool-strip-${message.id}-${segIdx}-${seg.tools[0]?.id ?? segIdx}`}
                tools={seg.tools}
              />
            ) : (
              <Fragment key={`tool-other-${seg.toolCall.id}-${seg.index}`}>
                {isGenerativeCanvasTool(seg.toolCall.name) ? (
                  <CanvasGenUiToolCall
                    toolCall={seg.toolCall}
                    sessionId={sessionId}
                    messageId={message.id}
                    showGenUiInline={
                      Boolean(sessionId) &&
                      seg.toolCall.name === 'emit_ui_tree' &&
                      seg.toolCall.status === 'success' &&
                      (genUiSourceToolCallId
                        ? seg.toolCall.id === genUiSourceToolCallId
                        : seg.index === lastSuccessfulEmitUiTreeIndex)
                    }
                  />
                ) : (
                  <ProjectToolCallBlock toolCall={seg.toolCall} sessionId={sessionId} />
                )}
              </Fragment>
            ),
          )}
        </div>
      )}

      {/* Task/todo list inline in agent response */}
      {inlineTodoSteps.length > 0 ? (
        <TodoListBlock
          steps={inlineTodoSteps}
          isStreaming={assistantStreamingLive}
          variant="inline"
          interactive={todoInteractive}
          sessionId={sessionId ?? undefined}
          onStatusChange={handleTodoStatusChange}
          showPin={Boolean(sessionId && !todoPinned)}
          onPin={sessionId ? () => setSessionTodoPinned(sessionId, true) : undefined}
          className="mb-3"
        />
      ) : null}

      {(message.workflow || message.workflowEmbed) && sessionId ? (
        <ChatWorkflowCard message={message} sessionId={sessionId} className="mb-3" />
      ) : null}

      {/* Main content — pet in left gutter via -ml/pl so .chat-prose text measure matches no-pet layout */}
      {message.content ? (
        <div className="relative -ml-20 w-[calc(100%+5rem)] pl-20">
          <div className="chat-prose w-full min-w-0">
            <RenderedMarkdown content={message.content} attachments={message.attachments} />
            {assistantStreamingLive && (
              <span
                className="inline-block w-0.5 h-[1em] bg-primary-500 animate-pulse ml-0.5 align-text-bottom"
                aria-hidden
              />
            )}
          </div>
        </div>
      ) : assistantStreamingLive ? (
        <div className="relative -ml-20 w-[calc(100%+5rem)] pl-20">
          <div className="w-full min-w-0">
            <TypingIndicator />
          </div>
        </div>
      ) : null}

      {sessionId && !showAnchoredGenUi ? (
        <GenUiInline sessionId={sessionId} messageId={message.id} />
      ) : null}

      {/* Artifacts */}
      {messageArtifacts.length > 0 && (
        <div className="mt-3 space-y-2">
          {messageArtifacts.map((artifact) => (
            <ArtifactCard key={artifact.id} artifact={artifact} />
          ))}
        </div>
      )}

      {Array.isArray(message.attachments) && message.attachments.length > 0 && (
        <div className="mt-3 flex flex-wrap items-start gap-2">
          {message.attachments.map((attachment) => (
            <AttachmentCard key={attachment.id} attachment={attachment} />
          ))}
        </div>
      )}

      {hasAssistantActions ? (
        <AssistantMessageActions
          copied={copied}
          canCopy={Boolean(message.content?.trim())}
          feedbackBusy={feedbackBusy}
          rating={message.rating ?? undefined}
          sessionId={sessionId}
          messageId={message.id}
          t={t}
          onCopy={handleCopy}
          onThumbsDown={onThumbsDown}
          onThumbsUp={onThumbsUp}
          onRegenerate={handleRegenerate}
          regenerateDisabled={!canRegenerate || streamActive}
        />
      ) : null}

      {!assistantStreamingLive && message.usage && message.usage.total_tokens > 0 && (
        <UsageStats usage={message.usage} />
      )}
    </article>
  );
}

AgentMessageInner.displayName = 'AgentMessage';

export const AgentMessage = memo(AgentMessageInner);

interface AssistantMessageActionsProps {
  copied: boolean;
  canCopy: boolean;
  feedbackBusy: boolean;
  rating?: number;
  sessionId?: string | null;
  messageId: string;
  t: TFunction;
  onCopy: () => void;
  onThumbsDown: () => void;
  onThumbsUp: () => void;
  onRegenerate: () => void;
  regenerateDisabled: boolean;
}

function AssistantMessageActions({
  copied,
  canCopy,
  feedbackBusy,
  rating,
  sessionId,
  messageId,
  t,
  onCopy,
  onThumbsDown,
  onThumbsUp,
  onRegenerate,
  regenerateDisabled,
}: AssistantMessageActionsProps) {
  const togglePinMessage = useChatStore((s) => s.togglePinMessage);
  const isPinned = useChatStore((s) => {
    if (!sessionId) return false;
    const sess = s.sessions.find((x) => x.id === sessionId);
    return sess?.pinnedMessageIds?.includes(messageId) ?? false;
  });

  return (
    <div
      className={cn(
        'chat-msg-actions mt-2 flex flex-wrap items-center gap-0.5',
        rating && 'chat-msg-actions--selected',
      )}
    >
      {sessionId ? (
        <button
          type="button"
          onClick={() => void togglePinMessage(sessionId, messageId)}
          className={cn(
            'p-1.5 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors',
            isPinned && 'text-primary-600 dark:text-primary-400',
          )}
          aria-label={
            isPinned
              ? t('chat.pins.unpin', { defaultValue: 'Unpin message' })
              : t('chat.pins.pin', { defaultValue: 'Pin message' })
          }
          title={
            isPinned
              ? t('chat.pins.unpin', { defaultValue: 'Unpin message' })
              : t('chat.pins.pin', { defaultValue: 'Pin message' })
          }
        >
          <Pin className={cn('w-3.5 h-3.5', isPinned && 'fill-current')} aria-hidden />
        </button>
      ) : null}
      <button
        type="button"
        onClick={onThumbsUp}
        disabled={!sessionId || feedbackBusy}
        className={cn(
          'p-1.5 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
          rating === 5
            ? 'text-mint-600 bg-mint-500/10'
            : 'text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken',
        )}
        aria-label={t('chat.feedbackLike', { defaultValue: 'Good response' })}
        title={t('chat.feedbackLike', { defaultValue: 'Good response' })}
      >
        <ThumbsUp className="w-3.5 h-3.5" />
      </button>
      <button
        type="button"
        onClick={onThumbsDown}
        disabled={!sessionId || feedbackBusy}
        className={cn(
          'p-1.5 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
          rating === 1
            ? 'text-amber-600 bg-amber-500/10'
            : 'text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken',
        )}
        aria-label={t('chat.feedbackDislike', { defaultValue: 'Bad response' })}
        title={t('chat.feedbackDislike', { defaultValue: 'Bad response' })}
      >
        <ThumbsDown className="w-3.5 h-3.5" />
      </button>
      {canCopy ? (
        <button
          type="button"
          onClick={onCopy}
          className="p-1.5 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors"
          aria-label={t('common.copy', { defaultValue: 'Copy' })}
          title={copied ? t('chat.copied') : t('chat.copy')}
        >
          {copied ? (
            <Check className="w-3.5 h-3.5 text-mint-500" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
        </button>
      ) : null}
      <button
        type="button"
        onClick={onRegenerate}
        disabled={regenerateDisabled}
        className={cn(
          'p-1.5 rounded-md transition-colors',
          regenerateDisabled
            ? 'opacity-40 cursor-not-allowed text-muted-foreground-tertiary'
            : 'text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken',
        )}
        aria-label={t('chat.regenerate', { defaultValue: 'Regenerate' })}
        title={t('chat.regenerate', { defaultValue: 'Regenerate' })}
      >
        <RotateCcw className="w-3.5 h-3.5" />
      </button>
      <button
        type="button"
        className="p-1.5 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors"
        aria-label={t('chat.branch', { defaultValue: 'Branch' })}
        title={t('chat.branch', { defaultValue: 'Branch' })}
      >
        <GitFork className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

/* ── Usage stats ── */
function UsageStats({ usage }: { usage: MessageUsage }) {
  const { t } = useTranslation();
  const parts: string[] = [];
  if (usage.prompt_tokens > 0) {
    parts.push(
      t('chat.usagePrompt', {
        count: usage.prompt_tokens,
        defaultValue: '{{count}} prompt',
      }),
    );
  }
  if (usage.completion_tokens > 0) {
    parts.push(
      t('chat.usageCompletion', {
        count: usage.completion_tokens,
        defaultValue: '{{count}} completion',
      }),
    );
  }
  if (usage.reasoning_tokens && usage.reasoning_tokens > 0) {
    parts.push(
      t('chat.usageReasoning', {
        count: usage.reasoning_tokens,
        defaultValue: '{{count}} reasoning',
      }),
    );
  }
  return (
    <div className="mt-1.5 flex items-center gap-1 text-[10px] tabular-nums text-muted-foreground-tertiary select-none">
      <span>{usage.total_tokens.toLocaleString()} tokens</span>
      {parts.length > 0 && (
        <span className="text-border">({parts.join(' · ')})</span>
      )}
    </div>
  );
}

/* ── Thinking block ── */
interface ThinkingBlockProps {
  thought?: string;
  isStreaming?: boolean;
  reasoningTokens?: number;
  className?: string;
}

function ThinkingBlock({
  thought,
  isStreaming = true,
  reasoningTokens,
  className,
}: ThinkingBlockProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const titleKey =
    thought && !isStreaming ? 'chat.thinkingSummary' : 'chat.thinkingInline';

  return (
    <div
      className={cn(
        'rounded-lg border border-border-subtle bg-muted/25 dark:bg-muted/15',
        'text-xs text-muted-foreground',
        className,
      )}
    >
      <button
        type="button"
        className="w-full flex items-center gap-2 px-2.5 py-2 text-left"
        onClick={() => thought && setExpanded(!expanded)}
        aria-expanded={Boolean(thought && expanded)}
      >
        {isStreaming ? (
          <Loader2
            className={cn(
              'h-3.5 w-3.5 text-muted-foreground-tertiary flex-shrink-0',
              'animate-spin',
            )}
            aria-hidden
          />
        ) : (
          <Sparkles className="h-3.5 w-3.5 text-muted-foreground-tertiary flex-shrink-0" aria-hidden />
        )}
        <span
          className={cn(
            'flex-1 font-medium text-muted-foreground text-xs leading-snug',
            isStreaming && 'italic',
          )}
        >
          {t(titleKey)}
        </span>
        {!isStreaming && reasoningTokens != null && reasoningTokens > 0 && (
          <span className="shrink-0 tabular-nums text-[10px] text-muted-foreground-tertiary">
            {reasoningTokens.toLocaleString()} tokens
          </span>
        )}
        {thought &&
          (expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground-tertiary flex-shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground-tertiary flex-shrink-0" />
          ))}
      </button>
      {expanded && thought && (
        <div className="px-2.5 pb-2.5">
          <div className="rounded-md border border-border-subtle/80 bg-surface-sunken/50 p-2 overflow-x-auto max-h-64 overflow-y-auto">
            <div className="text-[11px] leading-relaxed text-muted-foreground [&_p]:my-1 [&_code]:text-[10px] [&_code]:bg-surface-sunken [&_code]:px-1 [&_code]:rounded">
              <Markdown content={thought} />
            </div>
          </div>
        </div>
      )}
      {isStreaming && thought && !expanded && (
        <div className="px-2.5 pb-2 -mt-0.5">
          <p className="text-[10px] text-muted-foreground-tertiary italic truncate">
            {thought.slice(-120)}
          </p>
        </div>
      )}
    </div>
  );
}

/* ── ask_user: structured Q&A in expanded tool bubble ── */

type AskUserQuestionRow = { id: string; prompt: string; choices?: string[] };

function coerceRecord(v: unknown): Record<string, unknown> | null {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null;
  return v as Record<string, unknown>;
}

function parseAskUserQuestionsFromArgs(args: unknown): AskUserQuestionRow[] {
  const rec = coerceRecord(args);
  if (!rec) return [];
  let qs: unknown = rec.questions;
  if (typeof qs === 'string') {
    try {
      qs = JSON.parse(qs);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(qs)) return [];
  const out: AskUserQuestionRow[] = [];
  for (const item of qs) {
    const o = coerceRecord(item);
    if (!o) continue;
    const id = typeof o.id === 'string' ? o.id.trim() : '';
    const prompt = typeof o.prompt === 'string' ? o.prompt.trim() : '';
    if (!id || !prompt) continue;
    const row: AskUserQuestionRow = { id, prompt };
    if (Array.isArray(o.choices)) {
      const choices = o.choices.filter(
        (c): c is string => typeof c === 'string' && c.trim().length > 0,
      );
      if (choices.length) row.choices = choices;
    }
    out.push(row);
  }
  return out;
}

function parseAskUserAnswersFromResult(result: unknown): Record<string, string | string[]> | null {
  if (result == null) return null;
  let cur: unknown = result;
  if (typeof cur === 'string') {
    try {
      cur = JSON.parse(cur);
    } catch {
      return null;
    }
  }
  const top = coerceRecord(cur);
  if (!top) return null;
  if (top._wa_pending === true) return null;

  let payload: Record<string, unknown> | null = top;
  const dataWrap = coerceRecord(top.data);
  if (dataWrap) {
    payload = dataWrap;
  }
  if (!payload) return null;

  let answersRaw: unknown = payload.answers;
  const nested = coerceRecord(payload.data);
  if (answersRaw == null && nested?.answers != null) {
    answersRaw = nested.answers;
  }
  if (!answersRaw || typeof answersRaw !== 'object' || Array.isArray(answersRaw)) return null;

  const ar = answersRaw as Record<string, unknown>;
  const out: Record<string, string | string[]> = {};
  for (const [k, v] of Object.entries(ar)) {
    if (v == null) continue;
    if (Array.isArray(v)) {
      const strings = v.filter((x): x is string => typeof x === 'string');
      if (strings.length) out[k] = strings;
    } else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
      out[k] = String(v);
    }
  }
  return Object.keys(out).length > 0 ? out : null;
}

function formatAskUserAnswerValue(v: string | string[]): string {
  if (Array.isArray(v)) return v.map((x) => x.trim()).filter(Boolean).join(', ');
  return v.trim();
}

type ToolCallSegment =
  | { kind: 'tool_strip'; tools: ToolCall[] }
  | { kind: 'other'; toolCall: ToolCall; index: number };

function buildToolCallSegments(toolCalls: ToolCall[] | undefined): ToolCallSegment[] {
  if (!Array.isArray(toolCalls) || toolCalls.length === 0) return [];
  const out: ToolCallSegment[] = [];
  let buf: ToolCall[] = [];
  const flush = () => {
    if (buf.length) {
      out.push({ kind: 'tool_strip', tools: buf });
      buf = [];
    }
  };
  for (let i = 0; i < toolCalls.length; i++) {
    const tc = toolCalls[i];
    if (!tc) continue;
    if (tc.name === 'emit_pet_bubble') continue;
    if (!isGenerativeCanvasTool(tc.name) && !isProjectFamilyTool(tc.name)) {
      buf.push(tc);
    } else {
      flush();
      out.push({ kind: 'other', toolCall: tc, index: i });
    }
  }
  flush();
  return out;
}

/* ── Tool call strip (generic tools only) ── */
function toolCallNameFallback(name: string): string {
  if (!name) return '';
  return name
    .split(/_+/g)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

function toolCallStatusPresentation(status: ToolCall['status']) {
  const statusConfig = {
    pending: {
      icon: (
        <Loader2 className="h-3.5 w-3.5 text-muted-foreground-tertiary animate-spin" />
      ),
      border: 'border-border-subtle',
      bg: '',
    },
    running: {
      icon: <Loader2 className="h-3.5 w-3.5 text-sky-500 animate-spin" />,
      border: 'border-sky-200 dark:border-sky-800',
      bg: 'bg-sky-50/40 dark:bg-sky-900/10',
    },
    awaiting_user: {
      icon: (
        <MessageCircleQuestion
          className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400"
          aria-hidden
        />
      ),
      border: 'border-amber-200 dark:border-amber-800',
      bg: 'bg-amber-50/40 dark:bg-amber-900/10',
    },
    success: {
      icon: <Check className="h-3.5 w-3.5 text-mint-500" />,
      border: 'border-mint-200 dark:border-mint-800',
      bg: 'bg-mint-50/40 dark:bg-mint-900/10',
    },
    error: {
      icon: <AlertCircle className="h-3.5 w-3.5 text-red-500" />,
      border: 'border-red-200 dark:border-red-800',
      bg: 'bg-red-50/40 dark:bg-red-900/10',
    },
  };
  return statusConfig[status];
}

function ToolCallDetailsPane({ toolCall }: { toolCall: ToolCall }) {
  const { t } = useTranslation();

  const askUserQuestions = useMemo(
    () => (toolCall.name === 'ask_user' ? parseAskUserQuestionsFromArgs(toolCall.arguments) : []),
    [toolCall.name, toolCall.arguments],
  );
  const askUserAnswers = useMemo(
    () => (toolCall.name === 'ask_user' ? parseAskUserAnswersFromResult(toolCall.result) : null),
    [toolCall.name, toolCall.result],
  );
  const showAskUserStructured =
    toolCall.name === 'ask_user' &&
    (askUserQuestions.length > 0 || askUserAnswers !== null);

  const displayArguments = useMemo(
    () => redactLargeRawToolArguments(toolCall.arguments, t),
    [toolCall.arguments, t],
  );

  const formatValue = (value: unknown): string =>
    typeof value === 'string' ? value : JSON.stringify(value, null, 2);

  const askUserHistoryBlocks = (tf: TFunction) => {
    const answers = askUserAnswers;
    const orderedIds =
      askUserQuestions.length > 0
        ? askUserQuestions.map((q) => q.id)
        : answers
          ? Object.keys(answers)
          : [];
    const extraIds =
      answers && askUserQuestions.length > 0
        ? Object.keys(answers).filter((id) => !askUserQuestions.some((q) => q.id === id))
        : [];

    return (
      <div className="space-y-3">
        {askUserQuestions.length > 0 && (
          <div>
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {tf('chat.askUserTool.questionsTitle')}
            </div>
            <ul className="list-none space-y-2 p-0 m-0">
              {askUserQuestions.map((q) => (
                <li
                  key={q.id}
                  className="rounded-md border border-border-subtle bg-surface-sunken/60 px-2.5 py-2"
                >
                  <p className="text-[11px] font-medium text-foreground leading-snug">{q.prompt}</p>
                  {q.choices && q.choices.length > 0 && (
                    <p className="mt-1 text-[10px] text-muted-foreground-tertiary">
                      {tf('chat.askUserTool.choicesHint')}: {q.choices.join(' · ')}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            {tf('chat.askUserTool.answersTitle')}
          </div>
          {!answers || Object.keys(answers).length === 0 ? (
            <p className="text-[11px] text-muted-foreground-tertiary italic">
              {tf('chat.askUserTool.noAnswersYet')}
            </p>
          ) : (
            <ul className="list-none space-y-2 p-0 m-0">
              {orderedIds.map((qid) => {
                const q = askUserQuestions.find((x) => x.id === qid);
                const label =
                  q?.prompt ??
                  tf('chat.askUserTool.unknownQuestion', { id: qid, defaultValue: `Question ${qid}` });
                const raw = answers[qid];
                const line =
                  raw !== undefined && raw !== ''
                    ? formatAskUserAnswerValue(Array.isArray(raw) ? raw : String(raw))
                    : '—';
                return (
                  <li
                    key={qid}
                    className="rounded-md border border-border-subtle bg-surface-sunken/60 px-2.5 py-2"
                  >
                    <p className="text-[10px] font-medium text-muted-foreground leading-snug">{label}</p>
                    <p className="mt-0.5 text-[11px] text-foreground whitespace-pre-wrap break-words">
                      {line}
                    </p>
                  </li>
                );
              })}
              {extraIds.map((qid) => {
                const raw = answers![qid];
                const line = formatAskUserAnswerValue(Array.isArray(raw) ? raw : String(raw));
                return (
                  <li
                    key={`extra-${qid}`}
                    className="rounded-md border border-border-subtle bg-surface-sunken/60 px-2.5 py-2"
                  >
                    <p className="text-[10px] font-medium text-muted-foreground leading-snug">
                      {tf('chat.askUserTool.unknownQuestion', { id: qid, defaultValue: `Question ${qid}` })}
                    </p>
                    <p className="mt-0.5 text-[11px] text-foreground whitespace-pre-wrap break-words">
                      {line}
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <details className="group/raw rounded-md border border-border-subtle/80 bg-surface-sunken/40">
          <summary className="cursor-pointer select-none px-2 py-1.5 text-[10px] font-medium text-muted-foreground hover:text-foreground">
            {tf('chat.askUserTool.rawDetails')}
          </summary>
          <div className="space-y-2 border-t border-border-subtle/60 px-2 py-2">
            <pre className="no-scrollbar max-h-32 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] text-foreground">
              {formatValue(displayArguments)}
            </pre>
            {toolCall.result !== undefined && (
              <pre className="no-scrollbar max-h-32 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] text-foreground">
                {formatValue(toolCall.result)}
              </pre>
            )}
          </div>
        </details>
      </div>
    );
  };

  return (
    <div className="space-y-2">
      {showAskUserStructured ? (
        askUserHistoryBlocks(t)
      ) : (
        <>
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {t('chat.toolParameters')}
            </div>
            <div className="no-scrollbar overflow-x-auto rounded-md bg-surface-sunken p-2">
              <pre className="whitespace-pre-wrap font-mono text-[11px] text-foreground">
                {formatValue(displayArguments)}
              </pre>
            </div>
          </div>

          {toolCall.result !== undefined && (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t('chat.toolResult')}
              </div>
              <div className="no-scrollbar overflow-x-auto rounded-md bg-surface-sunken p-2">
                <pre className="whitespace-pre-wrap font-mono text-[11px] text-foreground">
                  {formatValue(toolCall.result)}
                </pre>
              </div>
            </div>
          )}
        </>
      )}

      {toolCall.error && (
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-red-500">
            {t('chat.toolError')}
          </div>
          <div className="rounded-md bg-red-50 p-2 dark:bg-red-900/20">
            <pre className="whitespace-pre-wrap font-mono text-[11px] text-red-600 dark:text-red-400">
              {toolCall.error}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

interface ToolCallChipProps {
  /** 1-based index within the tool strip (display only). */
  sequenceIndex: number;
  toolCall: ToolCall;
  expanded: boolean;
  onToggle: () => void;
}

function ToolCallChip({ sequenceIndex, toolCall, expanded, onToggle }: ToolCallChipProps) {
  const { t } = useTranslation();
  const toolDisplayName = t(`chat.toolNames.${toolCall.name}`, {
    defaultValue: toolCallNameFallback(toolCall.name),
  });
  const config = toolCallStatusPresentation(toolCall.status);

  return (
    <div
      className={cn(
        'flex-shrink-0 text-xs transition-colors rounded-lg border max-w-[14rem] min-w-[8.25rem]',
        expanded
          ? 'border-primary-300/80 bg-primary-50/90 dark:border-primary-600/45 dark:bg-primary-950/35'
          : cn(config.border, config.bg),
      )}
    >
      <button
        type="button"
        className={cn(
          'flex h-7 w-full max-w-[14rem] items-center gap-1 rounded-md px-1.5 py-1 text-left outline-none transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          expanded && 'text-primary-800 dark:text-primary-200',
        )}
        onClick={onToggle}
        aria-expanded={expanded}
        aria-pressed={expanded}
      >
        <span
          className={cn(
            'flex h-4 min-w-[1.125rem] shrink-0 items-center justify-center rounded px-0.5 font-mono text-[10px] font-semibold tabular-nums leading-none',
            expanded
              ? 'bg-primary-200/70 text-primary-900 dark:bg-primary-800/60 dark:text-primary-100'
              : 'bg-muted/60 text-muted-foreground-tertiary dark:bg-muted/40',
          )}
          aria-hidden
        >
          {sequenceIndex}
        </span>
        <Wrench
          className={cn(
            'h-3 w-3 flex-shrink-0',
            expanded ? 'text-primary-600 dark:text-primary-400' : 'text-muted-foreground',
          )}
          aria-hidden
        />
        <span
          className={cn(
            'min-w-0 flex-1 truncate font-medium',
            expanded ? 'text-primary-800 dark:text-primary-200' : 'text-foreground',
          )}
        >
          {toolDisplayName}
        </span>
        {toolCall.duration_ms !== undefined &&
          toolCall.status !== 'running' &&
          toolCall.status !== 'awaiting_user' && (
            <span className="mr-0.5 shrink-0 tabular-nums text-[10px] text-muted-foreground-tertiary">
              {toolCall.duration_ms}ms
            </span>
          )}
        {config.icon}
      </button>
    </div>
  );
}

function ToolCallStrip({ tools }: { tools: ToolCall[] }) {
  const { t } = useTranslation();
  const [activeDetailId, setActiveDetailId] = useState<string | null>(null);
  const [panelExpanded, setPanelExpanded] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth + 1) return;
      if (e.deltaY) {
        el.scrollLeft += e.deltaY;
        e.preventDefault();
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  useEffect(() => {
    if (activeDetailId && !tools.some((tc) => tc.id === activeDetailId)) {
      setActiveDetailId(null);
    }
  }, [tools, activeDetailId]);

  const selectChip = useCallback((id: string) => {
    setActiveDetailId((prev) => {
      const next = prev === id ? null : id;
      if (next !== null) setPanelExpanded(true);
      return next;
    });
  }, []);

  const activeTool = activeDetailId
    ? tools.find((tc) => tc.id === activeDetailId)
    : undefined;

  const togglePanel = useCallback(() => {
    setPanelExpanded((open) => !open);
  }, []);

  const showDetails = Boolean(activeTool && panelExpanded);

  return (
    <div className="space-y-1.5 rounded-lg border border-border-subtle bg-muted/25 px-1.5 py-1.5 dark:bg-muted/15">
      <div className="flex min-h-7 min-w-0 items-center gap-1.5">
        <button
          type="button"
          disabled={!activeTool}
          className={cn(
            'flex h-7 w-8 shrink-0 items-center justify-center rounded-md border-0',
            'bg-background/60 text-muted-foreground transition-colors',
            'hover:bg-muted/40 hover:text-foreground',
            'disabled:pointer-events-none disabled:opacity-40',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/45 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          )}
          onClick={togglePanel}
          aria-expanded={showDetails}
          aria-label={t('chat.toolStrip.toggleDetailsAria')}
        >
          {showDetails ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground-tertiary flex-shrink-0" aria-hidden />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground-tertiary flex-shrink-0" aria-hidden />
          )}
        </button>
        <div
          ref={scrollRef}
          className="no-scrollbar flex min-h-7 min-w-0 flex-1 items-stretch gap-1.5 overflow-x-auto overflow-y-visible"
        >
          {tools.map((tc, index) => (
            <ToolCallChip
              key={tc.id}
              sequenceIndex={index + 1}
              toolCall={tc}
              expanded={activeDetailId === tc.id}
              onToggle={() => selectChip(tc.id)}
            />
          ))}
        </div>
      </div>

      {showDetails && activeTool ? (
        <div
          className={cn(
            'no-scrollbar max-h-[min(50vh,22rem)] overflow-y-auto overscroll-contain rounded-md border border-border-subtle/80',
            'bg-surface-sunken/40 px-2 py-2 dark:bg-muted/10',
          )}
        >
          <ToolCallDetailsPane toolCall={activeTool} />
        </div>
      ) : null}
    </div>
  );
}
