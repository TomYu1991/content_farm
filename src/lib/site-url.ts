/**
 * Site_URL_Setting: the absolute HTTPS root URL of the static site.
 * Used by Astro's `site` option (canonical URLs, RSS, sitemap, robots).
 */
export const DEFAULT_SITE_URL = 'https://example.com';

/**
 * Validate and normalise a site root URL.
 * Accepts only absolute `https:` URLs without credentials, query or fragment.
 * Returns the origin + path with a trailing slash removed (e.g. `https://example.com`).
 */
export function resolveSiteUrl(raw: string | undefined): string {
  const value = (raw ?? '').trim() || DEFAULT_SITE_URL;

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error('SITE_URL must be an absolute HTTPS URL');
  }

  if (url.protocol !== 'https:') {
    throw new Error('SITE_URL must use https');
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error('SITE_URL must not contain credentials, query or fragment');
  }

  return `${url.origin}${url.pathname}`.replace(/\/+$/, '');
}
