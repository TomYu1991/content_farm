// @ts-check
import { defineConfig } from 'astro/config';
import { satteri } from '@astrojs/markdown-satteri';
import { affiliateRelPlugin } from './src/lib/monetization.ts';
import { resolveSiteUrl } from './src/lib/site-url.ts';
// Static-only build: HTML is a build artifact compiled from Markdown content files.
// No server adapter, no dynamic runtime.
// `/rss.xml` (@astrojs/rss), `/sitemap.xml` and `/robots.txt` are static endpoints
// built from the Production_Article_Set (task 2.4). @astrojs/sitemap is intentionally
// not used: it lists every route and emits sitemap-index.xml instead of /sitemap.xml.
export default defineConfig({
  site: resolveSiteUrl(process.env.SITE_URL),
  output: 'static',
  trailingSlash: 'ignore',
  markdown: {
    // Astro's default processor plus one plugin: body links to affiliate hosts
    // (AFFILIATE_HOSTS in src/lib/monetization.ts) get rel="sponsored nofollow".
    // The plugin declares only the hast fields it uses (src/lib stays free of
    // Sätteri types), hence the cast; the build output is checked by hand/tests.
    processor: satteri({ hastPlugins: [/** @type {any} */ (affiliateRelPlugin())] }),
  },
});
