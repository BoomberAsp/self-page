import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: 'src/content/posts' }),
  schema: z.object({
    title: z.string(),
    date: z.date(),
    updated: z.date().optional(),
    tags: z.array(z.string()).default([]),
    summary: z.string().optional(),
    draft: z.boolean().default(false),
  }),
});

const notes = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: 'src/content/notes' }),
  schema: z.object({
    title: z.string(),
    date: z.date(),
    subject: z.string().optional(),
    type: z.enum(['markdown', 'pdf']).default('markdown'),
    pdf_file: z.string().optional(),
    summary: z.string().optional(),
    tags: z.array(z.string()).default([]),
  }),
});

export const collections = { posts, notes };