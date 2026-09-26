import { describe, expect, it } from 'vitest';
import {
  extractLinkTargets,
  isUtcTimestamp,
  validateArticle,
  validateContentPath,
  validateMarkdownBody,
} from './article-schema';

const validData = {
  title: 'Hello',
  description: 'A post',
  pubDate: '2024-05-01T08:00:00Z',
  tags: ['astro'],
  slug: 'hello-world',
  draft: false,
  ai_assisted: true,
  model: 'provider/model-x',
  prompt_version: '1.0.0',
  sources: [],
};

const validInput = {
  filePath: 'src/content/articles/hello-world-abc123def456.md',
  body: '# Hello\n\nSee [docs](https://example.com/docs) and [home](/).\n',
  data: validData,
};

describe('isUtcTimestamp', () => {
  it('accepts real UTC instants in the exact format', () => {
    expect(isUtcTimestamp('2024-02-29T23:59:59Z')).toBe(true);
  });

  it('rejects other formats, impossible dates and non-strings', () => {
    for (const v of [
      '2024-05-01',
      '2024-05-01T08:00:00.000Z',
      '2024-05-01T08:00:00+00:00',
      '2023-02-29T00:00:00Z',
      '2024-13-01T00:00:00Z',
      '2024-01-01T24:00:00Z',
      new Date('2024-01-01T00:00:00Z'),
      undefined,
    ]) {
      expect(isUtcTimestamp(v)).toBe(false);
    }
  });
});

describe('validateContentPath', () => {
  it('accepts a direct child with a valid filename', () => {
    expect(validateContentPath('src/content/articles/a-1.md')).toEqual([]);
    expect(validateContentPath('src\\content\\articles\\a.md')).toEqual([]);
  });

  it('rejects traversal, nesting, other dirs and bad filenames', () => {
    for (const p of [
      'src/content/articles/../articles/a.md',
      'src/content/articles/./a.md',
      'src/content/articles/sub/a.md',
      'src/content/a.md',
      'src/content/articles/A.md',
      'src/content/articles/-a.md',
      'src/content/articles/a.mdx',
      `src/content/articles/${'a'.repeat(101)}.md`,
      undefined,
    ]) {
      expect(validateContentPath(p)).not.toEqual([]);
    }
  });
});

describe('validateMarkdownBody', () => {
  it('rejects empty and over-long bodies', () => {
    expect(validateMarkdownBody('   \n')).toHaveLength(1);
    expect(validateMarkdownBody('abcd', 3)).toHaveLength(1);
    expect(validateMarkdownBody('abc', 3)).toEqual([]);
  });

  it('reports the line of disallowed link targets', () => {
    const body = 'ok [a](https://x.test)\n[b](http://x.test)\n[c]: mailto:a@b.test\n<ftp://x.test>\n[d](//x.test)\n[e](#top)';
    const issues = validateMarkdownBody(body);
    expect(issues.map((i) => i.path)).toEqual(['body:2', 'body:3', 'body:4', 'body:5', 'body:6']);
  });

  it('rejects script elements outside code but ignores code', () => {
    expect(validateMarkdownBody('text <SCRIPT>alert(1)</SCRIPT>')[0]?.path).toBe('body:1');
    expect(validateMarkdownBody('`<script>` and\n```\n<script>[x](http://a)\n```\n')).toEqual([]);
  });

  it('extracts inline, reference and autolink targets', () => {
    const targets = extractLinkTargets('![i](/img.png "t") [a](<https://a.test/x y>)\n[r]: https://r.test\n<https://auto.test>');
    expect(targets.map((t) => t.target)).toEqual([
      '/img.png',
      'https://a.test/x y',
      'https://r.test',
      'https://auto.test',
    ]);
  });
});

describe('validateArticle', () => {
  it('accepts a valid Content_File and allows empty sources', () => {
    const result = validateArticle(validInput);
    expect(result.ok).toBe(true);
  });

  it('accepts valid Source_Items and optional updatedDate', () => {
    const result = validateArticle({
      ...validInput,
      data: {
        ...validData,
        updatedDate: '2024-05-02T00:00:00Z',
        sources: [{ title: 'Ref', url: 'https://ref.test/a', accessedDate: '2024-04-30T00:00:00Z' }],
      },
    });
    expect(result.ok).toBe(true);
  });

  it('reports field paths for invalid front-matter', () => {
    const result = validateArticle({
      ...validInput,
      data: {
        ...validData,
        title: '  ',
        slug: 'Bad_Slug',
        draft: 'false',
        tags: [1],
        sources: [{ title: '', url: 'http://ref.test', accessedDate: '2024-04-30' }],
      },
    });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    const paths = result.issues.map((i) => i.path);
    expect(paths).toEqual(
      expect.arrayContaining(['title', 'slug', 'draft', 'tags.0', 'sources.0.title', 'sources.0.url', 'sources.0.accessedDate']),
    );
  });

  it('rejects missing required fields including draft', () => {
    const { draft: _draft, sources: _sources, ...rest } = validData;
    const result = validateArticle({ ...validInput, data: rest });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.issues.map((i) => i.path)).toEqual(expect.arrayContaining(['draft', 'sources']));
  });

  it('rejects slugs longer than 80 characters', () => {
    const result = validateArticle({ ...validInput, data: { ...validData, slug: 'a'.repeat(81) } });
    expect(result.ok).toBe(false);
  });
});
