import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const catalogFile = fileURLToPath(new URL("../server/dashboard/data/monsters.json", import.meta.url));

// The monster catalog (built by tools/import-monsters) is served as a static, cacheable file
// instead of being bundled into the JavaScript.
function monsterCatalog(): Plugin {
  return {
    name: "monster-catalog",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.split("?")[0].endsWith("/monsters/catalog.json")) return next();
        res.setHeader("Content-Type", "application/json");
        res.end(readFileSync(catalogFile));
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "monsters/catalog.json", source: readFileSync(catalogFile) });
    },
  };
}

// GitHub Pages serves the site from /<repository>/: VITE_BASE sets it (default /DQMJ3P-Online/).
// Routes are hash routes (#/en/...), so deep links reload on static hosting.
export default defineConfig({
  base: process.env.VITE_BASE ?? "/DQMJ3P-Online/",
  plugins: [react(), monsterCatalog()],
  server: { proxy: { "/api": process.env.VITE_DEV_API ?? "http://127.0.0.1:8090" } },
  build: { target: "es2022", chunkSizeWarningLimit: 700 },
});
