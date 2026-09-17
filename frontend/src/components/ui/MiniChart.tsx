import { useTranslation } from 'react-i18next';
import type { AttendanceTrendDay } from '../../api/types';

const STATUS_COLOR: Record<'present' | 'late' | 'absent' | 'on_leave', string> = {
  present: '#22C55E',
  late: '#F59E0B',
  absent: '#EF4444',
  on_leave: '#8C7086',
};

// Stacked daily bar chart, plain SVG — no charting library dependency.
// DESIGN_SPEC §1: dense/functional, status colors match Badge.tsx exactly.
export function AttendanceTrendChart({ data }: { data: AttendanceTrendDay[] }) {
  const { t } = useTranslation();
  const width = 640;
  const height = 160;
  const barGap = 4;
  const barWidth = data.length ? (width - barGap * (data.length - 1)) / data.length : 0;
  const max = Math.max(1, ...data.map((d) => d.present + d.late + d.absent + d.on_leave));

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height + 20}`}
        width="100%"
        height={height + 20}
        preserveAspectRatio="none"
        className="min-w-[480px]"
        role="img"
      >
        {data.map((d, i) => {
          const total = d.present + d.late + d.absent + d.on_leave;
          const x = i * (barWidth + barGap);
          let yOffset = height;
          const segments = (['present', 'late', 'absent', 'on_leave'] as const).map((key) => {
            const value = d[key];
            const h = (value / max) * height;
            yOffset -= h;
            return { key, y: yOffset, h, value };
          });
          // Manual DD/MM formatting from the ISO date string — `new Date(isoDateOnly)`
          // parses as UTC midnight, which `toLocaleDateString` can then shift by a day
          // in timezones behind UTC. Splitting the string avoids that entirely.
          const [, mm, dd] = d.work_date.split('-');
          const label = `${dd}/${mm}`;
          return (
            <g key={d.work_date}>
              {total === 0 ? (
                <rect x={x} y={height - 2} width={barWidth} height={2} rx={1} fill="#E2E8F0" />
              ) : (
                segments
                  .filter((s) => s.value > 0)
                  .map((s) => (
                    <rect
                      key={s.key}
                      x={x}
                      y={s.y}
                      width={barWidth}
                      height={Math.max(s.h, 2)}
                      fill={STATUS_COLOR[s.key]}
                      rx={1}
                    >
                      <title>
                        {label}, {t(`status.attendance.${s.key}`)}: {s.value}
                      </title>
                    </rect>
                  ))
              )}
              <text
                x={x + barWidth / 2}
                y={height + 14}
                textAnchor="middle"
                fontSize="9"
                fontFamily="JetBrains Mono, monospace"
                fill="#94A3B8"
              >
                {i % 2 === 0 || data.length <= 10 ? label : ''}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-4 text-caption text-neutral-500">
        {(['present', 'late', 'absent', 'on_leave'] as const).map((key) => (
          <span key={key} className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: STATUS_COLOR[key] }} />
            {t(`status.attendance.${key}`)}
          </span>
        ))}
      </div>
    </div>
  );
}
