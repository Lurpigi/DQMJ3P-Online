import { lazy, Suspense } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation, useParams } from "react-router";
import { CatalogProvider } from "./catalog";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { detectLocale, isLocale } from "./i18n";
import { getPrefs } from "./prefs";

const Overview = lazy(() => import("./pages/Overview"));
const Championships = lazy(() => import("./pages/Championships"));
const ChampionshipPage = lazy(() => import("./pages/Championship"));
const Players = lazy(() => import("./pages/Players"));
const PlayerPage = lazy(() => import("./pages/Player"));
const ResultPage = lazy(() => import("./pages/Result"));
const Battles = lazy(() => import("./pages/Battles"));
const Monsters = lazy(() => import("./pages/Monsters"));
const MonsterPage = lazy(() => import("./pages/Monster"));
const Records = lazy(() => import("./pages/Records"));
const StatusPage = lazy(() => import("./pages/Status"));
const About = lazy(() => import("./pages/About"));
const NotFound = lazy(() => import("./pages/NotFound"));

function ToLocale() {
  const loc = useLocation();
  return <Navigate replace to={`/${detectLocale(getPrefs().locale)}${loc.pathname === "/" ? "" : loc.pathname}${loc.search}`} />;
}

function LocaleGate() {
  const { locale } = useParams();
  const loc = useLocation();
  if (!isLocale(locale)) return <Navigate replace to={`/${detectLocale(getPrefs().locale)}${loc.pathname}${loc.search}`} />;
  return <Layout />;
}

export default function App() {
  return (
    <HashRouter>
      <CatalogProvider>
        <Suspense fallback={<div className="wrap"><Loading /></div>}>
          <Routes>
            <Route path="/" element={<ToLocale />} />
            <Route path="/:locale" element={<LocaleGate />}>
              <Route index element={<Overview />} />
              <Route path="championships" element={<Championships />} />
              <Route path="championships/:id" element={<ChampionshipPage />} />
              <Route path="players" element={<Players />} />
              <Route path="players/:id" element={<PlayerPage />} />
              <Route path="results/:id" element={<ResultPage />} />
              <Route path="battles" element={<Battles />} />
              <Route path="monsters" element={<Monsters />} />
              <Route path="monsters/:id" element={<MonsterPage />} />
              <Route path="records" element={<Records />} />
              <Route path="status" element={<StatusPage />} />
              <Route path="about" element={<About />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </Suspense>
      </CatalogProvider>
    </HashRouter>
  );
}
