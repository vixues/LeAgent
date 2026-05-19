import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleDot,
  Clock,
  ListChecks,
  RefreshCcw,
  Square,
  XCircle,
} from 'lucide-react';

import { PageShell } from '@/components/layout/PageShell';
import { PageLoader } from '@/components/common/PageLoader';
import { EmptyState } from '@/components/common/EmptyState';
import { Badge, Button, Card, CardContent, Input, Select, Textarea } from '@/components/ui';
import {
  useCancelUserTask,
  useCreateAgentRun,
  useKillUserTask,
  useTaskOutput,
  useUserTask,
  useUserTasks,
} from '@/hooks/useTasks';
import type { Task, TaskPriority, TaskStatus, TaskType } from '@/types/admin';
import { cn, formatDate, formatRelativeTime } from '@/lib/utils';

const STATUS_OPTIONS: Array<{ value: TaskStatus | 'all'; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'killed', label: 'Killed' },
  { value: 'timeout', label: 'Timeout' },
];

const TYPE_OPTIONS: Array<{ value: TaskType | 'all'; label: string }> = [
  { value: 'all', label: 'All types' },
  { value: 'agent', label: 'Agent' },
  { value: 'shell', label: 'Shell' },
  { value: 'workflow', label: 'Workflow' },
  { value: 'tool', label: 'Tool' },
  { value: 'batch', label: 'Batch' },
  { value: 'dream', label: 'Dream' },
];

const PRIORITY_OPTIONS: Array<{ value: TaskPriority | 'all'; label: string }> = [
  { value: 'all', label: 'All priorities' },
  { value: 'low', label: 'Low' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'High' },
  { value: 'urgent', label: 'Urgent' },
];

const STATUS_BADGE_VARIANT: Record<
  TaskStatus,
  'default' | 'primary' | 'success' | 'error' | 'warning'
> = {
  pending: 'default',
  queued: 'default',
  running: 'primary',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
  killed: 'error',
  timeout: 'warning',
};

const ACTIVE_STATUSES: TaskStatus[] = ['pending', 'queued', 'running'];

function isTerminal(status: TaskStatus): boolean {
  return !ACTIVE_STATUSES.includes(status);
}

function StatusIcon({ status }: { status: TaskStatus }) {
  switch (status) {
    case 'running':
      return <CircleDot className="w-4 h-4 text-primary-500 animate-pulse" />;
    case 'completed':
      return <CheckCircle2 className="w-4 h-4 text-green-500" />;
    case 'failed':
      return <XCircle className="w-4 h-4 text-red-500" />;
    case 'cancelled':
      return <Ban className="w-4 h-4 text-yellow-500" />;
    case 'killed':
      return <Square className="w-4 h-4 text-red-600" />;
    case 'timeout':
      return <AlertTriangle className="w-4 h-4 text-orange-500" />;
    default:
      return <Clock className="w-4 h-4 text-gray-400" />;
  }
}

interface TaskOutputStreamProps {
  taskId: string;
}

/**
 * Polls ``/tasks/{id}/output`` every second starting from the last
 * offset and appends new bytes to an in-memory buffer. The React Query
 * hook auto-stops polling once the backend reports ``is_done``.
 */
function TaskOutputStream({ taskId }: TaskOutputStreamProps) {
  const [offset, setOffset] = useState(0);
  const [buffer, setBuffer] = useState('');
  const boxRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    setOffset(0);
    setBuffer('');
  }, [taskId]);

  const { data: chunk, refetch, isFetching } = useTaskOutput(taskId, offset);

  useEffect(() => {
    if (!chunk) return;
    if (chunk.output) {
      setBuffer((prev) => prev + chunk.output);
    }
    if (chunk.next_offset > offset) {
      setOffset(chunk.next_offset);
    }
  }, [chunk, offset]);

  useEffect(() => {
    if (!boxRef.current) return;
    boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [buffer]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {buffer.length} bytes · offset {offset}
          {chunk?.is_done ? ' · done' : isFetching ? ' · streaming' : ''}
        </span>
        <Button
          size="sm"
          variant="ghost"
          leftIcon={<RefreshCcw className="w-3.5 h-3.5" />}
          onClick={() => refetch()}
        >
          Refresh
        </Button>
      </div>
      <pre
        ref={boxRef}
        className="bg-gray-950 text-gray-100 rounded-lg p-3 text-xs font-mono max-h-[28rem] overflow-auto whitespace-pre-wrap break-all"
      >
        {buffer || (chunk?.is_done ? '(no output)' : 'Waiting for output…')}
      </pre>
    </div>
  );
}

interface TaskDetailProps {
  taskId: string;
}

function TaskDetail({ taskId }: TaskDetailProps) {
  const { data: task, isLoading } = useUserTask(taskId);
  const killMutation = useKillUserTask();
  const cancelMutation = useCancelUserTask();

  if (isLoading || !task) {
    return (
      <div className="flex items-center justify-center py-12">
        <PageLoader size="sm" message="Loading task…" />
      </div>
    );
  }

  const canKill = !isTerminal(task.status);
  const canCancel = task.status === 'pending' || task.status === 'queued';

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <StatusIcon status={task.status} />
            <h2 className="text-lg font-semibold text-foreground truncate">
              {task.name}
            </h2>
          </div>
          <p className="text-xs text-muted-foreground break-all">ID: {task.id}</p>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          {canCancel && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => cancelMutation.mutate(task.id)}
              loading={cancelMutation.isPending}
            >
              Cancel
            </Button>
          )}
          <Button
            size="sm"
            variant="danger"
            disabled={!canKill}
            onClick={() => killMutation.mutate(task.id)}
            loading={killMutation.isPending}
          >
            Kill
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-xs text-muted-foreground">Type</p>
          <Badge variant="default">{task.task_type}</Badge>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Status</p>
          <Badge variant={STATUS_BADGE_VARIANT[task.status]}>{task.status}</Badge>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Priority</p>
          <Badge variant="default">{task.priority}</Badge>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Progress</p>
          <p className="text-sm text-foreground">
            {task.progress}%
            {task.progress_message ? ` · ${task.progress_message}` : ''}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Started</p>
          <p className="text-sm text-foreground">
            {task.started_at ? formatDate(task.started_at) : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Completed</p>
          <p className="text-sm text-foreground">
            {task.completed_at ? formatDate(task.completed_at) : '—'}
          </p>
        </div>
      </div>

      {task.error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
          <p className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">
            Error
          </p>
          <pre className="text-xs text-red-700 dark:text-red-300 whitespace-pre-wrap font-mono">
            {task.error}
          </pre>
        </div>
      )}

      <div>
        <p className="text-xs font-medium text-foreground mb-2">Live output</p>
        <TaskOutputStream taskId={task.id} />
      </div>
    </div>
  );
}

export default function TasksPage() {
  const { t } = useTranslation();
  const { taskId: paramTaskId } = useParams<{ taskId?: string }>();

  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [typeFilter, setTypeFilter] = useState<TaskType | 'all'>('all');
  const [priorityFilter, setPriorityFilter] = useState<TaskPriority | 'all'>('all');
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [agentPrompt, setAgentPrompt] = useState('');
  const [agentRunName, setAgentRunName] = useState('Coding agent run');
  const [runtimeProfile, setRuntimeProfile] = useState<'coding_long' | 'coding_extended'>('coding_long');
  const createAgentRun = useCreateAgentRun();

  const params = useMemo(
    () => ({
      page,
      pageSize: 25,
      status: statusFilter === 'all' ? undefined : statusFilter,
      task_type: typeFilter === 'all' ? undefined : typeFilter,
      priority: priorityFilter === 'all' ? undefined : priorityFilter,
    }),
    [page, statusFilter, typeFilter, priorityFilter],
  );

  const { data, isLoading } = useUserTasks(params);

  const startAgentRun = async () => {
    const prompt = agentPrompt.trim();
    if (!prompt) return;
    const res = await createAgentRun.mutateAsync({
      message: prompt,
      name: agentRunName.trim() || 'Coding agent run',
      runtime_profile: runtimeProfile,
      prompt_variant: 'coding_agent',
      priority: runtimeProfile === 'coding_extended' ? 'urgent' : 'high',
    });
    setAgentPrompt('');
    setSelectedId(res.task_id);
  };

  // Honour /tasks/:taskId deep-links (e.g. clicking "last_task_id"
  // from a cron execution).
  useEffect(() => {
    if (paramTaskId) setSelectedId(paramTaskId);
  }, [paramTaskId]);

  useEffect(() => {
    if (selectedId) return;
    const first = data?.items?.[0];
    if (first) setSelectedId(first.id);
  }, [data, selectedId]);

  return (
    <PageShell
      icon={<ListChecks className="w-5 h-5" aria-hidden />}
      title={t('tasks.title', { defaultValue: 'Tasks' })}
      description={t('tasks.description', {
        defaultValue:
          'Monitor background tasks, stream their output, and kill runaways.',
      })}
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Card padding="none" className="h-fit">
          <CardContent padding="none" className="p-4 space-y-3">
            <div className="rounded-lg border border-border bg-surface-subtle p-3 space-y-3">
              <div>
                <p className="text-sm font-semibold text-foreground">
                  Long-running Coding Agent
                </p>
                <p className="text-xs text-muted-foreground">
                  Starts a background agent task and streams logs here by task id.
                </p>
              </div>
              <Input
                value={agentRunName}
                onChange={(e) => setAgentRunName(e.target.value)}
                placeholder="Task name"
              />
              <Textarea
                value={agentPrompt}
                onChange={(e) => setAgentPrompt(e.target.value)}
                placeholder="Describe the coding task to run in the background…"
                rows={4}
              />
              <div className="flex flex-col sm:flex-row gap-2">
                <Select
                  value={runtimeProfile}
                  onChange={(e) =>
                    setRuntimeProfile(e.target.value as 'coding_long' | 'coding_extended')
                  }
                >
                  <option value="coding_long">coding_long</option>
                  <option value="coding_extended">coding_extended</option>
                </Select>
                <Button
                  className="sm:w-auto"
                  onClick={() => void startAgentRun()}
                  disabled={!agentPrompt.trim()}
                  loading={createAgentRun.isPending}
                >
                  Start agent run
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <Select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as TaskStatus | 'all')}
              >
                {STATUS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
              <Select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value as TaskType | 'all')}
              >
                {TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
              <Select
                value={priorityFilter}
                onChange={(e) =>
                  setPriorityFilter(e.target.value as TaskPriority | 'all')
                }
              >
                {PRIORITY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </div>

            {isLoading ? (
              <div className="flex items-center justify-center py-16">
                <PageLoader size="sm" message="Loading tasks…" />
              </div>
            ) : !data?.items?.length ? (
              <EmptyState
                type="data"
                title="No tasks"
                description="Kick off a task from chat or an agent tool."
              />
            ) : (
              <ul className="divide-y divide-border">
                {data.items.map((task: Task) => (
                  <li key={task.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(task.id)}
                      className={cn(
                        'w-full text-left px-2 py-3 rounded-md hover:bg-surface-sunken transition-colors',
                        selectedId === task.id && 'bg-surface-sunken',
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <StatusIcon status={task.status} />
                          <span className="font-medium text-sm text-foreground truncate">
                            {task.name}
                          </span>
                        </div>
                        <Badge variant={STATUS_BADGE_VARIANT[task.status]} size="sm">
                          {task.status}
                        </Badge>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant="default" size="sm">
                          {task.task_type}
                        </Badge>
                        <Badge variant="default" size="sm">
                          {task.priority}
                        </Badge>
                        <span>
                          {task.started_at
                            ? formatRelativeTime(task.started_at)
                            : formatRelativeTime(task.created_at)}
                        </span>
                        <span>· {task.progress}%</span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {data && (data.has_next || data.has_prev) && (
              <div className="flex items-center justify-between pt-2 text-xs text-muted-foreground">
                <span>
                  Page {data.page} · {data.total} total
                </span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!data.has_prev}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    Prev
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!data.has_next}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card padding="none" className="min-h-[24rem]">
          <CardContent padding="none" className="p-5">
            {selectedId ? (
              <TaskDetail taskId={selectedId} />
            ) : (
              <EmptyState
                type="data"
                title="Select a task"
                description="Pick a task from the list to stream its live output."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}
