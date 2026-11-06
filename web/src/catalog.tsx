// Monster catalog (server/dashboard/data/monsters.json, copied to monsters/catalog.json at build).
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export interface Species {
  id: number; names: Partial<Record<"en" | "it" | "fr" | "ja", string>>; rank: number | null; family: number | null;
  size: number; stats: number[]; art: string | null; story_copy?: boolean;
}
export interface Art { file: string; tiles: number; sheet_name: string; match: string }
export interface CatalogData {
  version: string; generated: string; families: Record<string, string>;
  species: Species[]; art: Record<string, Art>;
  locations: Record<string, { en: string; short?: string; ja?: string }>;
  items: Record<string, Partial<Record<"en" | "it" | "fr", string>>>;
}
export interface Catalog extends CatalogData { byId: Map<number, Species> }

const Ctx = createContext<Catalog | null>(null);
let loading: Promise<Catalog> | null = null;

function loadCatalog(): Promise<Catalog> {
  loading ??= fetch(`${import.meta.env.BASE_URL}monsters/catalog.json`)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((data: CatalogData) => ({ ...data, byId: new Map(data.species.map((s) => [s.id, s])) }))
    .catch((e) => { loading = null; throw e; });
  return loading;
}

export function CatalogProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  useEffect(() => { loadCatalog().then(setCatalog, () => setCatalog(null)); }, []);
  return <Ctx.Provider value={catalog}>{children}</Ctx.Provider>;
}

export const useCatalog = () => useContext(Ctx);

/** Localized name: requested language, then English, Japanese, then the species id. */
export function speciesName(cat: Catalog | null, id: number, locale: string) {
  const names = cat?.byId.get(id)?.names;
  const key = locale as keyof Species["names"];
  return names?.[key] || names?.en || names?.ja || `#${id}`;
}

export function itemName(cat: Catalog | null, id: number, locale: string) {
  const names = cat?.items[String(id)];
  return names?.[locale as "en"] || names?.en || `#${id}`;
}

export function locationName(cat: Catalog | null, id: number | null | undefined, locale: string) {
  if (id === null || id === undefined) return null;
  const loc = cat?.locations[String(id)];
  if (!loc) return null;
  return (locale === "ja" && loc.ja) || loc.en;
}

export function artOf(cat: Catalog | null, id: number): Art | null {
  const s = cat?.byId.get(id);
  return s?.art ? cat!.art[s.art] ?? null : null;
}
