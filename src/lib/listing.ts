/**
 * Pure grouping helpers for the aggregate pages (tag index, per-tag pages,
 * archive). Inputs are Production_Article_Set items; every returned article
 * list is re-sorted with `sortArticles` (pubDate DESC, Canonical_URL ASC), so
 * page order never depends on caller order.
 */
import { sortArticles, type ProductionArticle } from './production-articles';

/** Articles and works both qualify (same ordering fields plus tags). */
type ListedArticle = Pick<ProductionArticle, 'canonicalUrl'> & {
  data: { pubDate: string; updatedDate?: string | undefined; tags: readonly string[] };
};

/** Route prefix of tag pages (matches `src/pages/tags/[tag].astro`). */
export const TAG_ROUTE_PREFIX = '/tags/';

/** A tag slug that is already URL-friendly: Unicode letters/marks/digits joined by single hyphens. */
const PLAIN_TAG_SLUG_RE = /^[\p{L}\p{M}\p{N}]+(?:-[\p{L}\p{M}\p{N}]+)*$/u;

/**
 * Identity of a tag: NFC, trimmed, internal whitespace collapsed, lower-cased.
 * Tags with the same key are the same tag (e.g. "Astro" and " astro ").
 * Returns '' for blank tags, which are ignored.
 */
export function tagKey(tag: string): string {
  return tag.normalize('NFC').trim().replace(/\s+/g, ' ').toLowerCase();
}

/** 32-bit FNV-1a over UTF-16 code units, as 8 lowercase hex characters. */
function fnv1a(value: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

/**
 * URL segment for a tag key. Keys that are already plain slugs are used as-is
 * (`astro`, `静态站点`); anything else is reduced to letters/digits/hyphens and
 * suffixed with a hash of the key so lossy reductions (`c++` vs `c#`) stay
 * distinct. Never contains `/`, `?`, `#`, `.` or whitespace.
 */
export function tagSlug(tag: string): string {
  const key = tagKey(tag);
  if (key.length === 0) throw new Error('Tag must not be blank');
  if (PLAIN_TAG_SLUG_RE.test(key)) return key;
  const base = key
    .replace(/[^\p{L}\p{M}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
  return `${base || 'tag'}-${fnv1a(key)}`;
}

/** Site-relative path of a tag page, e.g. `/tags/astro/`. */
export function tagPath(tag: string): string {
  return `${TAG_ROUTE_PREFIX}${tagSlug(tag)}/`;
}

export interface TagGroup<A extends ListedArticle = ListedArticle> {
  /** Display label: the code-unit-smallest trimmed spelling seen for this tag. */
  label: string;
  slug: string;
  path: string;
  /** Sorted by pubDate DESC, then Canonical_URL ASC. */
  articles: A[];
}

/** Unique, non-blank tags of one article, in first-seen order, as display labels. */
export function articleTags(tags: readonly string[]): Array<{ label: string; slug: string; path: string }> {
  const seen = new Set<string>();
  const out: Array<{ label: string; slug: string; path: string }> = [];
  for (const raw of tags) {
    const key = tagKey(raw);
    if (key.length === 0 || seen.has(key)) continue;
    seen.add(key);
    const slug = tagSlug(raw);
    out.push({ label: raw.normalize('NFC').trim().replace(/\s+/g, ' '), slug, path: `${TAG_ROUTE_PREFIX}${slug}/` });
  }
  return out;
}

/**
 * Group articles by tag. Groups are ordered by slug (code-unit order); an
 * article appears at most once per group. Throws if two different tag keys
 * map to the same slug, instead of silently merging them.
 */
export function groupByTag<A extends ListedArticle>(articles: readonly A[]): TagGroup<A>[] {
  const groups = new Map<string, { key: string; label: string; articles: A[] }>();
  for (const article of sortArticles(articles)) {
    const seen = new Set<string>();
    for (const raw of article.data.tags) {
      const key = tagKey(raw);
      if (key.length === 0 || seen.has(key)) continue;
      seen.add(key);
      const slug = tagSlug(raw);
      const label = raw.normalize('NFC').trim().replace(/\s+/g, ' ');
      const group = groups.get(slug);
      if (group === undefined) {
        groups.set(slug, { key, label, articles: [article] });
        continue;
      }
      if (group.key !== key) {
        throw new Error(`Tags ${JSON.stringify(group.key)} and ${JSON.stringify(key)} share slug "${slug}"`);
      }
      if (label < group.label) group.label = label;
      group.articles.push(article);
    }
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([slug, g]) => ({ label: g.label, slug, path: `${TAG_ROUTE_PREFIX}${slug}/`, articles: g.articles }));
}

export interface YearGroup<A extends ListedArticle = ListedArticle> {
  /** UTC year of pubDate, e.g. `2024`. */
  year: string;
  /** Sorted by pubDate DESC, then Canonical_URL ASC. */
  articles: A[];
}

/** Group articles by UTC publish year, newest year first. */
export function groupByYear<A extends ListedArticle>(articles: readonly A[]): YearGroup<A>[] {
  const groups: YearGroup<A>[] = [];
  for (const article of sortArticles(articles)) {
    const year = article.data.pubDate.slice(0, 4);
    const last = groups.at(-1);
    if (last !== undefined && last.year === year) last.articles.push(article);
    else groups.push({ year, articles: [article] });
  }
  return groups;
}

/** `YYYY-MM-DD` (UTC) display date for a UTC_Timestamp. */
export function formatDate(utcTimestamp: string): string {
  return utcTimestamp.slice(0, 10);
}
