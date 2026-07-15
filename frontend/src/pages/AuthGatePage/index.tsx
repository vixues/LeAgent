import { FormEvent, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/auth';
import { PageLoader } from '@/components/common/PageLoader';

export function AuthGatePage() {
  const { t } = useTranslation();
  const {
    authStatus,
    isAuthenticated,
    isHydratingAuth,
    login,
    setup,
    bootstrapSession,
  } = useAuthStore();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [username, setUsername] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void bootstrapSession();
  }, [bootstrapSession]);

  if (isHydratingAuth || authStatus === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50">
        <PageLoader message={t('common.meta.starting')} />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/home" replace />;
  }

  const needsSetup = Boolean(authStatus && !authStatus.setup_complete);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (needsSetup) {
        if (password.length < 6) {
          setError(t('login.errors.passwordTooShort'));
          return;
        }
        if (confirm && confirm !== password) {
          setError(t('auth.passwordMismatch'));
          return;
        }
        await setup(password, confirm || password);
      } else {
        if (!password) {
          setError(t('login.errors.passwordRequired'));
          return;
        }
        await login(password, username.trim() || undefined);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('login.errors.invalidCredentials'));
    } finally {
      setBusy(false);
    }
  }

  const fieldClass =
    'mt-1 w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-zinc-900 outline-none ' +
    'placeholder:text-zinc-400 ring-sky-500/30 focus:border-sky-400 focus:ring';

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-zinc-50 px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(14,165,233,0.08),_transparent_55%),radial-gradient(ellipse_at_bottom,_rgba(56,189,248,0.06),_transparent_50%)]"
      />
      <form
        onSubmit={onSubmit}
        className="relative w-full max-w-md rounded-2xl border border-zinc-200/80 bg-white p-8 shadow-sm"
      >
        <p className="text-sm font-medium tracking-[0.2em] text-sky-700 uppercase">LeAgent</p>
        <h1 className="mt-3 text-2xl font-semibold text-zinc-900">
          {needsSetup ? t('auth.setupTitle') : t('auth.login')}
        </h1>
        <p className="mt-2 text-sm text-zinc-600">
          {needsSetup ? t('auth.setupSubtitle') : t('login.subtitle')}
        </p>

        {!needsSetup && authStatus?.multi_user ? (
          <label className="mt-6 block text-sm text-zinc-700">
            {t('login.username')}
            <input
              className={fieldClass}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t('login.usernamePlaceholder')}
              autoComplete="username"
            />
          </label>
        ) : null}

        <label className="mt-4 block text-sm text-zinc-700">
          {needsSetup ? t('auth.accessPassword') : t('login.password')}
          <input
            type="password"
            className={fieldClass}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('login.passwordPlaceholder')}
            autoComplete={needsSetup ? 'new-password' : 'current-password'}
            required
          />
        </label>

        {needsSetup ? (
          <label className="mt-4 block text-sm text-zinc-700">
            {t('auth.confirmPassword')}
            <input
              type="password"
              className={fieldClass}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
          </label>
        ) : null}

        {error ? <p className="mt-4 text-sm text-rose-600">{error}</p> : null}

        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:opacity-60"
        >
          {busy ? t('common.meta.starting') : needsSetup ? t('auth.completeSetup') : t('auth.login')}
        </button>
      </form>
    </div>
  );
}
