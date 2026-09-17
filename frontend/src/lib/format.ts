// Data formatting rules — DESIGN_SPEC.md Section 1.8. Fixed regardless of UI
// language; only interface copy translates, not number/date formatting.

/**
 * Currency format: `€ X.XXX,XX` — euro symbol, non-breaking space, period as
 * thousands separator, comma as decimal separator, always exactly 2 decimals.
 * Negative amounts render with a leading `− ` (U+2212 minus) for deductions;
 * callers decide sign/color, this utility only formats magnitude + sign.
 */
export function formatCurrency(amountEur: number): string {
  const negative = amountEur < 0;
  const abs = Math.abs(amountEur);
  const parts = abs.toFixed(2).split('.');
  const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const formatted = `${intPart},${parts[1]}`;
  return `${negative ? '− ' : ''}€ ${formatted}`;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** `dd.MM.yyyy` */
export function formatDate(value: string | Date): string {
  const d = typeof value === 'string' ? new Date(value) : value;
  return `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.${d.getFullYear()}`;
}

/** `dd.MM.yyyy HH:mm` (24-hour) */
export function formatDateTime(value: string | Date): string {
  const d = typeof value === 'string' ? new Date(value) : value;
  return `${formatDate(d)} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** `HH:mm` (24-hour) — accepts a `HH:mm[:ss]` time string or Date */
export function formatTime(value: string | Date): string {
  if (typeof value === 'string' && /^\d{2}:\d{2}/.test(value)) {
    return value.slice(0, 5);
  }
  const d = typeof value === 'string' ? new Date(value) : value;
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** Plain integer + unit label, e.g. `12 min` (same abbreviation both languages) */
export function formatMinutes(value: number): string {
  return `${value} min`;
}

/**
 * Relative time for `last_synced_at`: "5 min ago" / "5 min më parë" if <60
 * min, else falls back to absolute `dd.MM.yyyy HH:mm`.
 */
export function formatRelativeSync(
  value: string | null,
  t: (key: string, opts?: Record<string, unknown>) => string
): string {
  if (!value) return t('common.never');
  const d = new Date(value);
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return t('common.justNow');
  if (diffMin < 60) return t('common.minutesAgo', { count: diffMin });
  return formatDateTime(d);
}
