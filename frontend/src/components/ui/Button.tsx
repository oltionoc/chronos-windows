import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import clsx from 'clsx';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'danger-outline' | 'success-outline' | 'link';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  iconOnly?: boolean;
  leftIcon?: ReactNode;
}

// Press-scale + transition timing per DESIGN_SPEC §1.9 — Primary/Secondary/
// Danger/Danger-outline (and the success-outline confirm variant, which
// shares the same filled/bordered treatment) only, not Ghost/Link.
// `transition: background-color 150ms ease-out, transform 100ms ease-out`.
//
// Written as an arbitrary *property* (`[transition:...]`), not an arbitrary
// value on `transition-*`. `transition-[...]` sets `transition-property`,
// which only accepts property names — passing the full shorthand there
// emitted `transition-property: background-color .15s ease-out, transform
// .1s ease-out`, which the parser drops. Only the utility's sibling
// `transition-duration`/`transition-timing-function` survived, leaving every
// filled/bordered button transitioning `all` at 150ms ease-in-out (the
// initial `transition-property` value) instead of the two timings above.
const pressClasses = 'active:scale-[0.98] [transition:background-color_150ms_ease-out,transform_100ms_ease-out]';

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    `bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800 disabled:bg-neutral-200 disabled:text-neutral-400 ${pressClasses}`,
  secondary:
    `bg-white border border-neutral-300 text-neutral-700 hover:bg-neutral-50 hover:border-neutral-400 active:bg-neutral-100 disabled:bg-white disabled:border-neutral-200 disabled:text-neutral-300 ${pressClasses}`,
  ghost:
    'bg-transparent text-neutral-700 hover:bg-neutral-100 active:bg-neutral-200 disabled:text-neutral-300 transition-colors duration-150 ease-out',
  danger:
    `bg-danger-600 text-white hover:bg-danger-700 active:bg-danger-800 disabled:bg-danger-100 disabled:text-danger-300 ${pressClasses}`,
  'danger-outline':
    `bg-white border border-danger-300 text-danger-700 hover:bg-danger-50 active:bg-danger-100 disabled:border-danger-100 disabled:text-danger-200 ${pressClasses}`,
  // Not enumerated in DESIGN_SPEC §6.1's variant table, but explicitly required
  // by §6.18 ("Approve leave uses a success-outline Confirm button"). States
  // derived from the danger-outline pattern using the success color tokens.
  'success-outline':
    `bg-white border border-success-300 text-success-700 hover:bg-success-50 active:bg-success-100 disabled:border-success-100 disabled:text-success-200 ${pressClasses}`,
  link: 'bg-transparent text-primary-600 hover:text-primary-700 hover:underline p-0 h-auto disabled:text-neutral-300 transition-colors duration-150 ease-out',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-sm gap-1.5',
  md: 'h-9 px-4 text-sm gap-2',
  lg: 'h-10 px-5 text-sm gap-2',
};

const iconOnlySizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 w-8',
  md: 'h-9 w-9',
  lg: 'h-10 w-10',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  iconOnly = false,
  leftIcon,
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  const isLink = variant === 'link';
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center rounded-md font-medium',
        'disabled:cursor-not-allowed',
        !isLink && (iconOnly ? iconOnlySizeClasses[size] : sizeClasses[size]),
        variantClasses[variant],
        className
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? (
        <span className="relative inline-flex items-center justify-center gap-2">
          <Loader2 size={16} className="absolute animate-spin" />
          <span className="invisible inline-flex items-center gap-2">
            {leftIcon}
            {children}
          </span>
        </span>
      ) : (
        <>
          {leftIcon}
          {children}
        </>
      )}
    </button>
  );
}
