export type ArtifactType = 'code' | 'file' | 'workflow' | 'table' | 'markdown' | 'image' | 'html' | 'react' | 'mermaid';

export interface Artifact {
  id: string;
  type: ArtifactType;
  title: string;
  content: string;
  language?: string;
  metadata?: Record<string, unknown>;
  createdAt: string;
  sessionId?: string;
  messageId?: string;
}

export interface ArtifactStore {
  artifacts: Record<string, Artifact>;
  pinnedIds: string[];
  openArtifactId: string | null;
  openTabIds: string[];
  activeTabId: string | null;

  addArtifact: (artifact: Artifact) => void;
  removeArtifact: (id: string) => void;
  openArtifact: (id: string) => void;
  closeArtifact: () => void;
  openTab: (id: string) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  pinArtifact: (id: string) => void;
  unpinArtifact: (id: string) => void;
  clearSessionArtifacts: (sessionId: string) => void;
  /** When chat message client id is replaced by server UUID after stream persist. */
  remapArtifactsMessageId: (sessionId: string, oldMessageId: string, newMessageId: string) => void;
}
