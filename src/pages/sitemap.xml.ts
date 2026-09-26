// /sitemap.xml: XML Sitemap listing only Production_Article_Set Canonical_URLs.
import type { APIRoute } from 'astro';
import { getProductionArticles } from '../lib/articles';
import { buildSitemapXml } from '../lib/discovery';

export const GET: APIRoute = async () => {
  const articles = await getProductionArticles();
  return new Response(buildSitemapXml(articles), {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
