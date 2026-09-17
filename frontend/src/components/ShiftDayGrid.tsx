import { Plus, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Toggle } from './ui/Controls';
import { Button } from './ui/Button';
import type { ShiftScheduleDay, ShiftWorkWindow } from '../api/types';

interface ShiftDayGridProps {
  days: ShiftScheduleDay[];
  onChange: (days: ShiftScheduleDay[]) => void;
}

function emptyBreak() {
  return { break_start_time: '12:00', break_end_time: '12:30', is_paid: false };
}

// A second block defaults to an afternoon/evening return, the shape a split
// shift almost always takes.
function emptyWorkWindow() {
  return { work_start_time: '17:00', work_end_time: '21:00' };
}

const TIME_INPUT_CLASS =
  'h-9 rounded-md border border-neutral-300 bg-white px-3 text-body text-neutral-800 transition-[border-color] duration-100 ease-out focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600 focus:ring-offset-0';

// Shift Day Grid (custom) — DESIGN_SPEC §6.15
export function ShiftDayGrid({ days, onChange }: ShiftDayGridProps) {
  const { t } = useTranslation();

  function updateDay(index: number, patch: Partial<ShiftScheduleDay>) {
    const next = days.slice();
    next[index] = { ...next[index], ...patch };
    onChange(next);
  }

  function toggleWorkingDay(index: number, working: boolean) {
    const existing = days[index].work_windows ?? [];
    updateDay(index, {
      is_working_day: working,
      work_windows: working
        ? existing.length > 0
          ? existing
          : [{ work_start_time: days[index].work_start_time || '08:00', work_end_time: days[index].work_end_time || '16:00' }]
        : [],
      break_windows: working ? days[index].break_windows : [],
    });
  }

  function updateWorkWindow(dayIndex: number, windowIndex: number, patch: Partial<ShiftWorkWindow>) {
    const next = (days[dayIndex].work_windows ?? []).slice();
    next[windowIndex] = { ...next[windowIndex], ...patch };
    updateDay(dayIndex, { work_windows: next });
  }

  function addWorkWindow(index: number) {
    updateDay(index, { work_windows: [...(days[index].work_windows ?? []), emptyWorkWindow()] });
  }

  function removeWorkWindow(dayIndex: number, windowIndex: number) {
    updateDay(dayIndex, {
      work_windows: (days[dayIndex].work_windows ?? []).filter((_, i) => i !== windowIndex),
    });
  }

  function addBreak(index: number) {
    updateDay(index, { break_windows: [...days[index].break_windows, emptyBreak()] });
  }

  function updateBreak(dayIndex: number, breakIndex: number, patch: Partial<ShiftScheduleDay['break_windows'][number]>) {
    const next = days[dayIndex].break_windows.slice();
    next[breakIndex] = { ...next[breakIndex], ...patch };
    updateDay(dayIndex, { break_windows: next });
  }

  function removeBreak(dayIndex: number, breakIndex: number) {
    updateDay(
      dayIndex,
      { break_windows: days[dayIndex].break_windows.filter((_, i) => i !== breakIndex) }
    );
  }

  return (
    <div>
      {days.map((day, index) => (
        <div
          key={day.day_of_week}
          className="mb-3 rounded-md border border-neutral-200 p-3 last:mb-0 md:mb-0 md:rounded-none md:border-0 md:border-b md:border-neutral-200 md:p-0 md:py-3 md:last:border-b-0 md:flex md:items-start md:gap-4"
        >
          <div className="mb-2 flex items-center justify-between md:mb-0 md:w-[100px] md:shrink-0 md:justify-start">
            <span className="text-body font-medium text-neutral-800">
              {t(`shiftSchedules.days.${day.day_of_week}`)}
            </span>
            <span className="md:ml-3">
              <Toggle checked={day.is_working_day} onChange={(v) => toggleWorkingDay(index, v)} />
            </span>
          </div>

          {!day.is_working_day ? (
            <p className="text-caption text-neutral-400">{t('shiftSchedules.notWorkingDay')}</p>
          ) : (
            <div className="flex flex-1 flex-col gap-3">
              {(day.work_windows ?? []).map((w, wIndex) => (
                <div key={wIndex} className="flex flex-wrap items-center gap-2">
                  <input
                    type="time"
                    value={w.work_start_time}
                    onChange={(e) => updateWorkWindow(index, wIndex, { work_start_time: e.target.value })}
                    className={TIME_INPUT_CLASS}
                  />
                  <span className="text-neutral-400">–</span>
                  <input
                    type="time"
                    value={w.work_end_time}
                    onChange={(e) => updateWorkWindow(index, wIndex, { work_end_time: e.target.value })}
                    className={TIME_INPUT_CLASS}
                  />
                  {(day.work_windows ?? []).length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeWorkWindow(index, wIndex)}
                      className="text-neutral-400 hover:text-danger-600"
                      aria-label="remove work block"
                    >
                      <X size={16} />
                    </button>
                  )}
                </div>
              ))}
              <div>
                <Button variant="link" leftIcon={<Plus size={14} />} onClick={() => addWorkWindow(index)} type="button">
                  {t('shiftSchedules.addWorkBlock')}
                </Button>
              </div>

              {day.break_windows.length > 0 && (
                <div className="flex flex-col gap-2 pl-4">
                  {day.break_windows.map((bw, bIndex) => (
                    <div key={bIndex} className="flex flex-wrap items-center gap-2">
                      <input
                        type="time"
                        value={bw.break_start_time}
                        onChange={(e) => updateBreak(index, bIndex, { break_start_time: e.target.value })}
                        className="h-9 rounded-md border border-neutral-300 bg-white px-3 text-body text-neutral-800 transition-[border-color] duration-100 ease-out focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600 focus:ring-offset-0"
                      />
                      <span className="text-neutral-400">–</span>
                      <input
                        type="time"
                        value={bw.break_end_time}
                        onChange={(e) => updateBreak(index, bIndex, { break_end_time: e.target.value })}
                        className="h-9 rounded-md border border-neutral-300 bg-white px-3 text-body text-neutral-800 transition-[border-color] duration-100 ease-out focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600 focus:ring-offset-0"
                      />
                      <Toggle
                        checked={bw.is_paid}
                        onChange={(v) => updateBreak(index, bIndex, { is_paid: v })}
                        label={t('shiftSchedules.paid')}
                      />
                      <button
                        type="button"
                        onClick={() => removeBreak(index, bIndex)}
                        className="text-neutral-400 hover:text-danger-600"
                        aria-label="remove break"
                      >
                        <X size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div className="pl-4">
                <Button variant="link" leftIcon={<Plus size={14} />} onClick={() => addBreak(index)} type="button">
                  {t('shiftSchedules.addBreak')}
                </Button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
