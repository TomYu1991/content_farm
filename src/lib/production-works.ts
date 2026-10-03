/**
 * Production_Work_Set: which portfolio works are published, in which order
 * and under which Canonical_URL. Pure functions only (no `astro:*` imports).
 */
import { isSlug, type ValidationIssue } from './article-schema';
import { CATEGORIES, categoryPath, type CategorySlug } from './categories';
import { sortArticles, type RejectionReason } from './production-articles';
import { resolveSiteUrl } from './site-url';
import { validateWork, type WorkFrontmatter, type WorkValidationOptions } from './work-schema';

/** Route prefix of work pages (matches `src/pages/works/[slug].astro`). */
export const WORK_ROUTE_PREFIX = '/works/';

export interface WorkEntryInput {
  id: string;
  filePath?: string | undefined;
  body?: string | undefined;
  data: unknown;
}

export interface ProductionWork<E extends WorkEntryInput = WorkEntryInput> {
  id: string;
  slug: string;
  /** Site-relative publish path, e.g. `/works/rattan-basket/`. */
  path: string;
  canonicalUrl: string;
  data: WorkFrontmatter & { draft: false };
  entry: E;
}

export interface RejectedWork {
  id: string;
  filePath: string | undefined;
  reason: RejectionReason;
  issues: ValidationIssue[];
}

export interface WorkSelection<E extends WorkEntryInput = WorkEntryInput> {
  /** Sorted by pubDate DESC, then canonicalUrl ASC. */
  works: ProductionWork<E>[];
  rejected: RejectedWork[];
}

export function workPath(slug: string): string {
  if (!isSlug(slug)) throw new Error(`Invalid slug: ${JSON.stringify(slug)}`);
  return `${WORK_ROUTE_PREFIX}${slug}/`;
}

export function workCanonicalUrl(siteUrl: string, slug: string): string {
  return `${resolveSiteUrl(siteUrl)}${workPath(slug)}`;
}

/**
 * Include a work only if it passes Work_Schema (including photo existence
 * when `options.availableImages` is given) AND `draft === false`. Duplicate
 * published slugs throw, as for articles.
 */
export function selectProductionWorks<E extends WorkEntryInput>(
  entries: readonly E[],
  siteUrl: string,
  options: WorkValidationOptions = {},
): WorkSelection<E> {
  const works: ProductionWork<E>[] = [];
  const rejected: RejectedWork[] = [];
  for (const entry of entries) {
    const result = validateWork(entry, options);
    if (!result.ok) {
      rejected.push({ id: entry.id, filePath: entry.filePath, reason: 'invalid', issues: result.issues });
      continue;
    }
    const { data } = result;
    if (data.draft !== false) {
      rejected.push({ id: entry.id, filePath: entry.filePath, reason: 'draft', issues: [] });
      continue;
    }
    works.push({
      id: entry.id,
      slug: data.slug,
      path: workPath(data.slug),
      canonicalUrl: workCanonicalUrl(siteUrl, data.slug),
      data: { ...data, draft: false },
      entry,
    });
  }
  const seen = new Map<string, string>();
  for (const work of works) {
    const other = seen.get(work.slug);
    if (other !== undefined) {
      throw new Error(`Duplicate published work slug "${work.slug}" in ${other} and ${work.entry.filePath ?? work.id}`);
    }
    seen.set(work.slug, work.entry.filePath ?? work.id);
  }
  return { works: sortArticles(works), rejected };
}

export interface CategoryGroup<W> {
  slug: CategorySlug;
  label: string;
  description: string;
  path: string;
  works: W[];
}

/** Every configured category (in CATEGORIES order) with its works, empty ones included. */
export function groupByCategory<W extends Pick<ProductionWork, 'canonicalUrl' | 'data'>>(
  works: readonly W[],
): CategoryGroup<W>[] {
  const sorted = sortArticles(works);
  return CATEGORIES.map((c) => ({
    slug: c.slug,
    label: c.label,
    description: c.description,
    path: categoryPath(c.slug),
    works: sorted.filter((w) => w.data.category === c.slug),
  }));
}

/**
 * Up to `limit` other works in the same category, most shared tags first,
 * then newest first (pubDate DESC, Canonical_URL ASC). Never includes `work`.
 */
export function relatedWorks<W extends Pick<ProductionWork, 'slug' | 'canonicalUrl' | 'data'>>(
  work: W,
  works: readonly W[],
  limit = 3,
): W[] {
  const tags = new Set(work.data.tags.map((t) => t.trim().toLowerCase()).filter(Boolean));
  const shared = (other: W) => other.data.tags.filter((t) => tags.has(t.trim().toLowerCase())).length;
  return sortArticles(works.filter((w) => w.slug !== work.slug && w.data.category === work.data.category))
    .map((w, index) => ({ w, index, score: shared(w) }))
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, Math.max(0, limit))
    .map(({ w }) => w);
}
