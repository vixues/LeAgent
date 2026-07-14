import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { QrCode, RefreshCw, Power, PowerOff } from 'lucide-react';
import { Button, Badge } from '@/components/ui';
import { useToast } from '@/components/ui/Toaster';
import {
  useWeixinLoginStart,
  useWeixinLoginStatus,
  useWeixinRuntime,
  useWeixinStart,
  useWeixinStop,
  type WeixinLoginStartResponse,
} from '@/hooks/useChannels';

const POLL_MS = 1600;

export function WeixinConnectPanel() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data: runtime, isLoading: runtimeLoading } = useWeixinRuntime();
  const startLogin = useWeixinLoginStart();
  const pollStatus = useWeixinLoginStatus();
  const startRuntime = useWeixinStart();
  const stopRuntime = useWeixinStop();

  const [session, setSession] = useState<WeixinLoginStartResponse | null>(null);
  const [loginStatus, setLoginStatus] = useState<string>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const pollingRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearPoll = useCallback(() => {
    pollingRef.current = false;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => () => clearPoll(), [clearPoll]);

  const pollOnce = useCallback(
    async (qrcode: string, baseUrl: string) => {
      if (!pollingRef.current) return;
      try {
        const res = await pollStatus.mutateAsync({ qrcode, base_url: baseUrl });
        setLoginStatus(res.status);
        setStatusMessage(res.message || '');
        const nextBase = res.base_url || baseUrl;
        if (res.status === 'confirmed') {
          clearPoll();
          toast({
            title: t('channels.weixinConnected'),
            description: res.running
              ? t('channels.weixinRunningHint')
              : res.message,
          });
          setSession(null);
          return;
        }
        if (res.status === 'expired') {
          clearPoll();
          setStatusMessage(t('channels.weixinExpired'));
          return;
        }
        if (pollingRef.current) {
          timerRef.current = setTimeout(() => {
            void pollOnce(qrcode, nextBase);
          }, POLL_MS);
        }
        return;
      } catch (e: unknown) {
        setStatusMessage(String(e));
      }
      if (pollingRef.current) {
        timerRef.current = setTimeout(() => {
          void pollOnce(qrcode, baseUrl);
        }, POLL_MS);
      }
    },
    [clearPoll, pollStatus, t, toast]
  );

  const beginScan = async () => {
    clearPoll();
    setLoginStatus('wait');
    setStatusMessage(t('channels.weixinWaiting'));
    try {
      const res = await startLogin.mutateAsync({});
      setSession(res);
      pollingRef.current = true;
      void pollOnce(res.qrcode, res.base_url);
    } catch (e: unknown) {
      setLoginStatus('error');
      setStatusMessage(String(e));
      toast({
        title: t('common.error'),
        description: String(e),
        variant: 'error',
      });
    }
  };

  const handleStop = async () => {
    try {
      await stopRuntime.mutateAsync();
      toast({ title: t('channels.weixinStopped') });
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const handleStartSaved = async () => {
    try {
      await startRuntime.mutateAsync();
      toast({ title: t('channels.weixinStarted') });
    } catch (e: unknown) {
      toast({ title: t('common.error'), description: String(e), variant: 'error' });
    }
  };

  const qrSrc = session?.qr_image_data_url || '';
  const qrLink = session?.qr_url || '';

  const running = !!runtime?.running;
  const configured = !!runtime?.configured;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <QrCode className="h-5 w-5 text-green-600 shrink-0" aria-hidden />
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              {t('channels.weixinPanelTitle')}
            </h2>
            {!runtimeLoading && (
              <Badge variant={running ? 'success' : configured ? 'warning' : 'default'}>
                {running
                  ? t('channels.weixinStatusRunning')
                  : configured
                    ? t('channels.weixinStatusConfigured')
                    : t('channels.weixinStatusIdle')}
              </Badge>
            )}
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('channels.weixinPanelDesc')}
          </p>
          {runtime?.account_id ? (
            <p className="mt-1 text-xs text-gray-400 font-mono truncate">
              account_id: {runtime.account_id}
            </p>
          ) : null}
          {runtime?.session_expired ? (
            <p className="mt-1 text-sm text-amber-600 dark:text-amber-400">
              {t('channels.weixinSessionExpired')}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <Button
            onClick={() => void beginScan()}
            loading={startLogin.isPending}
            leftIcon={<QrCode className="h-4 w-4" />}
            className="whitespace-nowrap shrink-0"
          >
            {session ? t('channels.weixinRefreshQr') : t('channels.weixinScan')}
          </Button>
          {configured && !running ? (
            <Button
              variant="secondary"
              onClick={() => void handleStartSaved()}
              loading={startRuntime.isPending}
              leftIcon={<Power className="h-4 w-4" />}
              className="whitespace-nowrap shrink-0"
            >
              {t('channels.weixinStart')}
            </Button>
          ) : null}
          {running ? (
            <Button
              variant="secondary"
              onClick={() => void handleStop()}
              loading={stopRuntime.isPending}
              leftIcon={<PowerOff className="h-4 w-4" />}
              className="whitespace-nowrap shrink-0"
            >
              {t('channels.weixinStop')}
            </Button>
          ) : null}
        </div>
      </div>

      {session ? (
        <div className="mt-5 flex flex-col sm:flex-row items-center gap-6">
          <div className="shrink-0 rounded-lg border border-gray-200 dark:border-gray-700 bg-white p-3">
            {qrSrc ? (
              <img
                src={qrSrc}
                alt={t('channels.weixinQrAlt')}
                className="h-48 w-48 object-contain"
              />
            ) : (
              <div className="h-48 w-48 flex flex-col items-center justify-center gap-2 text-xs text-center text-gray-500 p-3">
                <p>{t('channels.weixinQrRenderFail')}</p>
                {qrLink ? (
                  <a
                    href={qrLink}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary-600 dark:text-primary-400 break-all underline"
                  >
                    {t('channels.weixinOpenLink')}
                  </a>
                ) : null}
              </div>
            )}
          </div>
          <div className="space-y-2 text-sm">
            <p className="font-medium text-gray-800 dark:text-gray-200">
              {loginStatus === 'scanned'
                ? t('channels.weixinConfirmPhone')
                : loginStatus === 'expired'
                  ? t('channels.weixinExpired')
                  : t('channels.weixinWaiting')}
            </p>
            <p className="text-gray-500 dark:text-gray-400 text-xs">
              {t('channels.weixinScanHint')}
            </p>
            {statusMessage ? (
              <p className="text-gray-500 dark:text-gray-400">{statusMessage}</p>
            ) : null}
            {loginStatus === 'expired' ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void beginScan()}
                loading={startLogin.isPending}
                leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
                className="whitespace-nowrap"
              >
                {t('channels.weixinRefreshQr')}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
