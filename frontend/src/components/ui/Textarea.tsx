import { forwardRef } from 'react';
import type { TextareaHTMLAttributes } from 'react';
import clsx from 'clsx';
import { fieldBorder, FieldMessage, type FieldBaseProps } from './Input';

type TextareaProps = FieldBaseProps & TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, error, hint, containerClassName, className, id, name, rows = 3, required, ...rest },
  ref
) {
  const textareaId = id || name;
  return (
    <div className={containerClassName}>
      {label && (
        <label htmlFor={textareaId} className="mb-1.5 block text-label text-neutral-700">
          {label}
          {required && <span className="text-danger-600"> *</span>}
        </label>
      )}
      <textarea
        ref={ref}
        id={textareaId}
        name={name}
        required={required}
        rows={rows}
        className={clsx(
          'w-full resize-y rounded-md border bg-white px-3 py-2 text-body text-neutral-800 placeholder:text-neutral-400 transition-[border-color] duration-100 ease-out focus:outline-none disabled:cursor-not-allowed disabled:bg-neutral-50 disabled:text-neutral-400',
          fieldBorder(!!error),
          className
        )}
        style={{ minHeight: '4.5rem' }}
        {...rest}
      />
      <FieldMessage error={error} hint={hint} />
    </div>
  );
});
