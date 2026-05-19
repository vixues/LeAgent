---
name: workflow-helper
description: Guidance for creating, managing and executing workflow automations that chain multiple tools and agents together. Use when the user asks about building, listing, running or composing workflows and automated task pipelines.
license: Apache-2.0
allowed-tools: workflow_list workflow_run workflow_status code_execution
metadata:
  version: 1.0.0
  category: automation
  tags: [workflow, automation, orchestration, pipeline, dag]
---

# Workflow Helper

You are assisting with workflow design and automation. Follow these guidelines.

## Workflow Design

1. **Define the goal**: what outcome should the workflow produce?
2. **Identify steps**: break the goal into discrete, ordered operations.
3. **Map tools**: select the right tool or agent for each step.
4. **Plan data flow**: what inputs each step needs and what outputs it produces.
5. **Handle errors**: decide on retry policy, fallbacks, and failure escalation.

## Workflow Patterns

- **Sequential**: Step A → Step B → Step C. Each step uses the previous step's output.
- **Parallel**: Steps run concurrently when they have no dependencies.
- **Conditional**: Branch based on intermediate results or user input.
- **Loop**: Iterate over a collection with a consistent body.
- **Pipeline**: Stream data through stages (extract → transform → load).

## Common Operations

### Creating a Workflow

- Start from a clear problem statement and acceptance criteria.
- Prefer reusing existing workflow templates before writing a new one.
- Parameterize inputs so the workflow can be reused with different data.

### Running and Monitoring

- Present workflow status clearly: pending, running, succeeded, failed, paused.
- Surface intermediate outputs so the user can diagnose stalled runs.
- Respect cancel / pause signals and clean up subprocesses.

### Integrating with Other Skills

- Use `load_skill` to pull in a specialised skill when a step needs domain expertise.
- Pass structured JSON between steps to keep data shape predictable.

## Best Practices

- Keep individual steps small and idempotent where possible.
- Log meaningful progress updates — workflow runs can be long.
- Document expected inputs, outputs, and failure modes near the workflow definition.
- Use consistent naming conventions (snake_case for workflow IDs).
- Test workflows with small, representative datasets before production runs.
