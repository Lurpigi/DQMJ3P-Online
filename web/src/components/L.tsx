import { Link, useParams, useSearchParams, type LinkProps } from "react-router";
import { isLocale } from "../i18n";

export function useLocale() {
  const { locale } = useParams();
  return isLocale(locale) ? locale : "en";
}

/** A link inside the current language: <L to="/players/p123">. */
export function L({ to, ...rest }: Omit<LinkProps, "to"> & { to: string }) {
  const locale = useLocale();
  return <Link to={`/${locale}${to === "/" ? "" : to}`} {...rest} />;
}

/** Filters kept in the URL (shareable, survive reloads): get, set (empty removes), reset all. */
export function useQuery() {
  const [params, setParams] = useSearchParams();
  const get = (k: string) => params.get(k) ?? "";
  const set = (k: string, v: string, drop: string[] = []) => {
    const n = new URLSearchParams(params);
    if (v) n.set(k, v); else n.delete(k);
    drop.forEach((d) => n.delete(d));
    setParams(n, { replace: true });
  };
  const reset = () => setParams({}, { replace: true });
  return { params, get, set, reset, any: params.size > 0 };
}
