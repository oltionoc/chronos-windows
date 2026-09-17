import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { UploadCloud } from 'lucide-react';
import { Modal } from './ui/Modal';
import { Button } from './ui/Button';
import { useToast } from './ui/Toast';
import { ApiError } from '../api/client';
import type { BulkImportResult } from '../api/types';

interface BulkImportModalProps {
  open: boolean;
  onClose: () => void;
  resourceLabel: string;
  columns: string[];
  onImport: (file: File) => Promise<BulkImportResult>;
  onDone: () => void;
}

// Generic CSV bulk-import dialog, reused by every list page that needs a
// "single insert vs. many at once" option (Employees, Leave records).
export function BulkImportModal({ open, onClose, resourceLabel, columns, onImport, onDone }: BulkImportModalProps) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<BulkImportResult | null>(null);

  function reset() {
    setFile(null);
    setResult(null);
    setSubmitting(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit() {
    if (!file) return;
    setSubmitting(true);
    try {
      const res = await onImport(file);
      setResult(res);
      if (res.created > 0) {
        showToast(
          res.errors.length === 0 ? 'success' : 'warning',
          res.errors.length === 0
            ? t('bulkImport.successAllToast', { created: res.created })
            : t('bulkImport.successPartialToast', { created: res.created, errorCount: res.errors.length })
        );
        onDone();
      } else if (res.errors.length > 0) {
        showToast('error', t('toast.error'));
      }
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title={t('bulkImport.title', { resource: resourceLabel })} size="md">
      <div className="flex flex-col gap-4">
        <p className="text-caption text-neutral-500">{t('bulkImport.columnsHint', { columns: columns.join(', ') })}</p>

        <label className="flex cursor-pointer flex-col items-center gap-2 rounded-md border border-dashed border-neutral-300 px-4 py-8 text-center hover:border-primary-400">
          <UploadCloud size={24} className="text-neutral-400" />
          <span className="text-body-sm text-neutral-700">
            {file ? file.name : t('bulkImport.chooseFile')}
          </span>
          <input
            type="file"
            accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="hidden"
            onChange={(e) => {
              setResult(null);
              setFile(e.target.files?.[0] ?? null);
            }}
          />
        </label>

        {result && (
          <div className="max-h-48 overflow-y-auto rounded-md bg-neutral-50 p-3 text-body-sm">
            <p className="mb-2 font-medium text-neutral-700">
              {t('bulkImport.resultSummary', { created: result.created, errorCount: result.errors.length })}
            </p>
            {result.errors.length > 0 && (
              <ul className="space-y-1 text-danger-700">
                {result.errors.map((e) => (
                  <li key={e.row}>{t('bulkImport.rowError', { row: e.row, message: e.message })}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Button variant="ghost" onClick={handleClose}>
            {t('common.close')}
          </Button>
          <Button onClick={handleSubmit} disabled={!file} loading={submitting}>
            {submitting ? t('bulkImport.importing') : t('bulkImport.import')}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
