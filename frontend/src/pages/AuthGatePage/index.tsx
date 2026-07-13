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
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
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

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(56,189,248,0.18),_transparent_55%),radial-gradient(ellipse_at_bottom,_rgba(14,165,233,0.12),_transparent_50%)]"
      />
      <form
        onSubmit={onSubmit}
        className="relative w-full max-w-md rounded-2xl border border-white/10 bg-slate-900/70 p-8 shadow-2xl backdrop-blur-md"
      >
        <p className="text-sm font-medium tracking-[0.2em] text-sky-300/90 uppercase">LeAgent</p>
        <h1 className="mt-3 text-2xl font-semibold text-white">
          {needsSetup ? t('auth.setupTitle') : t('auth.login')}
        </h1>
        <p className="mt-2 text-sm text-slate-300">
          {needsSetup ? t('auth.setupSubtitle') : t('login.subtitle')}
        </p>

        {!needsSetup && authStatus?.multi_user ? (
          <label className="mt-6 block text-sm text-slate-300">
            {t('login.username')}
            <input
              className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-white outline-none ring-sky-400/40 focus:ring"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t('login.usernamePlaceholder')}
              autoComplete="username"
            />
          </label>
        ) : null}

        <label className="mt-4 block text-sm text-slate-300">
          {needsSetup ? t('auth.accessPassword') : t('login.password')}
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-white outline-none ring-sky-400/40 focus:ring"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('login.passwordPlaceholder')}
            autoComplete={needsSetup ? 'new-password' : 'current-password'}
            required
          />
        </label>

        {needsSetup ? (
          <label className="mt-4 block text-sm text-slate-300">
            {t('auth.confirmPassword')}
            <input
              type="password"
              className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-white outline-none ring-sky-400/40 focus:ring"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
          </label>
        ) : null}

        {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}

        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full rounded-lg bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:opacity-60"
        >
          {busy ? t('common.meta.starting') : needsSetup ? t('auth.completeSetup') : t('auth.login')}
        </button>
      </form>
    </div>
  );
}
