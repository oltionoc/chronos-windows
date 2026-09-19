import { useEffect, useState } from 'react';

// Optional company logo, set once at install (BRANDING_LOGO_PATH) and served
// publicly by the API. Probed once per page load and cached module-wide so
// every brand spot agrees without a request each. Until it resolves we render
// the built-in Chronos mark, so there's never a broken-image flash; if a logo
// is present the components swap to it.
const BRAND_LOGO_URL = '/api/v1/branding/logo';
type BrandState = 'unknown' | 'present' | 'absent';
let brandState: BrandState = 'unknown';
const brandListeners = new Set<() => void>();

function useBrandLogo(): BrandState {
  const [, force] = useState(0);
  useEffect(() => {
    const rerender = () => force((x) => x + 1);
    brandListeners.add(rerender);
    if (brandState === 'unknown') {
      const img = new Image();
      img.onload = () => {
        brandState = 'present';
        brandListeners.forEach((l) => l());
      };
      img.onerror = () => {
        brandState = 'absent';
        brandListeners.forEach((l) => l());
      };
      img.src = BRAND_LOGO_URL;
    }
    return () => {
      brandListeners.delete(rerender);
    };
  }, []);
  return brandState;
}

// Official chronos mark (source: ~/Chronos Attendance System Logo/logo/).
// Single path, inherits color via currentColor so it works on the dark
// sidebar (white) or a light background (primary-600) without a variant prop.
// When a company logo is installed it replaces the mark everywhere.
export function Logo({ size = 24, className }: { size?: number; className?: string }) {
  if (useBrandLogo() === 'present') {
    return (
      <img
        src={BRAND_LOGO_URL}
        width={size}
        height={size}
        className={className}
        alt="logo"
        style={{ objectFit: 'contain' }}
      />
    );
  }
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
  if (useBrandLogo() === 'present') {
    // A company logo replaces the whole Chronos lockup; aspect ratio is the
    // uploaded image's own, capped to the requested width.
    return (
      <img
        src={BRAND_LOGO_URL}
        className={className}
        alt="logo"
        style={{ width, height: 'auto', maxHeight: (width / 520) * 100 * 1.6, objectFit: 'contain' }}
      />
    );
  }
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
