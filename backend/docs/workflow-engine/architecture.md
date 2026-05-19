# Workflow engine — architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                     FastAPI app (main.py)                          │
│  /api/v1/workflow/flows/*     ← CRUD + import/export + executions  │
│  /api/v1/workflow/prompts/*   ← queue a run, cancel/pause/resume   │
│  /api/v1/workflow/object_info ← node registry snapshot             │
│  /api/v1/workflow/ws/executions[/{prompt_id}]  ← live progress     │
└───────────────┬────────────────────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────────────────┐
│                      WorkflowService facade                        │
│  - wraps DB writes, queue submission, execution resume             │
│  - constructed by ServiceManager._start_workflow_service()         │
└───────────┬──────────────────────────────┬─────────────────────────┘
            │                              │
            ▼                              ▼
   ┌────────────────┐             ┌──────────────────┐
   │  PromptQueue   │             │ WorkflowExecutor │
   │ (mem | redis)  │             │ (in-proc runs)   │
   └───────┬────────┘             └───────┬──────────┘
           │                              │
           │                              ▼
           │                 ┌──────────────────────────┐
           │                 │ DynamicPrompt +          │
           │                 │ TopologicalSort +        │
           │                 │ ExecutionList scheduler  │
           │                 └───────┬──────────────────┘
           │                         │
           ▼                         ▼
   ┌─────────────────────────────────────────────────────┐
   │  WorkflowWorker processes                           │
   │  - pull from PromptQueue                            │
   │  - invoke WorkflowExecutor.execute_async()          │
   │  - publish ProgressEvents to ExecutionEventBus      │
   └─────────────────────────────────────────────────────┘
```

## Package layout

```
leagent/workflow/
├── io/                  # Canonical document loader/serializer/validator
│   ├── loader.py        # load(), canonical shape assertion
│   ├── serializer.py    # export(), to_json()
│   ├── validator.py     # validate() — missing-target + cycle detection
│   ├── authoring.py     # to_canonical() — converts legacy / visual-editor
│   │                    #   authoring dicts into the canonical shape
│   ├── schema.py        # Schema dataclass (node metadata)
│   ├── types.py         # Input / WidgetInput / IO.* primitives
│   ├── contract.py      # fingerprint_inputs, check_lazy_status hooks
│   └── hash.py          # graph_hash() for cache keys
│
├── nodes/               # Node registry + abstract base + built-ins
│   ├── base.py          # WorkflowNode ABC with contract defaults
│   ├── registry.py      # NodeRegistry + hot-reload loader
│   ├── replacement.py   # NodeReplaceRegistry for deprecations
│   └── builtin/         # Start, End, ToolCall, LLMCall, Condition,
│                        #   Parallel, HumanReview, ErrorHandler,
│                        #   Transform, Subworkflow, Wait
│
├── engine/              # Scheduler + runner + caches
│   ├── graph.py         # DynamicPrompt, TopologicalSort, ExecutionList
│   ├── caching.py       # CacheSet, LRU/RAM/Null caches
│   ├── cache_provider.py# RedisCacheProvider for cross-worker caches
│   ├── runner.py        # NodeRunner: input resolution, fingerprint
│   │                    #   dispatch, caching, lazy handling, expand
│   ├── executor.py      # WorkflowExecutor top-level orchestrator
│   └── progress.py      # ProgressRegistry + events
│
├── queue/               # PromptQueue protocol + implementations
│   ├── base.py          # PromptItem / PromptHistoryEntry / Protocol
│   ├── memory.py        # InMemoryPromptQueue (heapq)
│   └── redis_stream.py  # RedisStreamPromptQueue
│
├── server/              # FastAPI router + WS + prompt hooks
│   ├── router.py        # /workflow/prompts, /flows/{id}/{validate,build,export}
│   ├── flows_router.py  # /workflow/flows CRUD + /executions/*
│   ├── ws.py            # stream_execution, stream_all handlers
│   ├── event_bus.py     # ExecutionEventBus (mem + redis pub/sub)
│   └── prompt_hooks.py  # apply_replacements, seed_context, validate_prompt
│
├── cli/                 # Worker launcher
│   └── workflow_worker.py
│
├── templates/           # Python-coded starter templates (dict factories)
├── template_service.py  # Unified catalog loader (YAML + Python)
├── registry.py          # FlowWorkflowRegistry (DB ↔ WorkflowDocument)
└── services.py          # WorkflowService facade
```

## Data flow for a single run

1. Client calls `POST /workflow/flows/{id}/run` with `input_data`.
2. Router authenticates, loads the stored `Flow.data`, applies deprecated
   node replacements via `prompt_hooks.apply_replacements`.
3. `io.load()` asserts the document is canonical and parses it into a
   `WorkflowDocument`.
4. `prompt_hooks.validate_prompt` rejects missing-target edges and control
   cycles (back-edges into `WaitNode`/`ErrorHandlerNode` are allowed).
5. `WorkflowService.enqueue()` persists a `WorkflowExecution` row and puts
   a `PromptItem` on the `PromptQueue`.
6. A `WorkflowWorker` pulls the item, instantiates `WorkflowExecutor`, and
   runs `execute_async`.
7. `NodeRunner` iterates the scheduler frontier, resolves inputs, consults
   `fingerprint_inputs` + caches, invokes the node, and emits progress
   events through `ProgressRegistry`.
8. Events fan out via `ExecutionEventBus` to any open WebSocket subscribers.
9. Final status is persisted and a `PromptHistoryEntry` is recorded on the
   queue.
