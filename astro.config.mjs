import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import react from '@astrojs/react';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { rehypeRewriteImg } from './src/plugins/rehype-rewrite-img';

export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  integrations: [
    react(),
    mdx({ rehypePlugins: [rehypeRewriteImg] }),
    sitemap(),
  ],
  site: 'https://oneweblog.cn',
  vite: {
    plugins: [tailwindcss()],
  },
});