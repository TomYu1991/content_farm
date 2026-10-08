import { describe, expect, it } from 'vitest';
import {
  groupByCategory,
  relatedWorks,
  selectProductionWorks,
  workPath,
  type WorkEntryInput,
} from './production-works';
import { validateWork } from './work-schema';

const SITE = 'https://maker.example.org/';

function work(slug: string, overrides: Record<string, unknown> = {}, body = ''): WorkEntryInput {
  return {
    id: `${slug}.md`,
    filePath: `src/content/works/${slug}.md`,
    body,
    data: {
      title: `Work ${slug}`,
      description: 'desc',
      pubDate: '2026-01-01T00:00:00Z',
      slug,
      draft: false,
      category: 'sewing',
      cover: `${slug}/cover.jpg`,
      coverAlt: '成品正面照',
      ...overrides,
    },
  };
}

describe('validateWork', () => {
  it('accepts a minimal hand-written work and applies defaults', () => {
    const result = validateWork(work('tote-bag'));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data).toMatchObject({
      tags: [],
      gallery: [],
      materials: [],
      tools: [],
      status: 'finished',
      ai_assisted: false,
      sources: [],
    });
  });

  it('rejects placeholder alt text, unknown categories and bad image refs', () => {
    const result = validateWork(
      work('tote-bag', {
        coverAlt: 'TODO',
        category: 'painting',
        gallery: [{ src: 'tote-bag/Step 1.JPG', alt: 'x' }],
      }),
    );
    expect(result.ok).toBe(false);
    if (result.ok) return;
    const paths = result.issues.map((i) => i.path);
    expect(paths).toEqual(expect.arrayContaining(['coverAlt', 'category', 'gallery.0.src']));
  });

  it('requires photos to live in the work folder', () => {
    const result = validateWork(work('tote-bag', { gallery: [{ src: 'other-work/a.jpg', alt: '步骤一' }] }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.issues.map((i) => i.path)).toContain('gallery.0.src');
  });

  it('requires model and prompt_version only for AI-assisted works', () => {
    const result = validateWork(work('tote-bag', { ai_assisted: true }));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.issues.map((i) => i.path).sort()).toEqual(['model', 'prompt_version']);
    expect(validateWork(work('tote-bag', { ai_assisted: true, model: 'm', prompt_version: '1' })).ok).toBe(true);
  });

  it('validates video ids per provider', () => {
    const ok = validateWork(work('a', { video: { provider: 'bilibili', id: 'BV1xx411c7mD', title: '过程' } }));
    expect(ok.ok).toBe(true);
    const bad = validateWork(work('a', { video: { provider: 'youtube', id: 'BV1xx411c7mD', title: '过程' } }));
    expect(bad.ok).toBe(false);
    const other = validateWork(work('a', { video: { provider: 'vimeo', id: '1', title: 't' } }));
    expect(other.ok).toBe(false);
  });

  it('checks the body only when present, with the article link rules', () => {
    expect(validateWork(work('a', {}, '')).ok).toBe(true);
    expect(validateWork(work('a', {}, '[x](http://insecure.example)\n')).ok).toBe(false);
    expect(validateWork(work('a', {}, '![步骤](/images/a.jpg)\n')).ok).toBe(true);
  });

  it('reports missing photos when the available set is given', () => {
    const images = new Set(['a/cover.jpg']);
    expect(validateWork(work('a'), { availableImages: images }).ok).toBe(true);
    const result = validateWork(work('a', { gallery: [{ src: 'a/b.jpg', alt: '细节' }] }), { availableImages: images });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.issues).toEqual([{ path: 'gallery.0.src', message: 'image not found: src/assets/works/a/b.jpg' }]);
  });

  it('rejects files outside src/content/works/', () => {
    expect(validateWork({ ...work('a'), filePath: 'src/content/articles/a.md' }).ok).toBe(false);
  });
});

describe('selectProductionWorks', () => {
  it('publishes valid non-draft works sorted by pubDate desc', () => {
    const { works, rejected } = selectProductionWorks(
      [
        work('old', { pubDate: '2025-01-01T00:00:00Z' }),
        work('new', { pubDate: '2026-05-01T00:00:00Z' }),
        work('draft', { draft: true }),
        work('broken', { coverAlt: '' }),
      ],
      SITE,
    );
    expect(works.map((w) => w.slug)).toEqual(['new', 'old']);
    expect(works[0]!.canonicalUrl).toBe('https://maker.example.org/works/new/');
    expect(rejected.map((r) => [r.id, r.reason])).toEqual([
      ['draft.md', 'draft'],
      ['broken.md', 'invalid'],
    ]);
  });

  it('throws on duplicate published slugs', () => {
    const a = work('same');
    const b = { ...work('same'), id: 'copy.md', filePath: 'src/content/works/copy.md' };
    expect(() => selectProductionWorks([a, b], SITE)).toThrow(/Duplicate/);
  });

  it('groups works by configured category, keeping empty categories', () => {
    const { works } = selectProductionWorks([work('a'), work('b', { category: 'woodworking' })], SITE);
    const groups = groupByCategory(works);
    expect(groups.find((g) => g.slug === 'sewing')!.works.map((w) => w.slug)).toEqual(['a']);
    expect(groups.find((g) => g.slug === 'woodworking')!.path).toBe('/categories/woodworking/');
    expect(groups.find((g) => g.slug === 'electronics')!.works).toEqual([]);
  });

  it('builds work paths from valid slugs only', () => {
    expect(workPath('tote-bag')).toBe('/works/tote-bag/');
    expect(() => workPath('../x')).toThrow();
  });
});

describe('relatedWorks', () => {
  const { works } = selectProductionWorks(
    [
      work('base', { tags: ['帆布', '包袋'] }),
      work('new-no-tags', { pubDate: '2026-06-01T00:00:00Z' }),
      work('old-shared', { pubDate: '2025-01-01T00:00:00Z', tags: [' 帆布 '] }),
      work('two-shared', { pubDate: '2025-02-01T00:00:00Z', tags: ['包袋', '帆布'] }),
      work('other-category', { category: 'woodworking', tags: ['帆布', '包袋'] }),
    ],
    SITE,
  );
  const base = works.find((w) => w.slug === 'base')!;

  it('ranks same-category works by shared tags, then newest, and excludes itself', () => {
    expect(relatedWorks(base, works).map((w) => w.slug)).toEqual(['two-shared', 'old-shared', 'new-no-tags']);
  });

  it('respects the limit and never pads with other categories', () => {
    expect(relatedWorks(base, works, 1).map((w) => w.slug)).toEqual(['two-shared']);
    const wood = works.find((w) => w.slug === 'other-category')!;
    expect(relatedWorks(wood, works)).toEqual([]);
    expect(relatedWorks(base, works, 0)).toEqual([]);
  });
});
