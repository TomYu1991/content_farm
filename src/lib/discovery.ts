/**
 * Pure builders for the discovery assets (`/rss.xml`, `/sitemap.xml`,
 * `/robots.txt`) and article SEO / Open Graph metadata.
 *
 * Every builder consumes Production_Article_Set items (see
 * production-articles.ts), so selection, ordering and Canonical_URL are the
 * same as on the HTML pages. No `astro:*` imports: endpoints and tests share
 * this module.
 */
import type { RSSOptions } from '@astrojs/rss';
import { articleTags } from './listing';
import { sortArticles, type ProductionArticle } from './production-articles';
import { resolveSiteUrl } from './site-url';

type DiscoverableArticle = Pick<ProductionArticle, 'canonicalUrl' | 'data'>;

/**
 * Characters allowed by XML 1.0: #x9 | #xA | #xD | [#x20-#xD7FF] |
 * [#xE000-#xFFFD] | [#x10000-#x10FFFF]. Anything else (C0 controls, lone
 * surrogates, U+FFFE/U+FFFF) makes a feed unparseable, so it is dropped.
 */
const INVALID_XML_CHARS_RE =
  /[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\u{10000}-\u{10FFFF}]/gu;

/** Remove characters that are not allowed anywhere in an XML 1.0 document. */
export function sanitizeXmlText(value: string): string {
  return value.replace(INVALID_XML_CHARS_RE, '');
}

/** Escape a string for XML text or attribute content (after sanitising). */
export function escapeXml(value: string): string {
  return sanitizeXmlText(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/** Site root with a trailing slash, e.g. `https://example.com/`. */
export function siteRootUrl(siteUrl: string): string {
  return `${resolveSiteUrl(siteUrl)}/`;
}

/** Absolute URL of the XML sitemap under Site_URL_Setting. */
export function sitemapUrl(siteUrl: string): string {
  return `${resolveSiteUrl(siteUrl)}/sitemap.xml`;
}

/** Absolute URL of the RSS feed under Site_URL_Setting. */
export function rssUrl(siteUrl: string): string {
  return `${resolveSiteUrl(siteUrl)}/rss.xml`;
}

export interface FeedChannel {
  title: string;
  description: string;
  /** Optional RSS `<language>` value, e.g. `zh-CN`. */
  language?: string;
}

/**
 * Options for `@astrojs/rss`: one RSS 2.0 item per article with title,
 * description, pubDate and the Canonical_URL as `<link>`/`<guid>`, ordered
 * pubDate DESC then Canonical_URL ASC. The library XML-escapes all text;
 * characters invalid in XML are stripped here first.
 */
export function buildRssOptions(
  articles: readonly DiscoverableArticle[],
  siteUrl: string,
  channel: FeedChannel,
): RSSOptions {
  return {
    title: sanitizeXmlText(channel.title),
    description: sanitizeXmlText(channel.description),
    site: siteRootUrl(siteUrl),
    trailingSlash: true,
    ...(channel.language ? { customData: `<language>${escapeXml(channel.language)}</language>` } : {}),
    items: sortArticles(articles).map(({ canonicalUrl, data }) => ({
      title: sanitizeXmlText(data.title),
      description: sanitizeXmlText(data.description),
      pubDate: new Date(data.pubDate),
      link: canonicalUrl,
      categories: articleTags(data.tags.map(sanitizeXmlText)).map((t) => t.label),
    })),
  };
}

/**
 * XML Sitemap (sitemaps.org 0.9) listing only the given articles'
 * Canonical_URLs. An empty input yields a valid, empty `<urlset>`.
 */
export function buildSitemapXml(articles: readonly DiscoverableArticle[]): string {
  const urls = sortArticles(articles).map(({ canonicalUrl, data }) => {
    const lastmod = data.updatedDate ?? data.pubDate;
    return `  <url>\n    <loc>${escapeXml(canonicalUrl)}</loc>\n    <lastmod>${escapeXml(lastmod)}</lastmod>\n  </url>\n`;
  });
  return (
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    urls.join('') +
    '</urlset>\n'
  );
}

/** robots.txt allowing all crawlers and pointing at `<Site_URL_Setting>/sitemap.xml`. */
export function buildRobotsTxt(siteUrl: string): string {
  return `User-agent: *\nAllow: /\n\nSitemap: ${sitemapUrl(siteUrl)}\n`;
}

export interface MetaTag {
  /** `name` attribute (e.g. `description`) or `property` attribute (e.g. `og:title`). */
  kind: 'name' | 'property';
  key: string;
  content: string;
}

/** Escape a string for HTML text or a quoted attribute value (`& < > " '`). */
export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export interface HeadMetaInput {
  description: string;
  canonicalUrl?: string | undefined;
  meta?: readonly MetaTag[] | undefined;
}

/**
 * Render description, canonical link and extra meta tags as an HTML string in
 * which every attribute value is fully escaped (Astro's own attribute
 * escaping leaves `<`/`>` as-is, which is valid but not fully escaped).
 */
export function renderHeadMeta({ description, canonicalUrl, meta = [] }: HeadMetaInput): string {
  const tags = [`<meta name="description" content="${escapeHtml(description)}">`];
  if (canonicalUrl) tags.push(`<link rel="canonical" href="${escapeHtml(canonicalUrl)}">`);
  for (const tag of meta) {
    const attr = tag.kind === 'property' ? 'property' : 'name';
    tags.push(`<meta ${attr}="${escapeHtml(tag.key)}" content="${escapeHtml(tag.content)}">`);
  }
  return tags.join('');
}

export interface ArticleSeo {
  title: string;
  description: string;
  canonicalUrl: string;
  meta: MetaTag[];
}

/**
 * SEO / Open Graph metadata of an article page. Values are raw strings: the
 * layout renders them through Astro expressions, which HTML-escape them.
 */
export function articleSeo(article: DiscoverableArticle, siteName: string, locale: string): ArticleSeo {
  const { data, canonicalUrl } = article;
  const meta: MetaTag[] = [
    { kind: 'property', key: 'og:type', content: 'article' },
    { kind: 'property', key: 'og:site_name', content: siteName },
    { kind: 'property', key: 'og:locale', content: locale.replace('-', '_') },
    { kind: 'property', key: 'og:title', content: data.title },
    { kind: 'property', key: 'og:description', content: data.description },
    { kind: 'property', key: 'og:url', content: canonicalUrl },
    { kind: 'property', key: 'article:published_time', content: data.pubDate },
  ];
  if (data.updatedDate !== undefined) {
    meta.push({ kind: 'property', key: 'article:modified_time', content: data.updatedDate });
  }
  for (const tag of articleTags(data.tags)) {
    meta.push({ kind: 'property', key: 'article:tag', content: tag.label });
  }
  meta.push({ kind: 'name', key: 'twitter:card', content: 'summary' });
  return { title: data.title, description: data.description, canonicalUrl, meta };
}
