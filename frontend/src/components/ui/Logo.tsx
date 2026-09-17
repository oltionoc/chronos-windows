// Official chronos mark (source: ~/Chronos Attendance System Logo/logo/).
// Single path, inherits color via currentColor so it works on the dark
// sidebar (white) or a light background (primary-600) without a variant prop.
export function Logo({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className={className}
      role="img"
      aria-label="chronos"
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M100 0 H0 V100 H100 V64 H50 V36 H100 Z M50 28 A22 22 0 1 1 49.99 28 Z"
        fill="currentColor"
      />
    </svg>
  );
}

const LOCKUP_COLOR = { dark: '#232326', light: '#FFFFFF' } as const;

// Full lockup (mark + "Chronos" wordmark baked into one graphic).
// `dark` (source: chronos-lockup-dark.svg) is the delivered asset, for light
// backgrounds. `light` is the same shape recolored white — no source file
// was provided for it, built here for the dark sidebar. Fixed color per
// variant, not currentColor — this is a brand asset, not a context-adaptive
// primitive like Logo above.
export function LogoLockup({
  width = 220,
  variant = 'dark',
  className,
}: {
  width?: number;
  variant?: 'dark' | 'light';
  className?: string;
}) {
  const color = LOCKUP_COLOR[variant];
  return (
    <svg width={width} height={(width / 520) * 100} viewBox="0 0 520 100" className={className} role="img" aria-label="chronos">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M100 0 H0 V100 H100 V64 H50 V36 H100 Z M50 28 A22 22 0 1 1 49.99 28 Z"
        fill={color}
      />
      <text x="132" y="72" fontFamily="Space Grotesk, Archivo, Helvetica, sans-serif" fontSize="72" letterSpacing="-1" fill={color}>
        Chronos
      </text>
    </svg>
  );
}
