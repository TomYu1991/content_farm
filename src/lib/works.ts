/**
 * Astro-facing accessor for the Production_Work_Set and its photos. Pages
 * must use this and never call `getCollection('works')` directly.
 */
import type { ImageMetadata } from 'astro';
import { getImage } from 'astro:assets';
import { getCollection, type CollectionEntry } from 'astro:content';
import { getSiteUrl } from './articles';
import { selectProductionWorks, type ProductionWork } from './production-works';
import { WORKS_ASSET_DIR } from './work-schema';

export type PublishedWork = ProductionWork<CollectionEntry<'works'>>;

// Every photo under src/assets/works/, imported so Astro optimises it at build time.
const modules = import.meta.glob<{ default: ImageMetadata }>(
  '/src/assets/works/**/*.{jpg,jpeg,png,webp}',
  { eager: true },
);

const PREFIX = `/${WORKS_ASSET_DIR}/`;

/** Image reference (`<slug>/<file>`) -> imported image metadata. */
const IMAGES = new Map<string, ImageMetadata>(
  Object.entries(modules).map(([key, mod]) => [key.slice(PREFIX.length), mod.default]),
);

/** Imported metadata of a work photo; references are validated before pages render. */
export function workImage(ref: string): ImageMetadata {
  const image = IMAGES.get(ref);
  if (image === undefined) throw new Error(`Work image not found: ${WORKS_ASSET_DIR}/${ref}`);
  return image;
}

/** Sorted (pubDate DESC, Canonical_URL ASC) published works; may be empty. */
export async function getProductionWorks(): Promise<PublishedWork[]> {
  const entries = await getCollection('works');
  const { works, rejected } = selectProductionWorks(entries, getSiteUrl(), {
    availableImages: new Set(IMAGES.keys()),
  });
  for (const r of rejected) {
    if (r.reason === 'invalid') {
      const details = r.issues.map((i) => `${i.path}: ${i.message}`).join('; ');
      console.warn(`[works] excluded ${r.filePath ?? r.id}: ${details}`);
    }
  }
  return works;
}

export interface SocialImage {
  url: string;
  width: number;
  height: number;
  alt: string;
}

/** 1200px-wide JPEG of the cover for Open Graph / Twitter cards (absolute URL). */
export async function socialImage(work: PublishedWork): Promise<SocialImage> {
  const image = await getImage({ src: workImage(work.data.cover), width: 1200, format: 'jpg' });
  const width = Number(image.attributes.width ?? image.options.width ?? 1200);
  const height = Number(image.attributes.height ?? image.options.height ?? 0);
  return {
    url: new URL(image.src, `${getSiteUrl()}/`).href,
    width,
    height,
    alt: work.data.coverAlt,
  };
}
