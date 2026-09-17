import { forwardRef, useEffect, useState } from 'react';
import type { InputHTMLAttributes } from 'react';
import { Search, X } from 'lucide-react';
import clsx from 'clsx';

export interface FieldBaseProps {
  label?: string;
  error?: string;
  hint?: string;
  containerClassName?: string;
}

export const baseFieldClasses =
  'h-9 w-full rounded-md border bg-white px-3 text-body text-neutral-800 placeholder:text-neutral-400 transition-[border-color] duration-100 ease-out focus:outline-none disabled:cursor-not-allowed disabled:bg-neutral-50 disabled:text-neutral-400 disabled:border-neutral-200 read-only:bg-neutral-50 read-only:border-neutral-200 read-only:text-neutral-800';

// Crisp doubled-line focus ring per DESIGN_SPEC §1.9 (overrides the generic
// offset-outline for Input/Select/Textarea): border-color to primary-600 +
// a flush 1px ring (box-shadow 0 0 0 1px, zero offset/blur), danger-500 for
// error+focus. Used on elements that receive focus directly.
export function fieldBorder(hasError?: boolean) {
  return hasError
    ? 'border-danger-500 focus:border-danger-500 focus:ring-1 focus:ring-danger-500 focus:ring-offset-0'
    : 'border-neutral-300 hover:border-neutral-400 focus:border-primary-600 focus:ring-1 focus:ring-primary-600 focus:ring-offset-0';
}

// Same ring treatment for wrapper elements where the focusable control is a
// child (e.g. CurrencyInput's `€`-prefixed wrapper div) — uses `focus-within`
// since the wrapper itself never receives focus.
export function fieldBorderWithin(hasError?: boolean) {
  return hasError
    ? 'border-danger-500 focus-within:border-danger-500 focus-within:ring-1 focus-within:ring-danger-500 focus-within:ring-offset-0'
    : 'border-neutral-300 hover:border-neutral-400 focus-within:border-primary-600 focus-within:ring-1 focus-within:ring-primary-600 focus-within:ring-offset-0';
}

export function FieldMessage({ error, hint }: { error?: string; hint?: string }) {
  if (error) return <p className="mt-1 text-error text-danger-600">{error}</p>;
  if (hint) return <p className="mt-1 text-caption text-neutral-500">{hint}</p>;
  return null;
}

type InputProps = FieldBaseProps & InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, containerClassName, className, id, name, required, ...rest },
  ref
) {
  const inputId = id || name;
  return (
    <div className={containerClassName}>
      {label && (
        <label htmlFor={inputId} className="mb-1.5 block text-label text-neutral-700">
          {label}
          {required && <span className="text-danger-600"> *</span>}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        name={name}
        required={required}
        className={clsx(baseFieldClasses, fieldBorder(!!error), className)}
        {...rest}
      />
      <FieldMessage error={error} hint={hint} />
    </div>
  );
});

interface CurrencyInputProps extends FieldBaseProps {
  name?: string;
  id?: string;
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
  required?: boolean;
}

export function CurrencyInput({
  label,
  error,
  hint,
  containerClassName,
  value,
  onChange,
  disabled,
  required,
  id,
  name,
}: CurrencyInputProps) {
  const [text, setText] = useState(value != null ? value.toFixed(2) : '');

  useEffect(() => {
    setText(value != null ? value.toFixed(2) : '');
  }, [value]);

  const inputId = id || name;

  return (
    <div className={containerClassName}>
      {label && (
        <label htmlFor={inputId} className="mb-1.5 block text-label text-neutral-700">
          {label}
          {required && <span className="text-danger-600"> *</span>}
        </label>
      )}
      <div
        className={clsx(
          'flex h-9 items-center rounded-md border bg-white transition-[border-color] duration-100 ease-out',
          fieldBorderWithin(!!error),
          disabled && 'cursor-not-allowed bg-neutral-50 border-neutral-200'
        )}
      >
        <span className="pl-3 select-none text-body text-neutral-500">€</span>
        <input
          id={inputId}
          name={name}
          type="text"
          inputMode="decimal"
          disabled={disabled}
          required={required}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => {
            const normalized = text.replace(/\./g, '').replace(',', '.');
            const parsed = parseFloat(normalized === '' ? text : normalized);
            if (Number.isFinite(parsed)) {
              onChange(parsed);
              setText(parsed.toFixed(2));
            } else {
              onChange(null);
              setText('');
            }
          }}
          className="h-full w-full flex-1 rounded-md bg-transparent px-2 text-right text-body tabular-nums text-neutral-800 focus:outline-none disabled:cursor-not-allowed disabled:text-neutral-400"
        />
      </div>
      <FieldMessage error={error} hint={hint} />
    </div>
  );
}

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  debounceMs?: number;
  className?: string;
}

export function SearchInput({ value, onChange, placeholder, debounceMs = 300, className }: SearchInputProps) {
  const [local, setLocal] = useState(value);

  useEffect(() => {
    setLocal(value);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (local !== value) onChange(local);
    }, debounceMs);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local]);

  return (
    <div className={clsx('relative h-9', className)}>
      <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
      <input
        type="text"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder={placeholder}
        className={clsx(
          baseFieldClasses,
          fieldBorder(false),
          'pl-9',
          local ? 'pr-8' : 'pr-3'
        )}
      />
      {local && (
        <button
          type="button"
          onClick={() => setLocal('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600"
          aria-label="clear"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
