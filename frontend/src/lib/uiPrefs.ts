import { useEffect, useState } from 'react';

// Per-browser UI preferences. Currently just whether the weekly schedule
// (Orari Javor) shows in the sidebar. This client plans every day in Orari
// Ditor, so the weekly view is hidden by default and revealed from Settings
// when someone actually wants the fixed-weekly fallback view. Hiding the link
// does NOT disable the weekly fallback itself — a day with no Orari Ditor entry
// still falls back to any weekly schedule server-side.
const SHOW_WEEKLY_KEY = 'chronos.showWeeklySchedule';

type Listener = () => void;
const listeners = new Set<Listener>();

function read(): boolean {
  try {
    return localStorage.getItem(SHOW_WEEKLY_KEY) === '1';
  } catch {
    return false;
  }
}

let showWeekly = read();

export function getShowWeeklySchedule(): boolean {
  return showWeekly;
}

export function setShowWeeklySchedule(value: boolean): void {
  showWeekly = value;
  try {
    localStorage.setItem(SHOW_WEEKLY_KEY, value ? '1' : '0');
  } catch {
    /* private mode / blocked storage — keep the in-memory value for this session */
  }
  listeners.forEach((l) => l());
}

export function useShowWeeklySchedule(): boolean {
  const [, force] = useState(0);
  useEffect(() => {
    const l = () => force((x) => x + 1);
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
  return showWeekly;
}
