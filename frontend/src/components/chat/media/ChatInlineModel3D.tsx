import { GenUiModel3D } from '@/components/canvas/genUi/GenUiModel3D';
import type { GenUiNode } from '@/types/genUi';

interface ChatInlineModel3DProps {
  src: string;
  title?: string;
}

/**
 * Inline 3D model viewer for assistant-produced GLB/GLTF assets. Wraps the
 * canvas :func:`GenUiModel3D` Three.js viewer so generated meshes render
 * interactively in the chat message body instead of falling back to a
 * download card.
 */
export function ChatInlineModel3D({ src, title }: ChatInlineModel3DProps) {
  const node: GenUiNode = {
    nodeId: 'chat-model3d',
    kind: 'Model3D',
    props: { src, caption: title, height: 320 },
  };
  return <GenUiModel3D node={node} />;
}
