import { useCallback } from 'react';
import { useReactFlow, XYPosition } from '@xyflow/react';
import { useFlowStore, FlowNode, FlowNodeData } from '../../stores/flow';
import { generateId } from '../../lib/utils';

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

interface UseAddComponentOptions {
  defaultPosition?: XYPosition;
  positionOffset?: { x: number; y: number };
}

export function useAddComponent(options: UseAddComponentOptions = {}) {
  const { defaultPosition = { x: 250, y: 250 }, positionOffset = { x: 50, y: 50 } } = options;
  const { addNode, nodes } = useFlowStore();
  const reactFlow = useReactFlow();

  const getNextPosition = useCallback((): XYPosition => {
    if (nodes.length === 0) {
      return defaultPosition;
    }

    const lastNode = nodes[nodes.length - 1];
    if (!lastNode) return defaultPosition;
    return {
      x: lastNode.position.x + positionOffset.x,
      y: lastNode.position.y + positionOffset.y,
    };
  }, [nodes, defaultPosition, positionOffset]);

  const screenToFlowPosition = useCallback(
    (screenPosition: XYPosition): XYPosition => {
      return reactFlow.screenToFlowPosition(screenPosition);
    },
    [reactFlow]
  );

  const addComponentAtPosition = useCallback(
    (component: ComponentDefinition, position: XYPosition): FlowNode => {
      const nodeData: FlowNodeData = {
        label: component.label,
        icon: component.icon || component.category,
        category: component.category,
        description: component.description,
        parameters: component.defaultParameters || {},
        inputs: component.inputs || ['input'],
        outputs: component.outputs || ['output'],
      };

      const newNode: FlowNode = {
        id: `${component.type}-${generateId()}`,
        type: 'generic',
        position,
        data: nodeData,
      };

      addNode(newNode);
      return newNode;
    },
    [addNode]
  );

  const addComponent = useCallback(
    (component: ComponentDefinition): FlowNode => {
      const position = getNextPosition();
      return addComponentAtPosition(component, position);
    },
    [addComponentAtPosition, getNextPosition]
  );

  const addComponentFromDrop = useCallback(
    (component: ComponentDefinition, dropEvent: React.DragEvent): FlowNode | null => {
      const targetIsCanvas = (dropEvent.target as HTMLElement).closest('.react-flow');
      if (!targetIsCanvas) return null;

      const position = screenToFlowPosition({
        x: dropEvent.clientX,
        y: dropEvent.clientY,
      });

      return addComponentAtPosition(component, position);
    },
    [addComponentAtPosition, screenToFlowPosition]
  );

  const addComponentAtCenter = useCallback(
    (component: ComponentDefinition): FlowNode => {
      const { x, y, zoom } = reactFlow.getViewport();
      const centerX = (-x + window.innerWidth / 2) / zoom;
      const centerY = (-y + window.innerHeight / 2) / zoom;

      return addComponentAtPosition(component, { x: centerX, y: centerY });
    },
    [addComponentAtPosition, reactFlow]
  );

  return {
    addComponent,
    addComponentAtPosition,
    addComponentFromDrop,
    addComponentAtCenter,
    screenToFlowPosition,
    getNextPosition,
  };
}

export const TOOL_COMPONENTS: ComponentDefinition[] = [
  {
    type: 'doc-read',
    label: 'Read Document',
    category: 'doc',
    description: 'Read content from files',
    inputs: ['trigger'],
    outputs: ['content'],
    defaultParameters: { path: '', encoding: 'utf-8' },
  },
  {
    type: 'doc-write',
    label: 'Write Document',
    category: 'doc',
    description: 'Write content to files',
    inputs: ['content'],
    outputs: ['success'],
    defaultParameters: { path: '', append: false },
  },
  {
    type: 'doc-parse',
    label: 'Parse Document',
    category: 'doc',
    description: 'Parse PDF, Word, Excel files',
    inputs: ['file'],
    outputs: ['data'],
    defaultParameters: { format: 'auto' },
  },
  {
    type: 'web-navigate',
    label: 'Navigate',
    category: 'web',
    description: 'Navigate to URL',
    inputs: ['trigger'],
    outputs: ['page'],
    defaultParameters: { url: '', waitFor: 'load' },
  },
  {
    type: 'web-click',
    label: 'Click Element',
    category: 'web',
    description: 'Click on web element',
    inputs: ['page'],
    outputs: ['page'],
    defaultParameters: { selector: '', timeout: 5000 },
  },
  {
    type: 'web-extract',
    label: 'Extract Data',
    category: 'web',
    description: 'Extract data from page',
    inputs: ['page'],
    outputs: ['data'],
    defaultParameters: { selector: '', attribute: 'text' },
  },
  {
    type: 'web-screenshot',
    label: 'Screenshot',
    category: 'web',
    description: 'Take page screenshot',
    inputs: ['page'],
    outputs: ['image'],
    defaultParameters: { fullPage: false },
  },
  {
    type: 'data-transform',
    label: 'Transform',
    category: 'data',
    description: 'Transform data structure',
    inputs: ['input'],
    outputs: ['output'],
    defaultParameters: { expression: '' },
  },
  {
    type: 'data-filter',
    label: 'Filter',
    category: 'data',
    description: 'Filter data by condition',
    inputs: ['input'],
    outputs: ['output'],
    defaultParameters: { condition: '' },
  },
  {
    type: 'data-aggregate',
    label: 'Aggregate',
    category: 'data',
    description: 'Aggregate data values',
    inputs: ['input'],
    outputs: ['output'],
    defaultParameters: { operation: 'sum', field: '' },
  },
  {
    type: 'llm-chat',
    label: 'AI Chat',
    category: 'llm',
    description: 'Chat with AI model',
    inputs: ['prompt'],
    outputs: ['response'],
    defaultParameters: { model: 'gpt-4', temperature: 0.7 },
  },
  {
    type: 'llm-summarize',
    label: 'Summarize',
    category: 'llm',
    description: 'Summarize text content',
    inputs: ['text'],
    outputs: ['summary'],
    defaultParameters: { maxLength: 500 },
  },
  {
    type: 'llm-extract',
    label: 'AI Extract',
    category: 'llm',
    description: 'Extract structured data',
    inputs: ['text'],
    outputs: ['data'],
    defaultParameters: { schema: {} },
  },
  {
    type: 'email-send',
    label: 'Send Email',
    category: 'email',
    description: 'Send email message',
    inputs: ['trigger'],
    outputs: ['success'],
    defaultParameters: { to: '', subject: '', body: '' },
  },
  {
    type: 'email-read',
    label: 'Read Emails',
    category: 'email',
    description: 'Read emails from inbox',
    inputs: ['trigger'],
    outputs: ['emails'],
    defaultParameters: { folder: 'INBOX', limit: 10 },
  },
  {
    type: 'condition',
    label: 'Condition',
    category: 'condition',
    description: 'Branch based on condition',
    inputs: ['input'],
    outputs: ['true', 'false'],
    defaultParameters: { expression: '' },
  },
  {
    type: 'loop',
    label: 'Loop',
    category: 'loop',
    description: 'Iterate over items',
    inputs: ['items'],
    outputs: ['item', 'done'],
    defaultParameters: { maxIterations: 100 },
  },
  {
    type: 'delay',
    label: 'Delay',
    category: 'delay',
    description: 'Wait for duration',
    inputs: ['trigger'],
    outputs: ['continue'],
    defaultParameters: { duration: 1000 },
  },
  {
    type: 'webhook-trigger',
    label: 'Webhook',
    category: 'webhook',
    description: 'Trigger on webhook',
    inputs: [],
    outputs: ['payload'],
    defaultParameters: { path: '', method: 'POST' },
  },
  {
    type: 'schedule-trigger',
    label: 'Schedule',
    category: 'trigger',
    description: 'Trigger on schedule',
    inputs: [],
    outputs: ['trigger'],
    defaultParameters: { cron: '0 * * * *' },
  },
  {
    type: 'notification',
    label: 'Notification',
    category: 'notification',
    description: 'Send notification',
    inputs: ['trigger'],
    outputs: ['success'],
    defaultParameters: { channel: 'default', message: '' },
  },
];

export const COMPONENT_CATEGORIES = [
  { id: 'doc', label: 'Documents', icon: 'FileText' },
  { id: 'web', label: 'Web Actions', icon: 'Globe' },
  { id: 'data', label: 'Data Processing', icon: 'Database' },
  { id: 'llm', label: 'AI / LLM', icon: 'Bot' },
  { id: 'email', label: 'Email', icon: 'Mail' },
  { id: 'condition', label: 'Logic', icon: 'GitBranch' },
  { id: 'loop', label: 'Loops', icon: 'Repeat' },
  { id: 'delay', label: 'Timing', icon: 'Clock' },
  { id: 'webhook', label: 'Webhooks', icon: 'Webhook' },
  { id: 'trigger', label: 'Triggers', icon: 'Zap' },
  { id: 'notification', label: 'Notifications', icon: 'Bell' },
];

export function getComponentsByCategory(category: string): ComponentDefinition[] {
  return TOOL_COMPONENTS.filter((c) => c.category === category);
}

export default useAddComponent;
