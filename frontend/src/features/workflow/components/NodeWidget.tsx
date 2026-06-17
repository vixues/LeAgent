import { memo, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { cn } from '@/lib/utils';
import { apiClient } from '@/api/client';
import { useChatStore } from '@/stores/chat';
import { normalizeAttachment, type Attachment } from '@/types/chat';

import type { InputSlot } from '../graph/objectInfo';

interface NodeWidgetProps {
  slot: InputSlot;
  value: unknown;
  onChange: (value: unknown) => void;
  /** Disabled when the input is driven by a link. */
  connected?: boolean;
}

/**
 * Render the inline editing widget for a node input, driven by the widget
 * kind the backend declared in `/object_info` (litegraph-style inline
 * widgets). When the slot is connected, the widget is shown read-only since
 * the value comes from upstream.
 */
function NodeWidgetImpl({ slot, value, onChange, connected }: NodeWidgetProps) {
  const baseField =
    'nodrag w-full rounded border border-border bg-background px-1.5 py-0.5 text-xs text-foreground disabled:opacity-50';
  const [uploadError, setUploadError] = useState<string | null>(null);
  const uploadRef = useRef<HTMLInputElement | null>(null);
  const sessionId = useChatStore((s) => s.currentSessionId);

  const isImagePicker = slot.widget === 'file' && String(slot.accept || '').includes('image/');
  const selectedId = typeof value === 'string' ? value : '';

  const { data: imageAttachments } = useQuery<Attachment[]>({
    queryKey: ['workflow', 'image-library', sessionId ?? 'workflow-library'],
    enabled: isImagePicker && !connected,
    queryFn: async () => {
      // Prefer session attachments when we're inside a chat thread; otherwise fall back
      // to the workflow asset library (non-chat).
      if (sessionId) {
        const res = await apiClient.get<{ attachments: unknown[] }>(
          `/chat/sessions/${sessionId}/attachments`,
        );
        const out: Attachment[] = [];
        const list = res.attachments ?? [];
        for (let i = 0; i < list.length; i++) {
          const att = normalizeAttachment(list[i], `session-att-${i}`);
          if (!att?.id) continue;
          const kind = (att.kind || '').toLowerCase();
          const type = (att.type || '').toLowerCase();
          if (kind === 'image' || type.startsWith('image/')) out.push(att);
        }
        return out;
      }

      const res = await apiClient.get<{ assets: unknown[] }>(`/workflow/assets`);
      const list = (res as { assets?: unknown[] }).assets ?? [];
      const out: Attachment[] = [];
      for (let i = 0; i < list.length; i++) {
        const item = list[i];
        if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
        const r = item as Record<string, unknown>;
        const id = typeof r.id === 'string' ? r.id : '';
        if (!id) continue;
        const filename = (typeof r.filename === 'string' ? r.filename : '') || id;
        const type = typeof r.mime_type === 'string' ? r.mime_type : '';
        const size = typeof r.size === 'number' ? r.size : 0;
        const previewUrl = typeof r.preview_url === 'string' ? r.preview_url : undefined;
        const downloadUrl = typeof r.download_url === 'string' ? r.download_url : undefined;
        out.push({
          id,
          name: filename,
          type,
          size,
          kind: 'image',
          previewUrl,
          downloadUrl,
        });
      }
      return out;
    },
    staleTime: 30_000,
  });

  const selectedPreview = useMemo(() => {
    if (connected || !isImagePicker || !selectedId) return null;
    const hit = (imageAttachments || []).find((a) => a.id === selectedId);
    return hit?.previewUrl || null;
  }, [connected, imageAttachments, isImagePicker, selectedId]);

  if (connected) {
    return (
      <div className="text-[10px] italic text-muted-foreground">
        {slot.id} ← linked
      </div>
    );
  }

  const uploadImage = async (file: File) => {
    setUploadError(null);
    if (sessionId) {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('session_id', sessionId);
      const res = await apiClient.upload<{ id: string }>(`/files/upload`, fd);
      const id = String(res?.id || '').trim();
      if (id) onChange(id);
      return;
    }

    // Non-chat workflow editor: upload into workflow asset library.
    const fd = new FormData();
    fd.append('file', file);
    const res = await apiClient.upload<{ id: string }>(`/workflow/assets/upload`, fd);
    const id = String(res?.id || '').trim();
    if (id) onChange(id);
  };

  switch (slot.widget) {
    case 'string':
      return slot.multiline ? (
        <textarea
          className={cn(baseField, 'resize-y min-h-[44px]')}
          value={typeof value === 'string' ? value : ''}
          placeholder={slot.tooltip ?? slot.id}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          type="text"
          className={baseField}
          value={typeof value === 'string' ? value : ''}
          placeholder={slot.tooltip ?? slot.id}
          onChange={(e) => onChange(e.target.value)}
        />
      );

    case 'int':
    case 'float':
      return (
        <input
          type="number"
          className={baseField}
          value={value === undefined || value === null ? '' : Number(value)}
          min={slot.min}
          max={slot.max}
          step={slot.step ?? (slot.widget === 'int' ? 1 : 0.01)}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '') return onChange(undefined);
            onChange(slot.widget === 'int' ? parseInt(raw, 10) : parseFloat(raw));
          }}
        />
      );

    case 'toggle':
      return (
        <label className="nodrag flex items-center gap-1.5 text-xs text-foreground">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          {slot.id}
        </label>
      );

    case 'combo':
      return (
        <select
          className={baseField}
          value={typeof value === 'string' ? value : (slot.default as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
        >
          {(slot.choices ?? []).map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </select>
      );

    case 'file':
      if (isImagePicker) {
        return (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5">
              <select
                className={cn(baseField, 'max-w-[160px]')}
                value={selectedId}
                onChange={(e) => onChange(e.target.value)}
              >
                <option value="">选择会话图片…</option>
                {(imageAttachments || []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name || a.id}
                  </option>
                ))}
              </select>

              <input
                ref={uploadRef}
                type="file"
                accept={slot.accept || 'image/*'}
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  void uploadImage(f).finally(() => {
                    if (uploadRef.current) uploadRef.current.value = '';
                  });
                }}
              />
              <button
                type="button"
                className="nodrag rounded border border-border bg-background px-2 py-0.5 text-[10px] text-foreground hover:bg-muted"
                onClick={() => uploadRef.current?.click()}
                title={sessionId ? '上传图片到会话附件' : '上传图片到工作流资源库'}
              >
                上传
              </button>
            </div>

            {selectedPreview ? (
              <img
                src={selectedPreview}
                alt="selected"
                className="h-16 w-full rounded border border-border object-contain bg-surface-sunken"
                loading="lazy"
                decoding="async"
              />
            ) : null}

            {uploadError ? (
              <div className="text-[10px] text-red-600 dark:text-red-400">{uploadError}</div>
            ) : null}
          </div>
        );
      }

      return (
        <input
          type="text"
          className={baseField}
          value={typeof value === 'string' ? value : ''}
          placeholder="file id or path"
          onChange={(e) => onChange(e.target.value)}
        />
      );

    case 'datetime':
      return (
        <input
          type="datetime-local"
          className={baseField}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value)}
        />
      );

    default:
      return null;
  }
}

export const NodeWidget = memo(NodeWidgetImpl);
