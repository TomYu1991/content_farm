// /rss.xml: RSS 2.0 feed of the sorted Production_Article_Set (static, built once).
import rss from '@astrojs/rss';
import type { APIRoute } from 'astro';
import { getProductionArticles, getSiteUrl } from '../lib/articles';
import { buildRssOptions } from '../lib/discovery';
import { SITE_DESCRIPTION, SITE_LANG, SITE_TITLE } from '../lib/site-meta';

export const GET: APIRoute = async () => {
  const articles = await getProductionArticles();
  const response = await rss(
    buildRssOptions(articles, getSiteUrl(), {
      title: SITE_TITLE,
      description: SITE_DESCRIPTION,
      language: SITE_LANG,
    }),
  );
  response.headers.set('Content-Type', 'application/rss+xml; charset=utf-8');
  return response;
};
