import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://kwu130.github.io",
  output: "static",
  build: {
    format: "directory"
  },
  integrations: [
    sitemap({
      filter: (page) => !page.endsWith("/404/")
    })
  ],
  markdown: {
    shikiConfig: {
      theme: "github-dark"
    }
  }
});
