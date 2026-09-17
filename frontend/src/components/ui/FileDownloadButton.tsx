import { useState } from 'react';
import { Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from './Button';
import { useToast } from './Toast';
import { ApiError } from '../../api/client';

interface FileDownloadButtonProps {
  onDownload: () => Promise<{ blob: Blob; filename: string | null }>;
  label: string;
  fallbackFilename?: string;
  disabled?: boolean;
  disabledHint?: string;
}

// File Download Button — DESIGN_SPEC §6.24
export function FileDownloadButton({ onDownload, label, fallbackFilename = 'download.pdf', disabled, disabledHint }: FileDownloadButtonProps) {
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();
  const { t } = useTranslation();

  async function handleClick() {
    setLoading(true);
    try {
      const { blob, filename } = await onDownload();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || fallbackFilename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : t('toast.error');
      showToast('error', message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <Button variant="secondary" leftIcon={<Download size={16} />} onClick={handleClick} loading={loading} disabled={disabled}>
        {label}
      </Button>
      {disabled && disabledHint && <p className="mt-1.5 text-caption text-neutral-500">{disabledHint}</p>}
    </div>
  );
}
