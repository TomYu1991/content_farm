// /sitemap.xml: XML Sitemap listing the Canonical_URLs of published articles and works.
import type { APIRoute } from 'astro';
import { getProductionArticles } from '../lib/articles';
import { buildSitemapXml } from '../lib/discovery';
import { getProductionWorks } from '../lib/works';

export const GET: APIRoute = async () => {
  const [articles, works] = await Promise.all([getProductionArticles(), getProductionWorks()]);
  return new Response(buildSitemapXml([...articles, ...works]), {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
