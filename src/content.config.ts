import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { CONTENT_DIR } from './lib/article-schema';
import { WORKS_CONTENT_DIR } from './lib/work-schema';

/**
 * `articles` collection: every Markdown file under src/content/articles/.
 *
 * No Astro-level schema is attached on purpose: a failing collection schema
 * aborts the whole build, whereas Requirement 7.2 requires invalid or draft
 * entries to be excluded defensively. The strict Article_Schema is applied by
 * `selectProductionArticles` (src/lib/production-articles.ts).
 *
 * Entry ids are the file path relative to the content directory (not the
 * front-matter slug), so a draft sharing a slug with a published article can
 * never overwrite it or break the build.
 */
const articles = defineCollection({
  loader: glob({
    pattern: '**/*.md',
    base: `./${CONTENT_DIR}`,
    generateId: ({ entry }) => entry,
  }),
});

/**
 * `works` collection: portfolio works under src/content/works/. Same
 * defensive approach: Work_Schema and photo existence are checked by
 * `selectProductionWorks` (src/lib/production-works.ts), and photos are
 * resolved from src/assets/works/ in src/lib/works.ts, so a broken work is
 * excluded with a warning instead of failing the build.
 */
const works = defineCollection({
  loader: glob({
    pattern: '**/*.md',
    base: `./${WORKS_CONTENT_DIR}`,
    generateId: ({ entry }) => entry,
  }),
});

export const collections = { articles, works };
