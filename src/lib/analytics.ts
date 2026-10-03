/**
 * Cookie-free page analytics: Cloudflare Web Analytics.
 *
 * The beacon sets no cookies and uses no local storage, so no cookie banner
 * is needed for it. It is only added when the build sees
 * PUBLIC_CF_ANALYTICS_TOKEN (deploy.yml passes the repository variable
 * CF_ANALYTICS_TOKEN). Local builds without it ship no third-party script.
 * The token is public by design (it appears in the page HTML), so it is a
 * variable, not a secret.
 */

export const CF_BEACON_SRC = 'https://static.cloudflareinsights.com/beacon.min.js';

/**
 * Site tokens are short alphanumeric strings (currently 32 hex characters).
 * Kept slightly loose so a format change does not break builds; the value is
 * still JSON-encoded and attribute-escaped, so it cannot inject markup.
 */
const TOKEN_RE = /^[A-Za-z0-9_-]{16,64}$/;

/**
 * Validated token, or `undefined` when analytics is not configured.
 * A set-but-malformed value fails the build instead of shipping a broken tag.
 */
export function resolveAnalyticsToken(raw: string | undefined): string | undefined {
  const value = raw?.trim() ?? '';
  if (value === '') return undefined;
  if (!TOKEN_RE.test(value)) {
    throw new Error('PUBLIC_CF_ANALYTICS_TOKEN must be a Cloudflare Web Analytics site token (16-64 letters, digits, "-" or "_")');
  }
  return value;
}

/** Value of the beacon's `data-cf-beacon` attribute (JSON; Astro escapes it as an attribute). */
export function beaconConfig(token: string): string {
  return JSON.stringify({ token });
}
