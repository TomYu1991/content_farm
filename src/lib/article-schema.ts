/**
 * Article_Schema for Content_File (Markdown + YAML front-matter) under
 * `src/content/articles/`.
 *
 * Pure, dependency-light validation used by the Production_Article_Set
 * selector. Validation never throws: callers get a list of issues with a
 * field path or a body line location.
 */
import { z } from 'astro/zod';

/** Content directory, relative to the project root (POSIX separators). */
export const CONTENT_DIR = 'src/content/articles';

/** Default maximum Markdown_Body length, in Unicode code points. */
export const DEFAULT_MAX_BODY_CHARS = 100_000;

export const FILENAME_RE = /^[a-z0-9][a-z0-9-]{0,99}\.md$/;
export const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
export const SLUG_MAX_LENGTH = 80;
export const UTC_TIMESTAMP_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$/;

/** True when `value` is `YYYY-MM-DDTHH:mm:ssZ` and denotes a real calendar instant. */
export function isUtcTimestamp(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const m = UTC_TIMESTAMP_RE.exec(value);
  if (!m) return false;
  const [year, month, day, hour, minute, second] = m.slice(1).map(Number) as [
    number,
    number,
    number,
    number,
    number,
    number,
  ];
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) return false;
  const date = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  // Round-trip rejects impossible days such as 2023-02-30.
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

/** True when `value` is an absolute URL using the `https:` scheme. */
export function isHttpsUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname.length > 0;
  } catch {
    return false;
  }
}

export function isSlug(value: unknown): value is string {
  return typeof value === 'string' && value.length <= SLUG_MAX_LENGTH && SLUG_RE.test(value);
}

const nonEmptyString = z.string().refine((s) => s.trim().length > 0, 'must be a non-empty string');

// Note: unquoted YAML timestamps are parsed as Date objects by js-yaml and are
// rejected here on purpose; front-matter dates must be quoted UTC strings.
export const utcTimestampSchema = z
  .string()
  .refine(isUtcTimestamp, 'must be a UTC timestamp formatted YYYY-MM-DDTHH:mm:ssZ');

export const slugSchema = z
  .string()
  .refine(isSlug, 'must match ^[a-z0-9]+(?:-[a-z0-9]+)*$ and be 1-80 characters');

export const sourceItemSchema = z.object({
  title: nonEmptyString,
  url: z.string().refine(isHttpsUrl, 'must be an absolute HTTPS URL'),
  accessedDate: utcTimestampSchema,
});

export const articleFrontmatterSchema = z.object({
  title: nonEmptyString,
  description: nonEmptyString,
  pubDate: utcTimestampSchema,
  updatedDate: utcTimestampSchema.optional(),
  tags: z.array(z.string()),
  slug: slugSchema,
  draft: z.boolean(),
  ai_assisted: z.boolean(),
  model: nonEmptyString,
  prompt_version: nonEmptyString,
  sources: z.array(sourceItemSchema),
});

export type ArticleFrontmatter = z.infer<typeof articleFrontmatterSchema>;
export type SourceItem = z.infer<typeof sourceItemSchema>;

export interface ValidationIssue {
  /** Field path (`draft`, `sources.0.url`), `path`, or `body` / `body:<line>`. */
  path: string;
  message: string;
}

/**
 * Validate a Content_File path relative to the project root.
 * The file must be a direct child of `contentDir`, contain no `.`/`..`
 * segments and have a filename matching FILENAME_RE.
 */
export function validateContentPath(
  filePath: string | undefined,
  contentDir: string = CONTENT_DIR,
): ValidationIssue[] {
  if (typeof filePath !== 'string' || filePath.length === 0) {
    return [{ path: 'path', message: 'missing file path' }];
  }
  const segments = filePath.replace(/\\/g, '/').split('/');
  if (segments.some((s) => s === '..' || s === '.')) {
    return [{ path: 'path', message: 'path must not contain "." or ".." segments' }];
  }
  const dirSegments = contentDir.replace(/\\/g, '/').replace(/\/+$/, '').split('/');
  const parent = segments.slice(0, -1);
  const insideDir =
    parent.length === dirSegments.length && parent.every((s, i) => s === dirSegments[i]);
  if (!insideDir) {
    return [{ path: 'path', message: `file must be directly inside ${contentDir}` }];
  }
  const filename = segments.at(-1) ?? '';
  if (!FILENAME_RE.test(filename)) {
    return [{ path: 'path', message: 'filename must match ^[a-z0-9][a-z0-9-]{0,99}\\.md$' }];
  }
  return [];
}

/**
 * Replace fenced code blocks and inline code spans with spaces (keeping line
 * breaks) so link and script checks only look at prose.
 */
function maskCode(body: string): string {
  const lines = body.split('\n');
  let fence: string | null = null;
  const masked = lines.map((line) => {
    const open = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (fence === null && open) {
      fence = open[1]!;
      return '';
    }
    if (fence !== null) {
      const close = new RegExp(`^ {0,3}${fence[0]}{${fence.length},}\\s*$`);
      if (close.test(line)) fence = null;
      return '';
    }
    return line.replace(/(`+)[\s\S]*?\1/g, (m) => ' '.repeat(m.length));
  });
  return masked.join('\n');
}

/** Link target accepted by Article_Schema: absolute HTTPS URL or site-absolute path. */
export function isAllowedLinkTarget(target: string): boolean {
  if (target.startsWith('/')) return !target.startsWith('//');
  return isHttpsUrl(target);
}

/** Extract Markdown link targets (inline, reference definitions, autolinks) with line numbers. */
export function extractLinkTargets(body: string): Array<{ line: number; target: string }> {
  const out: Array<{ line: number; target: string }> = [];
  maskCode(body.replace(/\r\n?/g, '\n'))
    .split('\n')
    .forEach((text, i) => {
      const line = i + 1;
      const refDef = /^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?/.exec(text);
      if (refDef) out.push({ line, target: refDef[1]! });
      for (const m of text.matchAll(/\]\(\s*(?:<([^>]*)>|([^\s)]+))/g)) {
        out.push({ line, target: m[1] ?? m[2] ?? '' });
      }
      for (const m of text.matchAll(/<([a-zA-Z][a-zA-Z0-9+.-]{1,31}:[^\s<>]*)>/g)) {
        out.push({ line, target: m[1]! });
      }
    });
  return out;
}

/** Validate Markdown_Body: non-empty, bounded length, allowed links, no `<script>`. */
export function validateMarkdownBody(
  body: string | undefined,
  maxChars: number = DEFAULT_MAX_BODY_CHARS,
): ValidationIssue[] {
  if (typeof body !== 'string' || body.trim().length === 0) {
    return [{ path: 'body', message: 'body must not be empty' }];
  }
  const issues: ValidationIssue[] = [];
  if ([...body].length > maxChars) {
    issues.push({ path: 'body', message: `body exceeds ${maxChars} characters` });
  }
  maskCode(body.replace(/\r\n?/g, '\n'))
    .split('\n')
    .forEach((text, i) => {
      if (/<script\b/i.test(text)) {
        issues.push({ path: `body:${i + 1}`, message: 'executable <script> element is not allowed' });
      }
    });
  for (const { line, target } of extractLinkTargets(body)) {
    if (!isAllowedLinkTarget(target)) {
      issues.push({
        path: `body:${line}`,
        message: 'link target must be an absolute HTTPS URL or a site path starting with "/"',
      });
    }
  }
  return issues;
}

export type ArticleValidationResult =
  | { ok: true; data: ArticleFrontmatter }
  | { ok: false; issues: ValidationIssue[] };

export interface ArticleInput {
  filePath?: string | undefined;
  body?: string | undefined;
  data: unknown;
}

export interface ArticleValidationOptions {
  contentDir?: string;
  maxBodyChars?: number;
}

/** Validate path, front-matter and body of one Content_File against Article_Schema. */
export function validateArticle(
  input: ArticleInput,
  options: ArticleValidationOptions = {},
): ArticleValidationResult {
  const issues: ValidationIssue[] = [
    ...validateContentPath(input.filePath, options.contentDir ?? CONTENT_DIR),
  ];
  const parsed = articleFrontmatterSchema.safeParse(input.data);
  if (!parsed.success) {
    for (const issue of parsed.error.issues) {
      issues.push({ path: issue.path.map(String).join('.') || 'front-matter', message: issue.message });
    }
  }
  issues.push(...validateMarkdownBody(input.body, options.maxBodyChars ?? DEFAULT_MAX_BODY_CHARS));
  if (issues.length > 0 || !parsed.success) return { ok: false, issues };
  return { ok: true, data: parsed.data };
}
