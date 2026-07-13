import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/components/ui/Toaster';
import { downloadAuthenticatedFile, openAuthenticatedFilePreview } from '@/lib/downloadAuthenticatedFile';

export function useFilePreviewActions(
  fileId: string,
  fileName: string,
  options?: { enabled?: boolean },
) {
  const enabled = options?.enabled ?? true;
  const previewUrl = `/api/v1/files/${fileId}/preview`;
  const { t } = useTranslation();
  const { toast } = useToast();
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [openBusy, setOpenBusy] = useState(false);

  const handleDownloadClick = useCallback(() => {
    if (!enabled || !fileId) return;
    setDownloadBusy(true);
    void downloadAuthenticatedFile(fileId, fileName)
      .catch(() => {
        toast({
          title: t('knowledge.downloadFailed'),
          variant: 'error',
        });
      })
      .finally(() => setDownloadBusy(false));
  }, [enabled, fileId, fileName, t, toast]);

  const handleOpenClick = useCallback(() => {
    if (!enabled || !fileId) return;
    setOpenBusy(true);
    void openAuthenticatedFilePreview(fileId)
      .catch(() => {
        toast({
          title: t('knowledge.downloadFailed'),
          variant: 'error',
        });
      })
      .finally(() => setOpenBusy(false));
  }, [enabled, fileId, t, toast]);

  return { previewUrl, downloadBusy, openBusy, handleDownloadClick, handleOpenClick };
}
