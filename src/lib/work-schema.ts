/**
 * Work_Schema for portfolio works: Markdown + YAML front-matter under
 * `src/content/works/`, with photos under `src/assets/works/<slug>/`.
 *
 * Like Article_Schema this is applied defensively by the selector (invalid
 * or draft works are excluded with a warning instead of failing the build).
 * Pure module: no `astro:*` imports, so tests share it.
 */
import { z } from 'astro/zod';
import {
  isHttpsUrl,
  slugSchema,
  sourceItemSchema,
  utcTimestampSchema,
  validateContentPath,
  validateMarkdownBody,
  DEFAULT_MAX_BODY_CHARS,
  type ValidationIssue,
} from './article-schema';
import { CATEGORY_SLUGS } from './categories';

/** Content directory of works, relative to the project root. */
export const WORKS_CONTENT_DIR = 'src/content/works';
/** Photo directory of works, relative to the project root. */
export const WORKS_ASSET_DIR = 'src/assets/works';

/**
 * Image reference relative to WORKS_ASSET_DIR: `<slug>/<file>.<ext>`,
 * lowercase ASCII only so references behave the same on every filesystem.
 */
// Formats the review gate can check for metadata (content_pipeline/media_check.py).
export const IMAGE_REF_RE = /^([a-z0-9]+(?:-[a-z0-9]+)*)\/[a-z0-9][a-z0-9_-]{0,99}\.(?:jpe?g|png|webp)$/;

export const BILIBILI_ID_RE = /^BV[0-9A-Za-z]{10}$/;
export const YOUTUBE_ID_RE = /^[A-Za-z0-9_-]{11}$/;

/** Alt texts / captions that mean "not written yet". */
const PLACEHOLDER_TEXT = new Set(['todo', 'tbd', '待填写', '待定', '-', '...', '…']);

const nonEmptyString = z.string().refine((s) => s.trim().length > 0, 'must be a non-empty string');

/** Alt text: required, and must not be a placeholder left by the ingest script. */
const altText = nonEmptyString.refine(
  (s) => !PLACEHOLDER_TEXT.has(s.trim().toLowerCase()),
  'alt text must describe the image (placeholder not allowed)',
);

export const imageRefSchema = z
  .string()
  .regex(IMAGE_REF_RE, 'must be "<slug>/<file>.(jpg|jpeg|png|webp)" in lowercase');

export const galleryItemSchema = z.object({
  src: imageRefSchema,
  alt: altText,
  caption: nonEmptyString.optional(),
});

export const videoSchema = z.discriminatedUnion('provider', [
  z.object({
    provider: z.literal('bilibili'),
    id: z.string().regex(BILIBILI_ID_RE, 'must be a BV id such as BV1xx411c7mD'),
    title: nonEmptyString,
  }),
  z.object({
    provider: z.literal('youtube'),
    id: z.string().regex(YOUTUBE_ID_RE, 'must be an 11-character YouTube video id'),
    title: nonEmptyString,
  }),
]);

const httpsUrl = z.string().refine(isHttpsUrl, 'must be an absolute HTTPS URL');

/** A material or tool with a shop link. `affiliate` defaults to true (rendered rel="sponsored nofollow"). */
export const linkedSupplySchema = z.object({
  name: nonEmptyString,
  url: httpsUrl,
  affiliate: z.boolean().default(true),
});

/**
 * One `materials` / `tools` entry: a plain name, or `{ name, url, affiliate? }`.
 * Normalised to one shape so pages never branch on the YAML form.
 */
export const supplyItemSchema = z
  .union([nonEmptyString, linkedSupplySchema])
  .transform((item): SupplyItem =>
    typeof item === 'string' ? { name: item, affiliate: false } : item,
  );

export interface SupplyItem {
  name: string;
  url?: string;
  /** True only for linked items; plain names are never affiliate links. */
  affiliate: boolean;
}

/** The maker's own product for this work (e.g. a PDF pattern or STL file on Etsy / Gumroad). */
export const shopLinkSchema = z.object({
  label: nonEmptyString,
  url: httpsUrl,
});

export const DIFFICULTY_LABELS = { beginner: '入门', intermediate: '进阶', advanced: '高阶' } as const;
export const STATUS_LABELS = { finished: '已完成', 'in-progress': '制作中' } as const;

export const workFrontmatterSchema = z
  .object({
    title: nonEmptyString,
    description: nonEmptyString,
    pubDate: utcTimestampSchema,
    updatedDate: utcTimestampSchema.optional(),
    slug: slugSchema,
    draft: z.boolean(),
    category: z.enum(CATEGORY_SLUGS),
    tags: z.array(z.string()).default([]),
    cover: imageRefSchema,
    coverAlt: altText,
    gallery: z.array(galleryItemSchema).default([]),
    video: videoSchema.optional(),
    materials: z.array(supplyItemSchema).default([]),
    tools: z.array(supplyItemSchema).default([]),
    shop: z.array(shopLinkSchema).default([]),
    difficulty: z.enum(['beginner', 'intermediate', 'advanced']).optional(),
    timeSpent: nonEmptyString.optional(),
    status: z.enum(['finished', 'in-progress']).default('finished'),
    ai_assisted: z.boolean().default(false),
    model: nonEmptyString.optional(),
    prompt_version: nonEmptyString.optional(),
    sources: z.array(sourceItemSchema).default([]),
  })
  .superRefine((data, ctx) => {
    // Photos of a work live in its own folder, so works never share images by accident.
    const refs: Array<[string, string]> = [
      ['cover', data.cover],
      ...data.gallery.map((item, i): [string, string] => [`gallery.${i}.src`, item.src]),
    ];
    for (const [path, ref] of refs) {
      const dir = IMAGE_REF_RE.exec(ref)?.[1];
      if (dir !== undefined && dir !== data.slug) {
        ctx.addIssue({
          code: 'custom',
          path: path.split('.').map((p) => (/^\d+$/.test(p) ? Number(p) : p)),
          message: `image must be inside the work folder "${data.slug}/"`,
        });
      }
    }
    // AI-assisted text must say which model and prompt produced it.
    if (data.ai_assisted) {
      for (const key of ['model', 'prompt_version'] as const) {
        if (data[key] === undefined) {
          ctx.addIssue({ code: 'custom', path: [key], message: 'is required when ai_assisted is true' });
        }
      }
    }
  });

export type WorkFrontmatter = z.infer<typeof workFrontmatterSchema>;
export type GalleryItem = z.infer<typeof galleryItemSchema>;
export type WorkVideo = z.infer<typeof videoSchema>;
export type ShopLink = z.infer<typeof shopLinkSchema>;

export interface WorkInput {
  filePath?: string | undefined;
  body?: string | undefined;
  data: unknown;
}

export interface WorkValidationOptions {
  contentDir?: string;
  maxBodyChars?: number;
  /** Existing image references (relative to WORKS_ASSET_DIR); omitted = not checked. */
  availableImages?: ReadonlySet<string>;
}

export type WorkValidationResult =
  | { ok: true; data: WorkFrontmatter }
  | { ok: false; issues: ValidationIssue[] };

/** Every image reference of a work, cover first. */
export function workImageRefs(data: Pick<WorkFrontmatter, 'cover' | 'gallery'>): string[] {
  return [data.cover, ...data.gallery.map((item) => item.src)];
}

/**
 * Validate path, front-matter, body (optional for works: a photo-only work is
 * fine) and, when `availableImages` is given, that every photo exists.
 */
export function validateWork(input: WorkInput, options: WorkValidationOptions = {}): WorkValidationResult {
  const issues: ValidationIssue[] = [
    ...validateContentPath(input.filePath, options.contentDir ?? WORKS_CONTENT_DIR),
  ];
  const parsed = workFrontmatterSchema.safeParse(input.data);
  if (!parsed.success) {
    for (const issue of parsed.error.issues) {
      issues.push({ path: issue.path.map(String).join('.') || 'front-matter', message: issue.message });
    }
  }
  if (typeof input.body === 'string' && input.body.trim().length > 0) {
    issues.push(...validateMarkdownBody(input.body, options.maxBodyChars ?? DEFAULT_MAX_BODY_CHARS));
  }
  if (parsed.success && options.availableImages !== undefined) {
    const { cover, gallery } = parsed.data;
    const refs: Array<[string, string]> = [
      ['cover', cover],
      ...gallery.map((item, i): [string, string] => [`gallery.${i}.src`, item.src]),
    ];
    for (const [path, ref] of refs) {
      if (!options.availableImages.has(ref)) {
        issues.push({ path, message: `image not found: ${WORKS_ASSET_DIR}/${ref}` });
      }
    }
  }
  if (issues.length > 0 || !parsed.success) return { ok: false, issues };
  return { ok: true, data: parsed.data };
}
