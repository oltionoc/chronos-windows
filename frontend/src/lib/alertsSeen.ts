// Per-viewer "seen" tracking for /reports/alerts — alerts are recomputed
// live on every fetch (no stable DB id), so "seen" is tracked by a stable
// composite key built from the fields that identify one real anomaly, and
// persisted in localStorage (per-browser, not synced — that's fine here,
// it's just a read/unread cue, not a source of truth).
import type { AlertItem } from '../api/types';

const STORAGE_KEY = 'chronos_alerts_seen';

export function alertKey(a: AlertItem): string {
  return [a.type, a.employee_id, a.work_date, a.device_label, a.username].join('|');
}

export function getSeenAlertKeys(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

export function markAlertsSeen(keys: string[]): void {
  try {
    const current = getSeenAlertKeys();
    keys.forEach((k) => current.add(k));
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...current]));
  } catch {
    /* private browsing / storage disabled — read/unread just won't persist */
  }
}

export function hasUnseenAlerts(alerts: AlertItem[]): boolean {
  const seen = getSeenAlertKeys();
  return alerts.some((a) => !seen.has(alertKey(a)));
}
