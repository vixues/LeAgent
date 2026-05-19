import type { Node, Edge, XYPosition } from '@xyflow/react';

export interface FlowNodeData extends Record<string, unknown> {
  label: string;
  icon: string;
  category: string;
  description?: string;
  parameters?: Record<string, unknown>;
  inputs?: string[];
  outputs?: string[];
}

export type FlowNode = Node<FlowNodeData>;
export type FlowEdge = Edge;

export interface FlowData {
  id: string;
  name: string;
  description?: string;
  icon?: string;
  icon_bg_color?: string;
  status?: string;
  flow_type?: string;
  is_public?: boolean;
  nodes: FlowNode[];
  edges: FlowEdge[];
  tags?: string[] | string;
  data?: string;
  settings?: string;
  version?: number;
  user_id?: string;
  folder_id?: string;
  run_count?: number;
  last_run_at?: string;
  created_at?: string;
  updated_at?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface FlowExecution {
  id: string;
  flowId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  startedAt: string;
  completedAt?: string;
  error?: string;
  nodeExecutions: NodeExecution[];
}

export interface NodeExecution {
  nodeId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  startedAt?: string;
  completedAt?: string;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string;
  logs?: string[];
}

export interface ComponentDefinition {
  type: string;
  label: string;
  category: string;
  description?: string;
  icon?: string;
  defaultParameters?: Record<string, unknown>;
  inputs?: string[];
  outputs?: string[];
}

export interface ComponentCategory {
  id: string;
  label: string;
  icon: string;
  description?: string;
}

export interface FlowValidationError {
  nodeId?: string;
  edgeId?: string;
  type: 'error' | 'warning';
  message: string;
}

export interface FlowValidationResult {
  isValid: boolean;
  errors: FlowValidationError[];
  warnings: FlowValidationError[];
}

export interface ConnectionValidation {
  isValid: boolean;
  reason?: string;
}

export interface DragDropData {
  component: ComponentDefinition;
  sourcePosition: XYPosition;
}
