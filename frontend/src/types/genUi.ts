/** Declarative generative UI (must stay aligned with backend `leagent.services.gen_ui.schema`). */

export type GenUiNodeKind =
  // Layout
  | 'Stack'
  | 'Grid'
  | 'Row'
  | 'Spacer'
  | 'ScrollArea'
  | 'Tabs'
  | 'TabItem'
  | 'Accordion'
  | 'AccordionItem'
  | 'AspectBox'
  | 'DesignSurface'
  // Typography & basic
  | 'Text'
  | 'Heading'
  | 'Divider'
  | 'Skeleton'
  // Data display
  | 'Badge'
  | 'Tag'
  | 'Stat'
  | 'Progress'
  | 'Avatar'
  | 'Image'
  | 'Video'
  | 'Model3D'
  | 'LiveCamera'
  | 'Icon'
  | 'Table'
  | 'TableRow'
  | 'TableCell'
  | 'List'
  | 'ListItem'
  | 'CodeBlock'
  | 'Markdown'
  | 'Chart'
  // Cards
  | 'Card'
  | 'WeatherCard'
  | 'DataCard'
  | 'MetricCard'
  | 'ProfileCard'
  | 'MediaCard'
  | 'AlertCard'
  | 'TimelineCard'
  | 'SlideDeck'
  | 'Slide'
  | 'KpiBoard'
  | 'FeatureGrid'
  | 'Stepper'
  | 'QuoteCard'
  | 'ImageGallery'
  | 'KeyValueList'
  | 'SectionHeader'
  // Interactive
  | 'Button'
  | 'InteractiveButton'
  | 'ToggleButton'
  | 'LinkButton'
  | 'Input'
  | 'Select'
  | 'Chip'
  | 'ChipGroup'
  // Forms (interactive ingress: workflow inputs, resume prompts)
  | 'Form'
  | 'NumberInput'
  | 'Switch'
  | 'Slider'
  | 'FileInput'
  | 'Textarea'
  // Feedback
  | 'Alert'
  | 'Callout'
  // Embed
  | 'HostedCanvasFrame'
  | 'HtmlFrame'
  | 'ThreeJsFrame'
  | 'JsonDebug';

export interface GenUiNode {
  nodeId: string;
  kind: GenUiNodeKind | string;
  props?: Record<string, unknown>;
  children?: GenUiNode[];
}

export interface GenUiTreeV1 {
  schemaVersion: '1';
  root: GenUiNode;
}

export interface UiTreeStreamPayload {
  tree: GenUiTreeV1;
  canvas_id?: string;
  /** Present when emitted from a companion `tool_result` (correlates UI with tool row). */
  tool_call_id?: string;
}

export interface UiPatchStreamPayload {
  patches: Array<{
    op: 'add' | 'replace' | 'remove';
    path: string;
    value?: unknown;
  }>;
  canvas_id?: string;
  seq?: number;
  tool_call_id?: string;
}
