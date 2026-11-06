import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import it from "./locales/it.json";
import es from "./locales/es.json";
import fr from "./locales/fr.json";
import ja from "./locales/ja.json";

// Same languages as the game server (sil_server.LANGUAGES)
export const LOCALES = ["en", "it", "es", "fr", "ja"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", it: "Italiano", es: "Español", fr: "Français", ja: "日本語" };

export const isLocale = (v: string | undefined): v is Locale => !!v && (LOCALES as readonly string[]).includes(v);

export function detectLocale(saved?: string): Locale {
  if (isLocale(saved)) return saved;
  for (const lang of navigator.languages ?? [navigator.language]) {
    const base = lang.toLowerCase().split("-")[0];
    if (isLocale(base)) return base;
  }
  return "en";
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, it: { translation: it }, es: { translation: es }, fr: { translation: fr }, ja: { translation: ja } },
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React escapes text; names are never rendered as HTML
});

export default i18n;
