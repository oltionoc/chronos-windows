import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { LanguageSwitcher } from '../components/ui/LanguageSwitcher';
import { LogoLockup } from '../components/ui/Logo';
import { SolisLabsLogo } from '../components/ui/SolisLabsLogo';
import { ApiError } from '../api/client';

// /login — DESIGN_SPEC §5.1. Not part of the app shell (no sidebar/topbar).
export function Login() {
  const { t } = useTranslation();
  const { user, loading, login } = useAuth();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) {
    const from = (location.state as { from?: Location })?.from;
    return <Navigate to={from?.pathname || '/'} replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(false);
    try {
      await login(username, password);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 400)) {
        setError(true);
      } else {
        setError(true);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-app px-4">
      <div className="w-full max-w-[400px] rounded-lg bg-white p-8 shadow-md">
        <div className="mb-6 flex items-start justify-between">
          <LogoLockup width={240} />
          <LanguageSwitcher />
        </div>
        <p className="mb-6 text-caption text-neutral-500">{t('auth.loginSubtitle')}</p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <Input
            label={t('auth.username')}
            name="username"
            autoComplete="username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <Input
            label={t('auth.password')}
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {error && (
            <div className="rounded-md bg-danger-50 px-3 py-3 text-sm text-danger-700">
              {t('auth.invalidCredentials')}
            </div>
          )}

          <Button type="submit" className="w-full justify-center" loading={submitting}>
            {t('auth.loginButton')}
          </Button>
        </form>
        <div className="mt-6 flex flex-col items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wide text-neutral-400">{t('common.poweredBy')}</span>
          <SolisLabsLogo width={220} variant="dark" />
        </div>
      </div>
    </div>
  );
}
