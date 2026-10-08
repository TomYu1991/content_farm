/**
 * Production_Article_Set: the single definition of which Content_File entries
 * are published, in which order, and under which Canonical_URL.
 *
 * Pure functions only (no `astro:content` import) so pages, RSS, sitemap and
 * tests share exactly the same selection, ordering and URL logic.
 */
import {
  validateArticle,
  isSlug,
  type ArticleFrontmatter,
  type ArticleValidationOptions,
  type ValidationIssue,
} from './article-schema';
import { resolveSiteUrl } from './site-url';

/** Route prefix of article pages (matches `src/pages/articles/[slug]`). */
export const ARTICLE_ROUTE_PREFIX = '/articles/';

/** Minimal structural shape of an Astro collection entry. */
export interface ArticleEntryInput {
  id: string;
  filePath?: string | undefined;
  body?: string | undefined;
  data: unknown;
}

export interface ProductionArticle<E extends ArticleEntryInput = ArticleEntryInput> {
  id: string;
  slug: string;
  /** Site-relative publish path, e.g. `/articles/my-post/`. */
  path: string;
  canonicalUrl: string;
  data: ArticleFrontmatter & { draft: false };
  /** The original entry, e.g. for `render(entry)` in article pages. */
  entry: E;
}

export type RejectionReason = 'draft' | 'invalid';

export interface RejectedArticle {
  id: string;
  filePath: string | undefined;
  reason: RejectionReason;
  issues: ValidationIssue[];
}

export interface ProductionSelection<E extends ArticleEntryInput = ArticleEntryInput> {
  /** Sorted by pubDate DESC, then canonicalUrl ASC. */
  articles: ProductionArticle<E>[];
  rejected: RejectedArticle[];
}

/** Publish path of an article: `/articles/<slug>/`. */
export function articlePath(slug: string): string {
  if (!isSlug(slug)) throw new Error(`Invalid slug: ${JSON.stringify(slug)}`);
  return `${ARTICLE_ROUTE_PREFIX}${slug}/`;
}

/** Canonical_URL = absolute HTTPS Site_URL_Setting + article publish path. */
export function canonicalUrl(siteUrl: string, slug: string): string {
  if (typeof siteUrl !== 'string' || siteUrl.trim().length === 0) {
    throw new Error('Site_URL_Setting must be a non-empty absolute HTTPS URL');
  }
  return `${resolveSiteUrl(siteUrl)}${articlePath(slug)}`;
}

/** Plain code-unit comparison: deterministic and locale-independent. */
function compareStrings(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/**
 * Order: pubDate descending, then Canonical_URL ascending.
 * pubDate strings share the fixed `YYYY-MM-DDTHH:mm:ssZ` shape, so
 * lexicographic order equals chronological order.
 */
export function compareArticles(a: DatedEntry, b: DatedEntry): number {
  return compareStrings(b.data.pubDate, a.data.pubDate) || compareStrings(a.canonicalUrl, b.canonicalUrl);
}

/** Minimal shape shared by published articles and works (ordering, sitemap, RSS). */
export interface DatedEntry {
  canonicalUrl: string;
  data: { pubDate: string; updatedDate?: string | undefined };
}

/** Return a new array sorted with `compareArticles`; the input is not mutated. */
export function sortArticles<T extends DatedEntry>(
  articles: readonly T[],
): T[] {
  return [...articles].sort(compareArticles);
}

/**
 * Select the Production_Article_Set from raw collection entries.
 *
 * An entry is included only if it passes Article_Schema (path, front-matter,
 * body) AND `draft === false`. Missing, non-boolean or `true` drafts are
 * excluded. Two published articles resolving to the same Canonical_URL are an
 * editorial conflict and throw, rather than silently dropping one.
 */
export function selectProductionArticles<E extends ArticleEntryInput>(
  entries: readonly E[],
  siteUrl: string,
  options: ArticleValidationOptions = {},
): ProductionSelection<E> {
  const articles: ProductionArticle<E>[] = [];
  const rejected: RejectedArticle[] = [];

  for (const entry of entries) {
    const result = validateArticle(entry, options);
    if (!result.ok) {
      rejected.push({ id: entry.id, filePath: entry.filePath, reason: 'invalid', issues: result.issues });
      continue;
    }
    const { data } = result;
    if (data.draft !== false) {
      rejected.push({ id: entry.id, filePath: entry.filePath, reason: 'draft', issues: [] });
      continue;
    }
    articles.push({
      id: entry.id,
      slug: data.slug,
      path: articlePath(data.slug),
      canonicalUrl: canonicalUrl(siteUrl, data.slug),
      data: { ...data, draft: false },
      entry,
    });
  }

  const byUrl = new Map<string, string>();
  for (const article of articles) {
    const other = byUrl.get(article.canonicalUrl);
    if (other !== undefined) {
      throw new Error(
        `Duplicate published slug "${article.slug}" in ${other} and ${article.entry.filePath ?? article.id}`,
      );
    }
    byUrl.set(article.canonicalUrl, article.entry.filePath ?? article.id);
  }

  return { articles: sortArticles(articles), rejected };
}
