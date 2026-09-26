import { describe, expect, it } from 'vitest';
import {
  articlePath,
  canonicalUrl,
  selectProductionArticles,
  type ArticleEntryInput,
} from './production-articles';

const SITE = 'https://blog.example.org/';

function entry(slug: string, overrides: Record<string, unknown> = {}, id = `${slug}.md`): ArticleEntryInput {
  return {
    id,
    filePath: `src/content/articles/${id}`,
    body: `Body of ${slug}\n`,
    data: {
      title: `Title ${slug}`,
      description: 'desc',
      pubDate: '2024-01-01T00:00:00Z',
      tags: [],
      slug,
      draft: false,
      ai_assisted: true,
      model: 'm',
      prompt_version: '1.0.0',
      sources: [],
      ...overrides,
    },
  };
}

describe('canonical URL', () => {
  it('joins the normalised HTTPS site URL and the article path', () => {
    expect(articlePath('my-post')).toBe('/articles/my-post/');
    expect(canonicalUrl(SITE, 'my-post')).toBe('https://blog.example.org/articles/my-post/');
    expect(canonicalUrl('https://example.org/base/', 'a')).toBe('https://example.org/base/articles/a/');
  });

  it('rejects non-HTTPS or blank site URLs and invalid slugs', () => {
    expect(() => canonicalUrl('http://example.org', 'a')).toThrow();
    expect(() => canonicalUrl('  ', 'a')).toThrow();
    expect(() => articlePath('Bad Slug')).toThrow();
  });
});

describe('selectProductionArticles', () => {
  it('returns an empty set for an empty collection', () => {
    expect(selectProductionArticles([], SITE)).toEqual({ articles: [], rejected: [] });
  });

  it('includes only schema-valid entries with draft === false', () => {
    const entries = [
      entry('published'),
      entry('draft-true', { draft: true }),
      entry('draft-missing', { draft: undefined }),
      entry('draft-string', { draft: 'false' }),
      entry('draft-number', { draft: 0 }),
      entry('bad-date', { pubDate: '2024-01-01' }),
      { ...entry('nested'), filePath: 'src/content/articles/sub/nested.md' },
      { ...entry('empty-body'), body: '' },
    ];
    const { articles, rejected } = selectProductionArticles(entries, SITE);
    expect(articles.map((a) => a.slug)).toEqual(['published']);
    expect(articles[0]?.data.draft).toBe(false);
    const reasons = Object.fromEntries(rejected.map((r) => [r.id, r.reason]));
    expect(reasons).toEqual({
      'draft-true.md': 'draft',
      'draft-missing.md': 'invalid',
      'draft-string.md': 'invalid',
      'draft-number.md': 'invalid',
      'bad-date.md': 'invalid',
      'nested.md': 'invalid',
      'empty-body.md': 'invalid',
    });
  });

  it('sorts by pubDate descending, then canonical URL ascending', () => {
    const entries = [
      entry('b', { pubDate: '2024-03-01T00:00:00Z' }),
      entry('old', { pubDate: '2023-12-31T23:59:59Z' }),
      entry('a', { pubDate: '2024-03-01T00:00:00Z' }),
      entry('new', { pubDate: '2024-03-01T00:00:01Z' }),
    ];
    const { articles } = selectProductionArticles(entries, SITE);
    expect(articles.map((a) => a.canonicalUrl)).toEqual([
      'https://blog.example.org/articles/new/',
      'https://blog.example.org/articles/a/',
      'https://blog.example.org/articles/b/',
      'https://blog.example.org/articles/old/',
    ]);
    expect(articles.map((a) => a.path)).toEqual(['/articles/new/', '/articles/a/', '/articles/b/', '/articles/old/']);
  });

  it('keeps the original entry for rendering', () => {
    const e = entry('keep');
    expect(selectProductionArticles([e], SITE).articles[0]?.entry).toBe(e);
  });

  it('ignores drafts sharing a published slug but throws on duplicate published slugs', () => {
    const published = entry('same', {}, 'same-1.md');
    const draft = entry('same', { draft: true }, 'same-2.md');
    expect(selectProductionArticles([published, draft], SITE).articles).toHaveLength(1);
    expect(() => selectProductionArticles([published, entry('same', {}, 'same-3.md')], SITE)).toThrow(
      /Duplicate published slug/,
    );
  });
});
