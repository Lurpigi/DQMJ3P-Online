import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/bitter/600.css";
import "@fontsource/bitter/700.css";
import "@fontsource/atkinson-hyperlegible/400.css";
import "@fontsource/atkinson-hyperlegible/700.css";
import "./styles.css";
import "./i18n";
import App from "./App";
import { applyTheme, getPrefs } from "./prefs";

applyTheme(getPrefs().theme);
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
