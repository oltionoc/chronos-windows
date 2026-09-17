import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import sq from './locales/sq.json';
import en from './locales/en.json';

const STORAGE_KEY = 'checkin_language';

function getInitialLanguage(): 'sq' | 'en' {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'sq' || stored === 'en') return stored;
  return 'sq'; // Albanian default per DESIGN_SPEC.md / BLUEPRINT.md
}

i18n.use(initReactI18next).init({
  resources: {
    sq: { translation: sq },
    en: { translation: en },
  },
  lng: getInitialLanguage(),
  fallbackLng: 'sq',
  interpolation: { escapeValue: false },
  returnNull: false,
});

i18n.on('languageChanged', (lng) => {
  localStorage.setItem(STORAGE_KEY, lng);
});

export default i18n;
