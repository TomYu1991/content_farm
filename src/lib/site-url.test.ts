import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import { DEFAULT_SITE_URL, resolveSiteUrl } from './site-url';

describe('resolveSiteUrl', () => {
  it('falls back to the default HTTPS site URL when unset or blank', () => {
    expect(resolveSiteUrl(undefined)).toBe(DEFAULT_SITE_URL);
    expect(resolveSiteUrl('   ')).toBe(DEFAULT_SITE_URL);
  });

  it('strips trailing slashes and keeps a base path', () => {
    expect(resolveSiteUrl('https://blog.example.org/')).toBe('https://blog.example.org');
    expect(resolveSiteUrl('https://example.org/blog/')).toBe('https://example.org/blog');
  });

  it('rejects non-HTTPS, relative or decorated URLs', () => {
    expect(() => resolveSiteUrl('http://example.com')).toThrow(/https/);
    expect(() => resolveSiteUrl('/relative')).toThrow();
    expect(() => resolveSiteUrl('https://user:pw@example.com')).toThrow();
    expect(() => resolveSiteUrl('https://example.com/?q=1')).toThrow();
  });

  it('always returns an absolute https URL without a trailing slash (fast-check smoke)', () => {
    fc.assert(
      fc.property(fc.domain(), (domain) => {
        const out = resolveSiteUrl(`https://${domain}/`);
        expect(new URL(out).protocol).toBe('https:');
        expect(out.endsWith('/')).toBe(false);
      }),
      { numRuns: 100 },
    );
  });
});
