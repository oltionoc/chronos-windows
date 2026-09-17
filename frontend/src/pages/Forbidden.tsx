import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { Button } from '../components/ui/Button';

// 403 page — DESIGN_SPEC §5.4: "a direct URL to another manager's employee
// returns a 403 page: centered message ... with a Button back to /".
export function Forbidden() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-app px-4 text-center">
      <ShieldAlert size={48} className="text-neutral-300" />
      <p className="text-section-title text-neutral-900">{t('forbidden.title')}</p>
      <Button onClick={() => navigate('/')}>{t('employees.backToDashboard')}</Button>
    </div>
  );
}
