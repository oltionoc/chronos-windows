// primary-500, violet-500, success-600, warning-600, sky-500, pink-500 — DESIGN_SPEC §6.22
const COLORS = ['#68686F', '#8C7086', '#16A34A', '#D97706', '#0EA5E9', '#EC4899'];

function colorForName(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return COLORS[Math.abs(hash) % COLORS.length];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? '';
  const last = parts.length > 1 ? parts[parts.length - 1][0] : '';
  return (first + last).toUpperCase();
}

// Avatar — DESIGN_SPEC §6.22
export function Avatar({ name, size = 32 }: { name: string; size?: 24 | 32 }) {
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{
        backgroundColor: colorForName(name || '?'),
        width: size,
        height: size,
        fontSize: size === 24 ? 10 : 12,
      }}
    >
      {initials(name || '?')}
    </span>
  );
}
