import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

/**
 * Sets `document.title` from i18n (call once per route). Pass a key under the default `translation` namespace.
 */
export function useDocumentTitle(titleKey: string) {
  const { t, i18n } = useTranslation();

  useEffect(() => {
    document.title = t(titleKey);
  }, [t, titleKey, i18n.language]);
}
