/**
 * Workflow editor route.
 *
 * The legacy React Flow editor internals (GenericNode canvas, zustand flow
 * store, heuristic save mapping) have been retired in favour of the
 * ComfyUI-style editor under `features/workflow` — React Flow + the custom
 * graph engine (typed sockets, inline widgets, `/object_info` registry, live
 * execution overlay). The `/workflows/new` and `/workflows/:id` routes are
 * preserved; only the implementation changed.
 */
import { WorkflowGraphEditor } from '@/features/workflow/WorkflowGraphEditor';

export function FlowPage() {
  return <WorkflowGraphEditor />;
}

export default FlowPage;
