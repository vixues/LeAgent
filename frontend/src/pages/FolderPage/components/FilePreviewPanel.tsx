import {
  Download,
  Trash2,
  FileText,
  FileSpreadsheet,
  FileImage,
  FileArchive,
  FileCode,
  File,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui';
import { URL_KEYS } from '@/controllers/API/helpers/constants';
import type { FolderFileItem } from '@/hooks/useFolders';
import { UniversalFilePreview } from '@/components/files/UniversalFilePreview';

interface FilePreviewPanelProps {
  file: FolderFileItem | null;
  onClose: () => void;
  onRemove: (fileId: string) => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

const FILE_TYPE_ICONS: Record<string, typeof FileText> = {
  document: FileText,
  data: FileSpreadsheet,
  image: FileImage,
  archive: FileArchive,
  code: FileCode,
};

/**
 * Rendered inside a <Modal/>, not as a persistent right-hand pane.
 * Uses design-system tokens + shared <Button/> everywhere.
 */
export default function FilePreviewPanel({
  file,
  onRemove,
}: FilePreviewPanelProps) {
  const { t } = useTranslation();
  if (!file) return null;
  const Icon = FILE_TYPE_ICONS[file.file_type] || File;

  return (
    <div className="flex flex-col">
      <div className="px-5 py-6 flex flex-col items-center gap-3 border-b border-border">
        <div className="w-16 h-16 rounded-2xl bg-surface-sunken flex items-center justify-center">
          <Icon className="w-8 h-8 text-muted-foreground-tertiary" />
        </div>
        <h3 className="text-sm font-semibold text-foreground text-center break-all max-w-full">
          {file.file_name}
        </h3>
      </div>

      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 px-5 py-4 border-b border-border">
        <DetailRow label={t('folders.detailType')} value={file.file_type} />
        <DetailRow label={t('folders.detailSize')} value={formatSize(file.size)} />
        <DetailRow label={t('folders.detailFileId')} value={file.file_id} mono />
        <DetailRow label={t('folders.detailFolderId')} value={file.folder_id} mono />
      </dl>

      <div className="px-5 py-4 border-b border-border">
        <UniversalFilePreview
          fileId={file.file_id}
          fileName={file.file_name}
          mimeType={file.mime_type ?? undefined}
          sizeBytes={file.size}
          showActions={false}
        />
      </div>

      <div className="flex flex-col sm:flex-row gap-3 px-5 py-4">
        {/*
          Wrap the native <a> in <Button asChild> via composition: since our
          Button doesn't support `asChild`, we render an anchor with the same
          visual language by re-using the primary Button as a label.
        */}
        <a
          href={`/api/v1${URL_KEYS.FILE_DOWNLOAD(file.file_id)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 inline-flex"
        >
          <Button
            type="button"
            variant="primary"
            className="w-full"
            leftIcon={<Download className="w-4 h-4" />}
          >
            {t('folders.downloadFile')}
          </Button>
        </a>
        <Button
          type="button"
          variant="danger"
          className="flex-1"
          leftIcon={<Trash2 className="w-4 h-4" />}
          onClick={() => onRemove(file.file_id)}
        >
          {t('folders.removeFile')}
        </Button>
      </div>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground mb-0.5">{label}</dt>
      <dd
        className={`text-sm text-foreground break-all ${
          mono ? 'font-mono text-xs text-muted-foreground' : ''
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
