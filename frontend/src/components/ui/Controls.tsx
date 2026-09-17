import { Check, Loader2, Minus } from 'lucide-react';
import clsx from 'clsx';

// ---- Checkbox (DESIGN_SPEC §6.5) ----
interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  indeterminate?: boolean;
  disabled?: boolean;
  label?: string;
  id?: string;
}

export function Checkbox({ checked, onChange, indeterminate, disabled, label, id }: CheckboxProps) {
  return (
    <label
      htmlFor={id}
      className={clsx('inline-flex items-center gap-2', disabled ? 'cursor-not-allowed' : 'cursor-pointer')}
    >
      <span className="relative inline-flex h-4 w-4 shrink-0">
        <input
          type="checkbox"
          id={id}
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="peer sr-only"
        />
        <span
          className={clsx(
            'flex h-4 w-4 items-center justify-center rounded-sm border-[1.5px] transition-colors',
            disabled
              ? 'border-neutral-200 bg-neutral-100'
              : checked || indeterminate
                ? 'border-primary-600 bg-primary-600'
                : 'border-neutral-300 bg-white hover:border-neutral-400',
            'peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary-600'
          )}
        >
          {indeterminate ? (
            <Minus size={12} className={disabled ? 'text-neutral-400' : 'text-white'} />
          ) : checked ? (
            <Check size={12} className={disabled ? 'text-neutral-400' : 'text-white'} />
          ) : null}
        </span>
      </span>
      {label && <span className="text-body text-neutral-800">{label}</span>}
    </label>
  );
}

// ---- Toggle / Switch (DESIGN_SPEC §6.7) ----
interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  loading?: boolean;
  label?: string;
  id?: string;
}

export function Toggle({ checked, onChange, disabled, loading, label, id }: ToggleProps) {
  return (
    <label
      htmlFor={id}
      className={clsx('inline-flex items-center gap-2', disabled || loading ? 'cursor-not-allowed' : 'cursor-pointer')}
    >
      <span className="relative inline-block h-[22px] w-10 shrink-0">
        <input
          type="checkbox"
          id={id}
          checked={checked}
          disabled={disabled || loading}
          onChange={(e) => onChange(e.target.checked)}
          className="peer sr-only"
        />
        <span
          className={clsx(
            'absolute inset-0 rounded-full transition-colors',
            disabled ? (checked ? 'bg-primary-200' : 'bg-neutral-200') : checked ? 'bg-primary-600' : 'bg-neutral-300',
            'peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary-600'
          )}
        />
        <span
          className={clsx(
            'absolute top-[3px] h-4 w-4 rounded-full bg-white shadow-sm transition-transform',
            checked ? 'translate-x-[21px]' : 'translate-x-[3px]',
            disabled && !checked && 'bg-neutral-100'
          )}
        />
        {loading && (
          <span className="absolute inset-0 flex items-center justify-center">
            <Loader2 size={12} className="animate-spin text-white" />
          </span>
        )}
      </span>
      {label && <span className="text-body text-neutral-800">{label}</span>}
    </label>
  );
}

// ---- Radio Group (DESIGN_SPEC §6.6) ----
export interface RadioOption {
  value: string;
  label: string;
  description?: string;
}

interface RadioGroupProps {
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: RadioOption[];
  disabled?: boolean;
}

export function RadioGroup({ name, value, onChange, options, disabled }: RadioGroupProps) {
  return (
    <div className="flex flex-col gap-2">
      {options.map((opt) => {
        const selected = opt.value === value;
        return (
          <label
            key={opt.value}
            className={clsx(
              'flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2.5 transition-colors',
              selected ? 'border-primary-600 bg-primary-50' : 'border-neutral-200 hover:bg-neutral-50',
              disabled && 'cursor-not-allowed opacity-60'
            )}
          >
            <span className="relative mt-0.5 inline-flex h-4 w-4 shrink-0">
              <input
                type="radio"
                name={name}
                value={opt.value}
                checked={selected}
                disabled={disabled}
                onChange={() => onChange(opt.value)}
                className="peer sr-only"
              />
              <span
                className={clsx(
                  'flex h-4 w-4 items-center justify-center rounded-full border-[1.5px] transition-colors',
                  selected ? 'border-primary-600' : 'border-neutral-300',
                  'peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary-600'
                )}
              >
                {selected && <span className="h-2 w-2 rounded-full bg-primary-600" />}
              </span>
            </span>
            <span>
              <span className="block text-body text-neutral-800">{opt.label}</span>
              {opt.description && <span className="block text-caption text-neutral-500">{opt.description}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}
