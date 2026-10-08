/**
 * Monetization settings and helpers: affiliate links, the disclosure notice,
 * "support me" / "buy the pattern" links and their display text.
 *
 * Pure module (no `astro:*` imports): pages, the Markdown plugin in
 * astro.config.mjs and tests share it. Every URL here is rendered as a plain
 * `href`, so `validateExternalLinks` (run by the tests) requires absolute HTTPS.
 */
import { extractLinkTargets, isHttpsUrl } from './article-schema';
import type { SupplyItem } from './work-schema';

export interface ExternalLink {
  /** Link text, e.g. "Buy me a coffee on Ko-fi". */
  label: string;
  /** Absolute HTTPS URL. */
  url: string;
}

/**
 * "Support me" links shown on the about page and every work page.
 * Empty = the section is hidden. Example:
 *   { label: 'Buy me a coffee on Ko-fi', url: 'https://ko-fi.com/yourname' },
 *   { label: 'Become a patron on Patreon', url: 'https://www.patreon.com/yourname' },
 */
export const SUPPORT_LINKS: readonly ExternalLink[] = [];

/**
 * Your own shops (patterns, STL files, kits), shown on the about page and on
 * work pages without a work-specific `shop` link. Empty = hidden. Example:
 *   { label: 'Sewing patterns on Etsy', url: 'https://www.etsy.com/shop/yourshop' },
 */
export const SHOP_LINKS: readonly ExternalLink[] = [];

/**
 * Set to true once you join Amazon Associates: the statement Amazon requires
 * ("As an Amazon Associate I earn from qualifying purchases.") is then shown in
 * the footer, on the disclosure page and in every affiliate notice.
 */
export const AMAZON_ASSOCIATE = false;

/**
 * Hosts whose links inside article / work bodies count as affiliate links:
 * they get rel="sponsored nofollow" and trigger the disclosure notice.
 * Subdomains match too (`www.amazon.com`, `smile.amazon.com`). Linked
 * `materials` / `tools` items use their own `affiliate` flag instead.
 */
export const AFFILIATE_HOSTS: readonly string[] = [
  'amazon.com',
  'amazon.co.uk',
  'amazon.ca',
  'amazon.com.au',
  'amzn.to',
  'awin1.com',
  'shareasale.com',
  'linksynergy.com',
  'anrdoezrs.net',
  'jdoqocy.com',
  'tkqlhce.com',
  'dpbolvw.net',
  'kqzyfj.com',
];

/** rel tokens for affiliate links (Google: paid links must be marked sponsored). */
export const AFFILIATE_REL = ['sponsored', 'nofollow'] as const;
export const AFFILIATE_REL_ATTR = AFFILIATE_REL.join(' ');

export const DISCLOSURE_PATH = '/disclosure/';

/** Display text for the monetization blocks (English market). Edit here to localise. */
export const MONETIZATION_TEXT = {
  lang: 'en',
  noticeLead: 'This page contains affiliate links.',
  notice:
    'If you buy through them, I may earn a small commission at no extra cost to you. I only link to things I have used or would use myself.',
  amazonStatement: 'As an Amazon Associate I earn from qualifying purchases.',
  noticeMore: 'Read the full disclosure',
  disclosureTitle: 'Affiliate disclosure',
  footerDisclosure: 'Affiliate disclosure',
  supportHeading: 'Support my work',
  supportLead: 'If my projects help you, you can support future builds here:',
  shopHeading: 'Get the pattern',
  shopLead: 'Want to make your own? Patterns and files are available here:',
  shopsHeading: 'My shops',
  affiliateMarker: '(affiliate link)',
} as const;

/** True when `url` is an absolute HTTPS URL on one of `hosts` (or a subdomain). */
export function isAffiliateUrl(url: string, hosts: readonly string[] = AFFILIATE_HOSTS): boolean {
  if (!isHttpsUrl(url)) return false;
  const host = new URL(url).hostname.toLowerCase().replace(/\.$/, '');
  return hosts.some((h) => {
    const want = h.toLowerCase();
    return host === want || host.endsWith(`.${want}`);
  });
}

/** True when the Markdown body links to an affiliate host. */
export function bodyHasAffiliateLinks(body: unknown, hosts: readonly string[] = AFFILIATE_HOSTS): boolean {
  if (typeof body !== 'string' || body.length === 0) return false;
  return extractLinkTargets(body).some(({ target }) => isAffiliateUrl(target, hosts));
}

/** True when a linked `materials` / `tools` item is an affiliate link. */
export function isAffiliateSupply(item: SupplyItem): item is SupplyItem & { url: string } {
  return item.url !== undefined && item.affiliate;
}

/** Whether a work page needs the affiliate notice: affiliate supplies or affiliate body links. */
export function workHasAffiliateLinks(
  data: { materials: readonly SupplyItem[]; tools: readonly SupplyItem[] },
  body: unknown,
  hosts: readonly string[] = AFFILIATE_HOSTS,
): boolean {
  return [...data.materials, ...data.tools].some(isAffiliateSupply) || bodyHasAffiliateLinks(body, hosts);
}

/** Problems with configured links (non-empty label, absolute HTTPS URL); [] when valid. */
export function validateExternalLinks(name: string, links: readonly ExternalLink[]): string[] {
  const issues: string[] = [];
  links.forEach((link, i) => {
    if (typeof link.label !== 'string' || link.label.trim() === '') issues.push(`${name}.${i}.label must be non-empty`);
    if (!isHttpsUrl(link.url)) issues.push(`${name}.${i}.url must be an absolute HTTPS URL`);
  });
  return issues;
}

/** Minimal shape of the Sätteri hast plugin used by astro.config.mjs (avoids a type-only dependency). */
interface HastElement {
  readonly properties?: Readonly<Record<string, unknown>>;
}
interface HastVisitorContext {
  setProperty(node: HastElement, key: string, value: unknown): void;
}

/**
 * Markdown (Sätteri hast) plugin: adds rel="sponsored nofollow" to every body
 * link that points at an affiliate host. Registered in astro.config.mjs.
 */
export function affiliateRelPlugin(hosts: readonly string[] = AFFILIATE_HOSTS) {
  return {
    name: 'affiliate-rel',
    element: {
      filter: ['a'],
      visit(node: HastElement, ctx: HastVisitorContext): void {
        const href = node.properties?.href;
        if (typeof href === 'string' && isAffiliateUrl(href, hosts)) {
          ctx.setProperty(node, 'rel', [...AFFILIATE_REL]);
        }
      },
    },
  };
}
