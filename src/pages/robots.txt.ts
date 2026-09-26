// /robots.txt: points crawlers at <Site_URL_Setting>/sitemap.xml.
import type { APIRoute } from 'astro';
import { getSiteUrl } from '../lib/articles';
import { buildRobotsTxt } from '../lib/discovery';

export const GET: APIRoute = () =>
  new Response(buildRobotsTxt(getSiteUrl()), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
