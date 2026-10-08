import { describe, expect, it } from 'vitest';
import { beaconConfig, resolveAnalyticsToken } from './analytics';
import {
  AFFILIATE_HOSTS,
  SHOP_LINKS,
  SUPPORT_LINKS,
  affiliateRelPlugin,
  bodyHasAffiliateLinks,
  isAffiliateUrl,
  validateExternalLinks,
  workHasAffiliateLinks,
} from './monetization';
import { validateWork } from './work-schema';

function work(overrides: Record<string, unknown> = {}) {
  return {
    filePath: 'src/content/works/tote-bag.md',
    body: '',
    data: {
      title: 'Tote bag',
      description: 'desc',
      pubDate: '2026-01-01T00:00:00Z',
      slug: 'tote-bag',
      draft: false,
      category: 'sewing',
      cover: 'tote-bag/cover.jpg',
      coverAlt: 'Finished tote bag, front view',
      ...overrides,
    },
  };
}

describe('materials / tools / shop in Work_Schema', () => {
  it('normalises plain names and linked items (affiliate defaults to true)', () => {
    const result = validateWork(
      work({
        materials: ['Canvas, 1 m', { name: 'Cotton webbing', url: 'https://www.amazon.com/dp/B000000000?tag=x-20' }],
        tools: [{ name: 'Rotary cutter', url: 'https://example.com/cutter', affiliate: false }],
        shop: [{ label: 'Tote bag PDF pattern on Etsy', url: 'https://www.etsy.com/listing/1' }],
      }),
    );
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.materials).toEqual([
      { name: 'Canvas, 1 m', affiliate: false },
      { name: 'Cotton webbing', url: 'https://www.amazon.com/dp/B000000000?tag=x-20', affiliate: true },
    ]);
    expect(result.data.tools).toEqual([{ name: 'Rotary cutter', url: 'https://example.com/cutter', affiliate: false }]);
    expect(result.data.shop).toHaveLength(1);
  });

  it.each([
    [{ materials: [{ name: 'x', url: 'http://insecure.example' }] }, 'materials.0'],
    [{ materials: [{ name: '', url: 'https://example.com' }] }, 'materials.0'],
    [{ tools: [{ name: 'x', url: 'https://example.com', affiliate: 'yes' }] }, 'tools.0'],
    [{ tools: [''] }, 'tools.0'],
    [{ shop: [{ label: 'x', url: 'javascript:alert(1)' }] }, 'shop.0.url'],
    [{ shop: [{ url: 'https://example.com' }] }, 'shop.0.label'],
  ])('rejects %j', (overrides, path) => {
    const result = validateWork(work(overrides));
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.issues.map((i) => i.path).some((p) => p.startsWith(path))).toBe(true);
  });
});

describe('affiliate detection', () => {
  it('matches configured hosts and their subdomains over HTTPS only', () => {
    expect(isAffiliateUrl('https://www.amazon.com/dp/B0?tag=me-20')).toBe(true);
    expect(isAffiliateUrl('https://amzn.to/abc')).toBe(true);
    expect(isAffiliateUrl('https://amazon.com.evil.example/x')).toBe(false);
    expect(isAffiliateUrl('https://notamazon.com/x')).toBe(false);
    expect(isAffiliateUrl('http://www.amazon.com/x')).toBe(false);
    expect(isAffiliateUrl('/works/a/')).toBe(false);
    expect(isAffiliateUrl('https://shop.example/x', ['shop.example'])).toBe(true);
  });

  it('finds affiliate links in Markdown bodies, ignoring code', () => {
    expect(bodyHasAffiliateLinks('I used [this glue](https://amzn.to/xyz).\n')).toBe(true);
    expect(bodyHasAffiliateLinks('See [my notes](/works/a/) and <https://example.com>.\n')).toBe(false);
    expect(bodyHasAffiliateLinks('`[x](https://amzn.to/xyz)`\n')).toBe(false);
    expect(bodyHasAffiliateLinks(undefined)).toBe(false);
  });

  it('needs the notice for affiliate supplies or affiliate body links only', () => {
    const plain = { name: 'Canvas', affiliate: false };
    const ownLink = { name: 'Pattern', url: 'https://example.com', affiliate: false };
    const affiliate = { name: 'Glue', url: 'https://example.com/glue', affiliate: true };
    expect(workHasAffiliateLinks({ materials: [plain], tools: [ownLink] }, '')).toBe(false);
    expect(workHasAffiliateLinks({ materials: [plain], tools: [affiliate] }, '')).toBe(true);
    expect(workHasAffiliateLinks({ materials: [], tools: [] }, '[a](https://amzn.to/x)')).toBe(true);
  });

  it('Markdown plugin marks only affiliate anchors as sponsored', () => {
    const plugin = affiliateRelPlugin();
    const calls: Array<[unknown, string, unknown]> = [];
    const ctx = { setProperty: (node: unknown, key: string, value: unknown) => void calls.push([node, key, value]) };
    const aff = { properties: { href: 'https://www.amazon.co.uk/dp/1' } };
    plugin.element.visit(aff, ctx);
    plugin.element.visit({ properties: { href: 'https://example.com' } }, ctx);
    plugin.element.visit({ properties: {} }, ctx);
    expect(plugin.element.filter).toEqual(['a']);
    expect(calls).toEqual([[aff, 'rel', ['sponsored', 'nofollow']]]);
  });
});

describe('site configuration', () => {
  it('configured support and shop links are absolute HTTPS with labels', () => {
    expect(validateExternalLinks('SUPPORT_LINKS', SUPPORT_LINKS)).toEqual([]);
    expect(validateExternalLinks('SHOP_LINKS', SHOP_LINKS)).toEqual([]);
    expect(validateExternalLinks('X', [{ label: ' ', url: 'http://a.example' }])).toEqual([
      'X.0.label must be non-empty',
      'X.0.url must be an absolute HTTPS URL',
    ]);
  });

  it('affiliate hosts are bare lowercase host names', () => {
    for (const host of AFFILIATE_HOSTS) expect(host).toMatch(/^[a-z0-9-]+(\.[a-z0-9-]+)+$/);
  });
});

describe('analytics token', () => {
  it('is optional, validated and JSON-encoded for the beacon', () => {
    expect(resolveAnalyticsToken(undefined)).toBeUndefined();
    expect(resolveAnalyticsToken('  ')).toBeUndefined();
    const token = '0123456789abcdef0123456789abcdef';
    expect(resolveAnalyticsToken(` ${token} `)).toBe(token);
    expect(beaconConfig(token)).toBe(`{"token":"${token}"}`);
    expect(() => resolveAnalyticsToken('abc"><script>')).toThrow(/PUBLIC_CF_ANALYTICS_TOKEN/);
    expect(() => resolveAnalyticsToken('short')).toThrow();
  });
});
