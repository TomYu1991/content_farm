import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import { getRssString } from '@astrojs/rss';
import { XMLParser, XMLValidator } from 'fast-xml-parser';
import {
  articleSeo,
  buildRobotsTxt,
  buildRssOptions,
  buildSitemapXml,
  escapeXml,
  renderHeadMeta,
  sanitizeXmlText,
} from './discovery';
import { selectProductionArticles, type ArticleEntryInput } from './production-articles';

const SITE = 'https://blog.example.org/';
const CHANNEL = { title: 'Site & <Co>', description: 'Desc "quoted"', language: 'zh-CN' };
const TRICKY = `Tom & "Jerry" <script>alert('x')</script> \u0001 ]]>`;

function entry(slug: string, overrides: Record<string, unknown> = {}): ArticleEntryInput {
  return {
    id: `${slug}.md`,
    filePath: `src/content/articles/${slug}.md`,
    body: `Body of ${slug}\n`,
    data: {
      title: `Title ${slug}`,
      description: `Description ${slug}`,
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

function production(entries: ArticleEntryInput[]) {
  return selectProductionArticles(entries, SITE).articles;
}

const parser = new XMLParser({ ignoreAttributes: false, isArray: (name) => name === 'item' || name === 'url' || name === 'category' });

async function rssItems(entries: ArticleEntryInput[]) {
  const xml = await getRssString(buildRssOptions(production(entries), SITE, CHANNEL));
  expect(XMLValidator.validate(xml)).toBe(true);
  const doc = parser.parse(xml);
  expect(doc.rss['@_version']).toBe('2.0');
  return { xml, channel: doc.rss.channel, items: (doc.rss.channel.item ?? []) as Array<Record<string, unknown>> };
}

describe('escapeXml / sanitizeXmlText', () => {
  it('escapes markup characters and drops XML-invalid control characters', () => {
    expect(escapeXml(`a&b<c>"d"'e'`)).toBe('a&amp;b&lt;c&gt;&quot;d&quot;&apos;e&apos;');
    expect(sanitizeXmlText('a\u0000b\u0008c\td\ne')).toBe('abc\td\ne');
  });

  it('always yields well-formed XML text content (fast-check)', () => {
    fc.assert(
      fc.property(fc.string({ unit: 'binary' }), (s) => {
        expect(XMLValidator.validate(`<a b="${escapeXml(s)}">${escapeXml(s)}</a>`)).toBe(true);
      }),
      { numRuns: 100 },
    );
  });
});

describe('RSS 2.0 feed', () => {
  it('is a valid feed without items for an empty Production_Article_Set', async () => {
    const { xml, channel, items } = await rssItems([]);
    expect(items).toEqual([]);
    expect(xml).not.toContain('<item');
    expect(channel.title).toBe('Site & <Co>');
    expect(channel.link).toBe('https://blog.example.org/');
    expect(channel.language).toBe('zh-CN');
  });

  it('lists only published articles, sorted, with title, description, pubDate and canonical link/guid', async () => {
    const { items } = await rssItems([
      entry('b', { pubDate: '2024-03-01T00:00:00Z' }),
      entry('draft', { draft: true, pubDate: '2030-01-01T00:00:00Z' }),
      entry('invalid-draft', { draft: 'false' }),
      entry('a', { pubDate: '2024-03-01T00:00:00Z', tags: ['Astro', ' astro '] }),
      entry('new', { pubDate: '2024-05-06T07:08:09Z' }),
    ]);
    expect(items.map((i) => i.link)).toEqual([
      'https://blog.example.org/articles/new/',
      'https://blog.example.org/articles/a/',
      'https://blog.example.org/articles/b/',
    ]);
    const first = items[0]!;
    expect(first.title).toBe('Title new');
    expect(first.description).toBe('Description new');
    expect(first.pubDate).toBe('Mon, 06 May 2024 07:08:09 GMT');
    expect(first.guid).toEqual({ '#text': 'https://blog.example.org/articles/new/', '@_isPermaLink': 'true' });
    expect(items[1]!.category).toEqual(['Astro']);
  });

  it('escapes content-sourced metadata', async () => {
    const { xml, items } = await rssItems([entry('x', { title: TRICKY, description: TRICKY, tags: [TRICKY] })]);
    expect(xml).not.toContain('<script>');
    const expected = TRICKY.replace('\u0001', '');
    expect(items[0]!.title).toBe(expected);
    expect(items[0]!.description).toBe(expected);
    expect(items[0]!.category).toEqual([expected.replace(/\s+/g, ' ').trim()]);
  });
});

describe('XML sitemap', () => {
  it('is a valid empty urlset for an empty set', () => {
    const xml = buildSitemapXml([]);
    expect(XMLValidator.validate(xml)).toBe(true);
    expect(parser.parse(xml).urlset['@_xmlns']).toBe('http://www.sitemaps.org/schemas/sitemap/0.9');
    expect(xml).not.toContain('<url>');
  });

  it('lists only published canonical URLs', () => {
    const xml = buildSitemapXml(
      production([
        entry('pub', { updatedDate: '2024-02-02T00:00:00Z' }),
        entry('draft', { draft: true }),
        entry('no-draft', { draft: undefined }),
      ]),
    );
    expect(XMLValidator.validate(xml)).toBe(true);
    const urls = parser.parse(xml).urlset.url as Array<{ loc: string; lastmod: string }>;
    expect(urls).toEqual([{ loc: 'https://blog.example.org/articles/pub/', lastmod: '2024-02-02T00:00:00Z' }]);
    expect(xml).not.toContain('draft');
  });
});

describe('robots.txt', () => {
  it('points at the sitemap under Site_URL_Setting', () => {
    expect(buildRobotsTxt(SITE)).toContain('Sitemap: https://blog.example.org/sitemap.xml\n');
    expect(buildRobotsTxt('https://example.org/base/')).toContain('Sitemap: https://example.org/base/sitemap.xml\n');
  });
});

describe('renderHeadMeta', () => {
  it('fully escapes content-sourced attribute values', () => {
    const html = renderHeadMeta({
      description: TRICKY,
      canonicalUrl: 'https://blog.example.org/articles/x/',
      meta: [{ kind: 'property', key: 'og:title', content: TRICKY }],
    });
    expect(html).not.toMatch(/<script|<\/script/);
    expect(html).toContain('content="Tom &amp; &quot;Jerry&quot; &lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;');
    expect(html).toContain('<link rel="canonical" href="https://blog.example.org/articles/x/">');
    expect(html).toContain('<meta property="og:title" content="Tom &amp;');
  });

  it('never lets an attribute value break out of its quotes (fast-check)', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const html = renderHeadMeta({ description: s });
        expect(html.startsWith('<meta name="description" content="')).toBe(true);
        expect(html.endsWith('">')).toBe(true);
        expect(html.slice(34, -2)).not.toMatch(/["<>]/);
      }),
      { numRuns: 100 },
    );
  });
});

describe('articleSeo', () => {
  it('uses the shared canonical URL and emits Open Graph article metadata', () => {
    const [article] = production([entry('seo', { tags: ['Astro'], updatedDate: '2024-01-02T00:00:00Z' })]);
    const seo = articleSeo(article!, 'Site', 'zh-CN');
    expect(seo.canonicalUrl).toBe('https://blog.example.org/articles/seo/');
    const og = Object.fromEntries(seo.meta.map((m) => [m.key, m.content]));
    expect(og).toMatchObject({
      'og:type': 'article',
      'og:title': 'Title seo',
      'og:description': 'Description seo',
      'og:url': 'https://blog.example.org/articles/seo/',
      'og:locale': 'zh_CN',
      'article:published_time': '2024-01-01T00:00:00Z',
      'article:modified_time': '2024-01-02T00:00:00Z',
      'article:tag': 'Astro',
    });
  });
});

describe('articleSeo share image', () => {
  it('adds og:image tags and a large Twitter card only when an image is given', () => {
    const [article] = production([entry('with-image')]);
    const plain = articleSeo(article!, 'Site', 'zh-CN');
    expect(plain.meta.some((m) => m.key === 'og:image')).toBe(false);
    expect(plain.meta.find((m) => m.key === 'twitter:card')?.content).toBe('summary');

    const image = { url: 'https://blog.example.org/_astro/cover.jpg', width: 1200, height: 800, alt: '成品' };
    const seo = articleSeo(article!, 'Site', 'zh-CN', image);
    const get = (key: string) => seo.meta.find((m) => m.key === key)?.content;
    expect(get('og:image')).toBe(image.url);
    expect(get('og:image:width')).toBe('1200');
    expect(get('og:image:height')).toBe('800');
    expect(get('og:image:alt')).toBe('成品');
    expect(get('twitter:card')).toBe('summary_large_image');
  });
});
