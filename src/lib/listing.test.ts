import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import { articleTags, formatDate, groupByTag, groupByYear, tagPath, tagSlug } from './listing';
import { canonicalUrl, compareArticles } from './production-articles';

type Item = { canonicalUrl: string; data: { pubDate: string; tags: string[] } & Record<string, unknown> };

function item(slug: string, pubDate: string, tags: string[] = []): Item {
  return { canonicalUrl: canonicalUrl('https://example.org', slug), data: { pubDate, tags } };
}

const asArticles = (xs: Item[]) => xs as unknown as Parameters<typeof groupByYear>[0];

describe('tagSlug / tagPath', () => {
  it('keeps plain Unicode slugs and normalises case and whitespace', () => {
    expect(tagSlug('astro')).toBe('astro');
    expect(tagSlug('  Astro ')).toBe('astro');
    expect(tagSlug('静态站点')).toBe('静态站点');
    expect(tagPath('Astro')).toBe('/tags/astro/');
  });

  it('keeps lossy reductions distinct via a hash suffix', () => {
    const a = tagSlug('C++');
    const b = tagSlug('C#');
    expect(a).not.toBe(b);
    expect(a).toMatch(/^c-[0-9a-f]{8}$/);
    expect(tagSlug('a/b?c')).not.toMatch(/[/?#.\s]/);
  });

  it('rejects blank tags', () => {
    expect(() => tagSlug('   ')).toThrow();
  });

  it('never yields a path separator, query, fragment, dot or whitespace', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0), (tag) => {
        const slug = tagSlug(tag);
        expect(slug.length).toBeGreaterThan(0);
        expect(slug).not.toMatch(/[/\\?#.%\s]/);
        expect(tagSlug(` ${tag.toUpperCase()} `)).toBe(tagSlug(tag.toUpperCase()));
      }),
      { numRuns: 100 },
    );
  });
});

describe('articleTags', () => {
  it('drops blank and duplicate (case-insensitive) tags', () => {
    expect(articleTags(['Astro', ' ', 'astro', 'Web  Dev']).map((t) => t.label)).toEqual(['Astro', 'Web Dev']);
  });
});

describe('groupByTag', () => {
  it('returns no groups for an empty set', () => {
    expect(groupByTag([])).toEqual([]);
  });

  it('groups articles per tag, sorted by pubDate DESC then canonical URL ASC', () => {
    const items = [
      item('b', '2024-01-01T00:00:00Z', ['X']),
      item('a', '2024-01-01T00:00:00Z', ['x', 'X']),
      item('c', '2024-06-01T00:00:00Z', ['x', 'y']),
    ];
    const groups = groupByTag(asArticles(items));
    expect(groups.map((g) => g.slug)).toEqual(['x', 'y']);
    expect(groups[0]!.articles.map((a) => a.canonicalUrl)).toEqual([
      'https://example.org/articles/c/',
      'https://example.org/articles/a/',
      'https://example.org/articles/b/',
    ]);
    expect(groups[0]!.label).toBe('X');
    expect(groups[1]!.articles).toHaveLength(1);
  });
});

describe('groupByYear', () => {
  it('returns no groups for an empty set', () => {
    expect(groupByYear([])).toEqual([]);
  });

  it('groups by UTC year, newest first, preserving the production order', () => {
    const items = [
      item('old', '2023-12-31T23:59:59Z'),
      item('new-b', '2024-03-01T00:00:00Z'),
      item('new-a', '2024-03-01T00:00:00Z'),
    ];
    const groups = groupByYear(asArticles(items));
    expect(groups.map((g) => g.year)).toEqual(['2024', '2023']);
    expect(groups[0]!.articles.map((a) => a.canonicalUrl)).toEqual([
      'https://example.org/articles/new-a/',
      'https://example.org/articles/new-b/',
    ]);
    const flat = groups.flatMap((g) => g.articles);
    expect([...flat].sort(compareArticles)).toEqual(flat);
  });
});

describe('formatDate', () => {
  it('formats a UTC timestamp as YYYY-MM-DD', () => {
    expect(formatDate('2024-02-29T23:00:00Z')).toBe('2024-02-29');
  });
});
