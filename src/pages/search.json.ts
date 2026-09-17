import { getCollection } from 'astro:content';
import { titleHtml } from '../lib/math-title';

export async function GET() {
  const posts = (await getCollection('posts', ({ data }) => !data.draft))
    .sort((a, b) => b.data.date.getTime() - a.data.date.getTime());

  const index = posts.map((p) => ({
    id: p.id,
    title: p.data.title,
    titleHtml: titleHtml(p.data.title),
    summary: p.data.summary ?? '',
    tags: p.data.tags,
    date: p.data.date.toISOString(),
    column: p.id.includes('/') ? p.id.split('/')[0] : '',
  }));

  return new Response(JSON.stringify(index), {
    headers: { 'Content-Type': 'application/json' },
  });
}