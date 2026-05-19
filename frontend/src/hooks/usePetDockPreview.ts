import { useQuery } from '@tanstack/react-query';
import { petSpaceApi, type PetProject, type PetProjectFileRow } from '@/api/petSpace';
import { isPetBuiltinAppearance, type PetBuiltinAppearance } from '@/lib/builtinPets';
import { effectivePetImageMime, isPetRenderableImageRow } from '@/lib/petAppearanceMime';
import { parsePetSettings, type PetSettings } from '@/lib/petSettings';
import { usePetSpaceUiStore } from '@/stores/petSpaceUiStore';

export interface PetDockPreview {
  projectId: string | null;
  previewFileId: string | null;
  mimeType: string | null;
  /** Static shipped mascot when set (no authed blob). */
  appearanceBuiltin: PetBuiltinAppearance | null;
  /** Original filename for ``previewFileId`` (weak MIME fallback in preview hook). */
  appearancePreviewOriginalName: string | null;
  /** Parsed primary project settings (nest, behavior, appearance, …) */
  settings: PetSettings;
  rawSettings: string | null;
  nestBackgroundFileId: string | null;
  nestBackgroundMime: string | null;
  nestBackgroundOriginalName: string | null;
  /** Project files (for per-state clip bindings in dock preview). */
  projectFiles: PetProjectFileRow[];
}

function resolvePreviewFile(project: PetProject, files: PetProjectFileRow[]): {
  fileId: string | null;
  mime: string | null;
  builtin: PetBuiltinAppearance | null;
} {
  const parsed = parsePetSettings(project.settings);
  if (isPetBuiltinAppearance(parsed.appearance_builtin)) {
    return { fileId: null, mime: null, builtin: parsed.appearance_builtin };
  }
  let appearanceId: string | null = null;
  if (typeof parsed.appearance_file_id === 'string') {
    appearanceId = parsed.appearance_file_id;
  }
  if (appearanceId) {
    const row = files.find((f) => f.file_id === appearanceId);
    const m = row ? effectivePetImageMime(row.mime_type, row.original_name) : null;
    if (row && m) {
      return { fileId: row.file_id, mime: m, builtin: null };
    }
  }
  const firstImage = files.find((f) => isPetRenderableImageRow(f));
  if (firstImage) {
    const m = effectivePetImageMime(firstImage.mime_type, firstImage.original_name);
    if (m) {
      return { fileId: firstImage.file_id, mime: m, builtin: null };
    }
  }
  return { fileId: null, mime: null, builtin: null };
}

function nestBackgroundPreviewMeta(
  parsed: PetSettings,
  files: PetProjectFileRow[],
): { mime: string | null; originalName: string | null } {
  const bg = parsed.nest?.backgroundFileId;
  if (typeof bg !== 'string' || !bg) return { mime: null, originalName: null };
  const row = files.find((f) => f.file_id === bg);
  if (!row) return { mime: null, originalName: null };
  const m = effectivePetImageMime(row.mime_type, row.original_name);
  if (!m) return { mime: null, originalName: null };
  return { mime: m, originalName: row.original_name };
}

/**
 * Loads the pet project to show in the sidebar dock: the library selected on Pet Space
 * when that page is open, otherwise the primary project (first in list = most recently updated).
 */
export function usePetDockPreview() {
  const dockPreviewProjectId = usePetSpaceUiStore((s) => s.dockPreviewProjectId);
  return useQuery({
    queryKey: ['pet-space', 'dock', dockPreviewProjectId ?? 'primary'],
    queryFn: async (): Promise<PetDockPreview> => {
      const projects = await petSpaceApi.listProjects();
      if (!projects.length) {
        return {
          projectId: null,
          previewFileId: null,
          mimeType: null,
          appearanceBuiltin: null,
          appearancePreviewOriginalName: null,
          settings: {},
          rawSettings: null,
          nestBackgroundFileId: null,
          nestBackgroundMime: null,
          nestBackgroundOriginalName: null,
          projectFiles: [],
        };
      }
      const primary = projects[0]!;
      const chosen =
        dockPreviewProjectId && projects.some((p) => p.id === dockPreviewProjectId)
          ? (projects.find((p) => p.id === dockPreviewProjectId) ?? primary)
          : primary;
      const files = await petSpaceApi.listFiles(chosen.id);
      const { fileId, mime, builtin } = resolvePreviewFile(chosen, files);
      const settings = parsePetSettings(chosen.settings);
      const nestBgId =
        typeof settings.nest?.backgroundFileId === 'string' ? settings.nest.backgroundFileId : null;
      const nestBg = nestBackgroundPreviewMeta(settings, files);
      const previewRow = fileId ? files.find((f) => f.file_id === fileId) : null;
      return {
        projectId: chosen.id,
        previewFileId: fileId,
        mimeType: mime,
        appearanceBuiltin: builtin,
        appearancePreviewOriginalName: previewRow?.original_name ?? null,
        settings,
        rawSettings: chosen.settings ?? null,
        nestBackgroundFileId: nestBgId,
        nestBackgroundMime: nestBg.mime,
        nestBackgroundOriginalName: nestBg.originalName,
        projectFiles: files,
      };
    },
    staleTime: 20_000,
  });
}
