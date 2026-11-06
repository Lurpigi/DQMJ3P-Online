import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { apiUrl, useApi, type Freshness } from "../api";
import i18n, { LOCALE_NAMES, LOCALES, type Locale } from "../i18n";
import { applyTheme, setLocalePref, usePrefs } from "../prefs";
import { relative } from "../format";
import { Icon } from "./Icon";
import { L, useLocale } from "./L";

const NAV = [["", "nav.overview"], ["/championships", "nav.championships"], ["/players", "nav.players"],
  ["/battles", "nav.battles"], ["/monsters", "nav.monsters"], ["/records", "nav.records"]] as const;

export function Layout() {
  const locale = useLocale();
  const { t } = useTranslation();
  const [prefs, update] = usePrefs();
  const loc = useLocation();
  const navigate = useNavigate();
  const meta = useApi<{ freshness: Freshness[] }>(apiUrl("/meta"), 60000);

  useEffect(() => {
    if (i18n.language !== locale) i18n.changeLanguage(locale);
    document.documentElement.lang = locale;
    setLocalePref(locale);
  }, [locale]);
  useEffect(() => applyTheme(prefs.theme), [prefs.theme]);
  useEffect(() => { document.getElementById("main")?.focus({ preventScroll: true }); window.scrollTo(0, 0); }, [loc.pathname]);

  // Changing language keeps the page and its filters
  const switchLocale = (next: Locale) => navigate(`/${next}${loc.pathname.replace(/^\/[a-z]{2}(?=\/|$)/, "")}${loc.search}`);
  const cycleTheme = () => update({ theme: prefs.theme === "system" ? "dark" : prefs.theme === "dark" ? "light" : "system" });
  const fresh = meta.data?.freshness ?? [];
  const failing = fresh.some((f) => f.failing || (f.lag_seconds ?? 0) > 600);
  const newest = fresh.map((f) => f.as_of).filter(Boolean).sort().pop();

  return (
    <>
      <a className="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>{t("nav.skip")}</a>
      <header className="site-header">
        <div className="wrap header-row">
          <L to="/" className="brand" aria-label={t("brand.home")}>
            <img src={`${import.meta.env.BASE_URL}logo.png`} alt="" width={32} height={32} />
            <span><strong>DQMJ3P Online</strong><small>{t("brand.tagline")}</small></span>
          </L>
          <div className="header-tools">
            <label className="sr-only" htmlFor="locale">{t("nav.language")}</label>
            <select id="locale" value={locale} onChange={(e) => switchLocale(e.target.value as Locale)}>
              {LOCALES.map((l) => <option key={l} value={l}>{LOCALE_NAMES[l]}</option>)}
            </select>
            <button type="button" className="btn btn-ghost theme-btn" onClick={cycleTheme}
                    aria-label={t("theme.label", { theme: t(`theme.${prefs.theme}`) })} title={t(`theme.${prefs.theme}`)}>
              <Icon name={prefs.theme === "dark" ? "moon" : prefs.theme === "light" ? "sun" : "system"} />
            </button>
          </div>
        </div>
        <nav className="wrap main-nav" aria-label={t("nav.main")}>
          {NAV.map(([path, key]) => (
            <NavLink key={key} to={`/${locale}${path}`} end={path === ""} className={({ isActive }) => (isActive ? "active" : undefined)}>{t(key)}</NavLink>
          ))}
        </nav>
      </header>
      <main id="main" tabIndex={-1} className="wrap">
        <Outlet />
      </main>
      <footer className="site-footer">
        <div className="wrap footer-row">
          <span className={failing ? "fresh fresh-bad" : "fresh"}>
            {failing ? t("freshness.delayed") : newest ? t("freshness.updated", { when: relative(newest, locale) }) : t("freshness.unknown")}
          </span>
          <nav aria-label={t("nav.secondary")}>
            <L to="/status">{t("nav.status")}</L>
            <L to="/about">{t("nav.about")}</L>
          </nav>
        </div>
        <p className="wrap copyright">{t("footer.copyright")} {t("footer.unofficial")}</p>
      </footer>
    </>
  );
}
