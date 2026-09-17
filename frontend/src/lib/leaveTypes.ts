// Leave type names are bilingual data (admin-entered, not an i18n key) —
// the backend always returns both name_en/name_sq and the frontend picks
// which one to show based on the active UI language.
export function localizedLeaveTypeName(
  names: { name_en?: string | null; name_sq?: string | null },
  language: string
): string {
  const preferred = language.startsWith('sq') ? names.name_sq : names.name_en;
  return preferred || names.name_en || names.name_sq || '';
}
