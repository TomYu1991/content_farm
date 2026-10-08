/**
 * Work categories. The `slug` is stored in work front-matter (`category`) and
 * used in `/categories/<slug>/`; the label is display text only. Add a new
 * craft here first, then use its slug in works.
 */
export interface Category {
  slug: string;
  label: string;
  description: string;
}

export const CATEGORIES = [
  { slug: '3d-printing', label: '3D打印', description: 'FDM / 光固化打印的模型、收纳与功能件。' },
  { slug: 'sewing', label: '缝纫', description: '布艺、服装与包袋。' },
  { slug: 'woodworking', label: '木工', description: '小家具、木雕与木作器物。' },
  { slug: 'electronics', label: '电子DIY', description: 'Arduino、ESP32 等电子小制作。' },
  { slug: 'handcraft', label: '手工', description: '皮革、首饰、编织与模型等。' },
] as const satisfies readonly Category[];

export type CategorySlug = (typeof CATEGORIES)[number]['slug'];

export const CATEGORY_SLUGS = CATEGORIES.map((c) => c.slug) as [CategorySlug, ...CategorySlug[]];

/** Route prefix of category pages (matches `src/pages/categories/[category].astro`). */
export const CATEGORY_ROUTE_PREFIX = '/categories/';

export function categoryPath(slug: CategorySlug): string {
  return `${CATEGORY_ROUTE_PREFIX}${slug}/`;
}

export function getCategory(slug: string): Category | undefined {
  return CATEGORIES.find((c) => c.slug === slug);
}
