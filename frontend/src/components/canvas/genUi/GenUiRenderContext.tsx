import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { GenUiThemeId } from '@/components/canvas/genUi/themeManager';

export interface GenUiRenderContextValue {
  /** When set, ``Image`` may resolve ``/api/v1/files/{uuid}/preview`` to an authed blob URL. */
  sessionId?: string;
  /** Assistant message id — used for GenUi button actions (patch UI, open artifact in thread). */
  messageId?: string;
  /** Active ``DesignSurface`` preset — nested cards/panels inherit themed chrome. */
  themeId?: GenUiThemeId | null;
}

const GenUiRenderContext = createContext<GenUiRenderContextValue | null>(null);

export function GenUiRenderProvider({
  sessionId,
  messageId,
  children,
}: {
  sessionId?: string;
  messageId?: string;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ sessionId, messageId }), [sessionId, messageId]);
  return <GenUiRenderContext.Provider value={value}>{children}</GenUiRenderContext.Provider>;
}

export function useGenUiRenderContext(): GenUiRenderContextValue {
  return useContext(GenUiRenderContext) ?? {};
}
