/**
 * Astro-facing accessor for the Production_Article_Set. Pages, RSS and
 * sitemap must use this (or the pure functions it wraps) and never call
 * `getCollection('articles')` directly.
 */
import { getCollection, type CollectionEntry } from 'astro:content';
import { selectProductionArticles, type ProductionArticle } from './production-articles';
import { resolveSiteUrl } from './site-url';

export type PublishedArticle = ProductionArticle<CollectionEntry<'articles'>>;

/** Normalised Site_URL_Setting (Astro `site`), e.g. `https://example.com`. */
export function getSiteUrl(): string {
  return resolveSiteUrl(import.meta.env.SITE);
}

/** Sorted (pubDate DESC, Canonical_URL ASC) published articles; may be empty. */
export async function getProductionArticles(): Promise<PublishedArticle[]> {
  const entries = await getCollection('articles');
  const { articles, rejected } = selectProductionArticles(entries, getSiteUrl());
  for (const r of rejected) {
    if (r.reason === 'invalid') {
      const details = r.issues.map((i) => `${i.path}: ${i.message}`).join('; ');
      console.warn(`[articles] excluded ${r.filePath ?? r.id}: ${details}`);
    }
  }
  return articles;
}
