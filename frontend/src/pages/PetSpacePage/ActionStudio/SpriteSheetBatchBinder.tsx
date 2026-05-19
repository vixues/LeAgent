import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { petSpaceApi, type PetProjectFileRow } from '@/api/petSpace';
import { fetchAuthedFilePreviewBlob } from '@/hooks/useAuthedFileBlobUrl';
import { isPetRenderableImageRow } from '@/lib/petAppearanceMime';
import { loadImageElement, spriteSheetToGifBlob } from '@/lib/spriteSheetToGif';
import { mergePetSettings, type PetClipState } from '@/lib/petSettings';
import { Button, Input } from '@/components/ui';
import { STUDIO_STATE_GROUPS } from './studioStateGroups';

export function SpriteSheetBatchBinder({
  projectId,
  baseSettings,
  files,
  onDone,
  defaultTarget,
}: {
  projectId: string;
  baseSettings: string | null | undefined;
  files: PetProjectFileRow[];
  onDone: () => void;
  defaultTarget: PetClipState;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const images = useMemo(() => files.filter((f) => isPetRenderableImageRow(f)), [files]);
  const [sourceId, setSourceId] = useState<string | null>(() => images[0]?.file_id ?? null);
  const [cols, setCols] = useState(4);
  const [rows, setRows] = useState(4);
  const [pad, setPad] = useState(0);
  const [fps, setFps] = useState(8);
  const [transparent, setTransparent] = useState(true);
  const [startFrame, setStartFrame] = useState(0);
  const [endFrame, setEndFrame] = useState(7);
  const [target, setTarget] = useState<PetClipState>(defaultTarget);
  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const totalFrames = cols * rows;

  useEffect(() => {
    if (!images.find((f) => f.file_id === sourceId) && images[0]) {
      setSourceId(images[0]!.file_id);
    }
  }, [images, sourceId]);
  useEffect(() => {
    if (endFrame > totalFrames - 1) setEndFrame(Math.max(0, totalFrames - 1));
    if (startFrame > totalFrames - 1) setStartFrame(0);
  }, [totalFrames, startFrame, endFrame]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const uploadMut = useMutation({
    mutationFn: ({ file }: { file: File }) => petSpaceApi.uploadFile(projectId, file),
  });

  const buildGifBlob = async (): Promise<Blob> => {
    const row = images.find((f) => f.file_id === sourceId) ?? null;
    if (!row) throw new Error(t('petSpace.spriteNeedImage'));
    if (startFrame < 0 || endFrame < startFrame || endFrame >= totalFrames) {
      throw new Error(t('petSpace.studio.rangeInvalid', { n: totalFrames - 1 }));
    }
    const sourcePreviewBlob = await fetchAuthedFilePreviewBlob(
      row.file_id,
      row.mime_type,
      row.original_name,
    );
    const sheetObjectUrl = URL.createObjectURL(sourcePreviewBlob);
    try {
      const img = await loadImageElement(sheetObjectUrl);
      const speed = 1;
      const adjustedFps = Math.max(1, Math.round(fps * speed));
      const { blob } = await spriteSheetToGifBlob(img, {
        cols,
        rows,
        pad,
        fps: adjustedFps,
        transparent,
        loop: 0,
        frameRange: { start: startFrame, end: endFrame },
      });
      return blob;
    } finally {
      URL.revokeObjectURL(sheetObjectUrl);
    }
  };

  const runPreview = async () => {
    setErr(null);
    setPreviewBusy(true);
    try {
      const gifBlob = await buildGifBlob();
      setPreviewUrl(URL.createObjectURL(gifBlob));
    } catch (e) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const runBind = async () => {
    setErr(null);
    setBusy(true);
    try {
      const gifBlob = await buildGifBlob();
      const file = new File([gifBlob], `clip-${String(target).replace(/[^a-z0-9]/gi, '-')}.gif`, {
        type: 'image/gif',
      });
      const res = await uploadMut.mutateAsync({ file });
      const settings = mergePetSettings(baseSettings, {
        clips: {
          [target]: { fileId: res.id, loop: 'loop', overrideCssMotion: true, speed: 1 },
        },
      });
      await petSpaceApi.updateProject(projectId, { settings });
      void qc.invalidateQueries({ queryKey: ['pet-space', 'files', projectId] });
      void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
      void qc.invalidateQueries({ queryKey: ['pet-space', 'dock'] });
      onDone();
    } catch (e) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const srcRow = images.find((f) => f.file_id === sourceId) ?? null;

  if (images.length === 0) {
    return <p className="text-sm text-muted-foreground border border-dashed rounded-xl p-4">{t('petSpace.spriteNoImages')}</p>;
  }

  const controlsLocked = busy || previewBusy || !srcRow || uploadMut.isPending;

  return (
    <div className="rounded-xl border border-border p-4 bg-surface-sunken/20">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-6">
        <div className="min-w-0 flex-1 space-y-3">
          <h3 className="text-sm font-semibold">{t('petSpace.studio.batchTitle')}</h3>
          <p className="text-xs text-muted-foreground leading-snug">{t('petSpace.studio.batchIntro')}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <label className="space-y-1 block">
              <span className="text-muted-foreground">{t('petSpace.spriteSource')}</span>
              <select
                className="w-full rounded-lg border border-border bg-background px-2 py-1.5"
                value={sourceId ?? ''}
                onChange={(e) => setSourceId(e.target.value || null)}
              >
                {images.map((f) => (
                  <option key={f.id} value={f.file_id}>
                    {f.original_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 block">
              <span className="text-muted-foreground">{t('petSpace.studio.bindTo')}</span>
              <select
                className="w-full rounded-lg border border-border bg-background px-2 py-1.5"
                value={target}
                onChange={(e) => setTarget(e.target.value as PetClipState)}
              >
                {STUDIO_STATE_GROUPS.flatMap((g) => g.states).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 block">
              <span className="text-muted-foreground">{t('petSpace.spriteCols')}</span>
              <Input type="number" min={1} max={32} value={cols} onChange={(e) => setCols(+e.target.value || 1)} />
            </label>
            <label className="space-y-1 block">
              <span className="text-muted-foreground">{t('petSpace.spriteRows')}</span>
              <Input type="number" min={1} max={32} value={rows} onChange={(e) => setRows(+e.target.value || 1)} />
            </label>
            <label className="space-y-1 block">
              <span className="text-muted-foreground">{t('petSpace.spritePad')}</span>
              <Input type="number" min={0} max={64} value={pad} onChange={(e) => setPad(+e.target.value || 0)} />
            </label>
            <label className="space-y-1 block">
              <span className="text-muted-foreground">{t('petSpace.spriteFps')}</span>
              <Input type="number" min={1} max={60} value={fps} onChange={(e) => setFps(+e.target.value || 8)} />
            </label>
            <label className="space-y-1 block">
              <span className="text-muted-foreground">{t('petSpace.studio.frameStart')}</span>
              <Input
                type="number"
                min={0}
                max={totalFrames - 1}
                value={startFrame}
                onChange={(e) => setStartFrame(Math.max(0, +e.target.value || 0))}
              />
            </label>
            <label className="space-y-1 block">
              <span className="text-muted-foreground">{t('petSpace.studio.frameEnd')}</span>
              <Input
                type="number"
                min={0}
                max={totalFrames - 1}
                value={endFrame}
                onChange={(e) => setEndFrame(Math.min(totalFrames - 1, +e.target.value || 0))}
              />
            </label>
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={transparent} onChange={(e) => setTransparent(e.target.checked)} />
            {t('petSpace.spriteTransparent')}
          </label>
          {err ? <p className="text-xs text-red-600">{err}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="secondary" disabled={controlsLocked} onClick={() => void runPreview()}>
              {t('petSpace.studio.batchPreviewButton')}
            </Button>
            <Button type="button" size="sm" disabled={busy || !srcRow || uploadMut.isPending || previewBusy} onClick={() => void runBind()}>
              {t('petSpace.studio.generateAndBind')}
            </Button>
          </div>
        </div>
        <div className="shrink-0 lg:w-52 xl:w-60">
          <p className="text-xs font-medium text-muted-foreground mb-2">{t('petSpace.studio.batchGifPreview')}</p>
          <div className="flex min-h-[10rem] items-center justify-center rounded-lg border border-border bg-background/80 p-2">
            {previewUrl ? (
              <img
                src={previewUrl}
                alt=""
                className="max-h-48 w-full max-w-full object-contain"
              />
            ) : (
              <p className="text-center text-xs text-muted-foreground px-2">{t('petSpace.studio.batchPreviewPlaceholder')}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
