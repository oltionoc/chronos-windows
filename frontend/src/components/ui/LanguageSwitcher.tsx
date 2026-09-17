import { useTranslation } from 'react-i18next';
import clsx from 'clsx';

// Language Switcher — DESIGN_SPEC §6.21
export function LanguageSwitcher({ size = 'compact' }: { size?: 'compact' | 'large' }) {
  const { i18n } = useTranslation();

  if (size === 'large') {
    return (
      <div className="flex gap-3">
        {(['sq', 'en'] as const).map((lng) => {
          const active = i18n.language === lng;
          return (
            <button
              key={lng}
              type="button"
              onClick={() => i18n.changeLanguage(lng)}
              className={clsx(
                'flex-1 rounded-md border px-4 py-3 text-center text-body font-medium transition-colors',
                active
                  ? 'border-primary-600 bg-primary-50 text-primary-700'
                  : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50'
              )}
            >
              {lng === 'sq' ? 'Shqip' : 'English'}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="inline-flex rounded-full bg-neutral-100 p-0.5">
      {(['sq', 'en'] as const).map((lng) => {
        const active = i18n.language === lng;
        return (
          <button
            key={lng}
            type="button"
            onClick={() => i18n.changeLanguage(lng)}
            className={clsx(
              'rounded-full px-3 py-1 text-xs font-medium transition-colors',
              active ? 'bg-white text-neutral-900 shadow-sm' : 'text-neutral-500 hover:text-neutral-700'
            )}
          >
            {lng.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}
