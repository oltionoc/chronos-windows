import { useEffect, useRef, useState } from 'react';
import type { SelectHTMLAttributes } from 'react';
import { ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { baseFieldClasses, fieldBorder, FieldMessage, type FieldBaseProps } from './Input';
import { SearchInput } from './Input';
import { Checkbox } from './Controls';

export interface SelectOption {
  value: string | number;
  label: string;
}

type SelectProps = FieldBaseProps &
  Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> & {
    options: SelectOption[];
    placeholder?: string;
    // Shows the red-asterisk "required" label styling without wiring up
    // native HTML5 required validation — for fields that are visually
    // required but must not hard-block Save (DESIGN_SPEC §5.23, Users
    // form's Assigned Location field).
    requiredMark?: boolean;
  };

export function Select({
  label,
  error,
  hint,
  containerClassName,
  className,
  options,
  placeholder,
  id,
  name,
  required,
  requiredMark,
  ...rest
}: SelectProps) {
  const selectId = id || name;
  return (
    <div className={containerClassName}>
      {label && (
        <label htmlFor={selectId} className="mb-1.5 block text-label text-neutral-700">
          {label}
          {(required || requiredMark) && <span className="text-danger-600"> *</span>}
        </label>
      )}
      <div className="relative">
        <select
          id={selectId}
          name={name}
          required={required}
          className={clsx(baseFieldClasses, fieldBorder(!!error), 'appearance-none pr-8', className)}
          {...rest}
        >
          {placeholder !== undefined && <option value="">{placeholder}</option>}
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown
          size={16}
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-neutral-500"
        />
      </div>
      <FieldMessage error={error} hint={hint} />
    </div>
  );
}

interface SearchableSelectProps extends FieldBaseProps {
  options: SelectOption[];
  value: string | number | null;
  onChange: (value: string | number | null) => void;
  placeholder?: string;
  disabled?: boolean;
  searchPlaceholder?: string;
  noResultsLabel?: string;
  id?: string;
}

export function SearchableSelect({
  label,
  error,
  hint,
  containerClassName,
  options,
  value,
  onChange,
  placeholder,
  disabled,
  searchPlaceholder,
  noResultsLabel,
  id,
}: SearchableSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const selected = options.find((o) => String(o.value) === String(value));
  const filtered = query
    ? options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))
    : options;

  return (
    <div className={containerClassName} ref={ref}>
      {label && <label className="mb-1.5 block text-label text-neutral-700">{label}</label>}
      <div className="relative">
        <button
          type="button"
          id={id}
          disabled={disabled}
          onClick={() => setOpen((o) => !o)}
          className={clsx(
            baseFieldClasses,
            fieldBorder(!!error),
            'flex items-center justify-between text-left'
          )}
        >
          <span className={clsx('truncate', selected ? 'text-neutral-800' : 'text-neutral-400')}>
            {selected ? selected.label : placeholder || ''}
          </span>
          <ChevronDown size={16} className="ml-2 shrink-0 text-neutral-500" />
        </button>
        {open && (
          <div className="absolute z-popover mt-1 w-full rounded-lg border border-neutral-200 bg-white shadow-md">
            <div className="border-b border-neutral-200 p-2">
              <SearchInput value={query} onChange={setQuery} debounceMs={0} placeholder={searchPlaceholder} />
            </div>
            <ul className="max-h-[280px] overflow-y-auto py-1">
              {filtered.length === 0 && (
                <li className="px-3 py-2 text-caption text-neutral-500">{noResultsLabel ?? t('common.noResults')}</li>
              )}
              {filtered.map((o) => (
                <li key={o.value}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange(o.value);
                      setOpen(false);
                      setQuery('');
                    }}
                    className={clsx(
                      'block w-full px-3 py-2 text-left text-body hover:bg-neutral-50',
                      String(o.value) === String(value) && 'bg-primary-50 text-primary-700'
                    )}
                  >
                    {o.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <FieldMessage error={error} hint={hint} />
    </div>
  );
}

interface MultiSelectProps extends FieldBaseProps {
  options: SelectOption[];
  value: (string | number)[];
  onChange: (value: (string | number)[]) => void;
  placeholder?: string;
  allLabel?: string;
}

// Multi-select filter (used for Attendance Status filter — DESIGN_SPEC §5.12,
// "Status Select (multi: present/late/absent/on_leave/holiday/not_scheduled)").
// Not a named component in §6's component map; implemented as a variant of
// Select using the same popover pattern as SearchableSelect.
export function MultiSelect({ label, containerClassName, options, value, onChange, placeholder, allLabel }: MultiSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  function toggle(v: string | number) {
    if (value.includes(v)) onChange(value.filter((x) => x !== v));
    else onChange([...value, v]);
  }

  const summary =
    value.length === 0
      ? (allLabel ?? placeholder ?? '')
      : value.length === 1
        ? options.find((o) => o.value === value[0])?.label
        : t('common.itemsSelected', { count: value.length });

  return (
    <div className={containerClassName} ref={ref}>
      {label && <label className="mb-1.5 block text-label text-neutral-700">{label}</label>}
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className={clsx(baseFieldClasses, fieldBorder(false), 'flex items-center justify-between text-left')}
        >
          <span className={clsx('truncate', value.length ? 'text-neutral-800' : 'text-neutral-400')}>{summary}</span>
          <ChevronDown size={16} className="ml-2 shrink-0 text-neutral-500" />
        </button>
        {open && (
          <div className="absolute z-popover mt-1 w-full min-w-[200px] rounded-lg border border-neutral-200 bg-white py-1 shadow-md">
            <ul className="max-h-[280px] overflow-y-auto">
              {options.map((o) => (
                <li key={o.value} className="px-3 py-1.5 hover:bg-neutral-50">
                  <Checkbox checked={value.includes(o.value)} onChange={() => toggle(o.value)} label={o.label} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
