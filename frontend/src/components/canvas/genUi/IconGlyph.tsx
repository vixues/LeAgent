/**
 * Tiny adapter so any GenUi card/button can render `props.icon` as either a
 * Lucide glyph (kebab-case slug, PascalCase, or auto) or an emoji fallback —
 * keeping every renderer free of `lucide-react` import boilerplate.
 */

import { GenUiIcon } from '@/components/canvas/genUi/GenUiIcon';
import { resolveIconSize } from '@/components/canvas/genUi/styles';

export type IconTone = 'muted' | 'default' | 'primary' | 'success' | 'warning' | 'error';

interface IconGlyphProps {
  /** Lucide kebab id, PascalCase, or emoji. `null|undefined|''` renders nothing. */
  name?: unknown;
  size?: number | string;
  tone?: IconTone | string;
  iconSet?: 'auto' | 'lucide' | 'emoji';
  strokeWidth?: number;
  className?: string;
}

export function IconGlyph({
  name,
  size = 20,
  tone = 'default',
  iconSet,
  strokeWidth,
  className,
}: IconGlyphProps) {
  if (name == null || name === '') return null;
  const px = resolveIconSize(size);
  return (
    <span className={className}>
      <GenUiIcon
        node={{
          nodeId: '_glyph',
          kind: 'Icon',
          props: {
            name,
            size: px,
            color: tone,
            iconSet,
            strokeWidth,
          },
        }}
      />
    </span>
  );
}
