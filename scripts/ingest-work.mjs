#!/usr/bin/env node
/**
 * Import photos of one work into the site and create a draft work page.
 *
 *   npm run ingest -- --slug rattan-basket --category handcraft --title "藤编收纳篮" <photo-dir>
 *
 * For every JPEG/PNG/WebP/AVIF/TIFF in <photo-dir> (sorted by file name):
 *   - rotates it upright using the EXIF orientation, then drops ALL metadata
 *     (EXIF, GPS location, camera serial, XMP, ICC is converted to sRGB);
 *   - shrinks it to at most 2000px on the long edge (never enlarges);
 *   - writes a JPEG to src/assets/works/<slug>/ (cover.jpg, 01.jpg, 02.jpg, ...);
 *   - verifies the written file carries no EXIF/XMP/IPTC block.
 * The first photo (or --cover <file name>) becomes the cover.
 *
 * Then src/content/works/<slug>.md is created with `draft: true` and "待填写"
 * alt texts. The schema rejects placeholder alt texts, so the work cannot be
 * published until every photo has a real description.
 *
 * src/assets/works/<slug>/notes.md is created as a template for your making
 * notes. They are the only source the "Generate work draft" workflow sends to
 * the model (together with the facts in the front-matter); it drafts the
 * description, tags and body. Or skip the workflow and write the body yourself.
 * With --force an existing notes.md is kept.
 *
 * HEIC photos from iPhones are not supported by sharp's prebuilt binaries:
 * export them as JPEG first (or set the camera to "Most Compatible").
 * Existing output is never overwritten unless --force is given.
 */
import { existsSync } from 'node:fs';
import { mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import sharp from 'sharp';
import { CATEGORY_SLUGS } from '../src/lib/categories.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ASSET_DIR = 'src/assets/works';
const CONTENT_DIR = 'src/content/works';
const INPUT_EXT = new Set(['.jpg', '.jpeg', '.png', '.webp', '.avif', '.tif', '.tiff']);
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_EDGE = 2000;
const PLACEHOLDER = '待填写';

function fail(message) {
  console.error(`ingest-work: ${message}`);
  process.exit(1);
}

/** YAML double-quoted scalar (JSON strings are valid YAML double-quoted strings). */
const q = (value) => JSON.stringify(value);

function utcNow() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    slug: { type: 'string' },
    category: { type: 'string' },
    title: { type: 'string' },
    cover: { type: 'string' },
    quality: { type: 'string', default: '85' },
    force: { type: 'boolean', default: false },
    help: { type: 'boolean', short: 'h', default: false },
  },
});

if (values.help || positionals.length !== 1) {
  console.log(
    'Usage: npm run ingest -- --slug <slug> --category <' +
      CATEGORY_SLUGS.join('|') +
      '> [--title <title>] [--cover <file>] [--quality 85] [--force] <photo-dir>',
  );
  process.exit(values.help ? 0 : 1);
}

const slug = values.slug ?? '';
if (!SLUG_RE.test(slug) || slug.length > 80) fail('--slug must be lowercase letters, digits and single hyphens (1-80)');
if (!CATEGORY_SLUGS.includes(values.category ?? '')) fail(`--category must be one of: ${CATEGORY_SLUGS.join(', ')}`);
const quality = Number(values.quality);
if (!Number.isInteger(quality) || quality < 50 || quality > 100) fail('--quality must be an integer 50-100');

const inputDir = path.resolve(positionals[0]);
if (!existsSync(inputDir)) fail(`photo folder not found: ${inputDir}`);

const files = (await readdir(inputDir, { withFileTypes: true }))
  .filter((d) => d.isFile() && INPUT_EXT.has(path.extname(d.name).toLowerCase()))
  .map((d) => d.name)
  .sort((a, b) => a.localeCompare(b, 'en', { numeric: true }));
if (files.length === 0) fail(`no JPEG/PNG/WebP/AVIF/TIFF photos in ${inputDir}`);

let coverName = files[0];
if (values.cover !== undefined) {
  if (!files.includes(values.cover)) fail(`--cover ${values.cover} is not a photo in ${inputDir}`);
  coverName = values.cover;
}
const ordered = [coverName, ...files.filter((f) => f !== coverName)];

const outDir = path.join(ROOT, ASSET_DIR, slug);
const mdPath = path.join(ROOT, CONTENT_DIR, `${slug}.md`);
if (!values.force && existsSync(outDir)) fail(`${ASSET_DIR}/${slug}/ already exists (use --force to replace it)`);
if (!values.force && existsSync(mdPath)) fail(`${CONTENT_DIR}/${slug}.md already exists (use --force to replace it)`);

const notesPath = path.join(outDir, 'notes.md');
const keptNotes = values.force && existsSync(notesPath) ? await readFile(notesPath, 'utf8') : null;
if (values.force) await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });

const written = [];
for (const [index, name] of ordered.entries()) {
  const outName = index === 0 ? 'cover.jpg' : `${String(index).padStart(2, '0')}.jpg`;
  const outFile = path.join(outDir, outName);
  // sharp writes no metadata unless .withMetadata()/.keepExif() is called.
  const info = await sharp(path.join(inputDir, name), { failOn: 'error' })
    .rotate()
    .resize({ width: MAX_EDGE, height: MAX_EDGE, fit: 'inside', withoutEnlargement: true })
    .toColourspace('srgb')
    .jpeg({ quality, mozjpeg: true })
    .toFile(outFile);
  const meta = await sharp(outFile).metadata();
  if (meta.exif || meta.xmp || meta.iptc) {
    await rm(outDir, { recursive: true, force: true });
    if (keptNotes !== null) {
      await mkdir(outDir, { recursive: true });
      await writeFile(notesPath, keptNotes, 'utf8');
    }
    fail(`metadata still present in ${outName}; no photos were kept`);
  }
  written.push({ ref: `${slug}/${outName}`, source: name, width: info.width, height: info.height, bytes: info.size });
}

const [cover, ...gallery] = written;
const lines = [
  '---',
  `title: ${q(values.title ?? slug)}`,
  `description: ${q(PLACEHOLDER)}`,
  `pubDate: ${q(utcNow())}`,
  `slug: ${q(slug)}`,
  'draft: true',
  `category: ${q(values.category)}`,
  'tags: []',
  `cover: ${q(cover.ref)}`,
  `coverAlt: ${q(PLACEHOLDER)}`,
  gallery.length === 0 ? 'gallery: []' : 'gallery:',
  ...gallery.flatMap((g) => [`  - src: ${q(g.ref)}`, `    alt: ${q(PLACEHOLDER)}`, `    # 原图：${g.source}`]),
  '# materials / tools: plain names, or { name, url } shop links (affiliate by default;',
  '# add affiliate: false for a plain link). Example:',
  '#   - "10 安帆布 1 米"',
  '#   - { name: "Cotton webbing", url: "https://www.amazon.com/dp/..." }',
  'materials: []',
  'tools: []',
  '# shop: [{ label: "PDF pattern on Etsy", url: "https://www.etsy.com/listing/..." }]',
  '# difficulty: "beginner"   # beginner | intermediate | advanced',
  '# timeSpent: "约 6 小时"',
  '# video: { provider: "bilibili", id: "BV1xxxxxxxxx", title: "制作过程" }',
  'status: "finished"',
  '---',
  '',
];
await mkdir(path.dirname(mdPath), { recursive: true });
await writeFile(mdPath, lines.join('\n'), 'utf8');

const NOTES_TEMPLATE = `# ${values.title ?? slug} 制作笔记

<!-- 只写你确定的事实。AI 只根据这里和作品文件里的材料、工具等信息起草文字，看不到照片。 -->

## 为什么做

## 设计与尺寸

## 制作步骤

1.

## 踩过的坑

## 下次改进
`;
await writeFile(notesPath, keptNotes ?? NOTES_TEMPLATE, 'utf8');

for (const w of written) {
  console.log(`${w.source} -> ${ASSET_DIR}/${w.ref}  ${w.width}x${w.height}  ${(w.bytes / 1024).toFixed(0)} KiB`);
}
console.log(`\nCreated ${CONTENT_DIR}/${slug}.md (draft: true) and ${ASSET_DIR}/${slug}/notes.md.`);
console.log('Next:');
console.log('  1. Write your making notes in notes.md; fill materials/tools and every "待填写" alt text.');
console.log(`  2. git switch -c work/${slug}; commit these files; git push -u origin work/${slug}`);
console.log(`  3. Run the "Generate work draft (manual)" workflow with work_slug=${slug} (optional),`);
console.log('     or write the body yourself. Then review, set draft: false and open the PR.');
