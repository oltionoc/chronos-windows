import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { FileQuestion } from 'lucide-react';
import { Button } from '../components/ui/Button';

// Catch-all for unmatched routes. Not an explicit DESIGN_SPEC route — a
// judgment call to avoid a blank screen on bad URLs (see FRONTEND_NOTES.md).
export function NotFound() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-app px-4 text-center">
      <FileQuestion size={48} className="text-neutral-300" />
      <p className="text-section-title text-neutral-900">{t('notFound.title')}</p>
      <p className="text-body-muted text-neutral-500">{t('notFound.message')}</p>
      <Button onClick={() => navigate('/')}>{t('employees.backToDashboard')}</Button>
    </div>
  );
}
