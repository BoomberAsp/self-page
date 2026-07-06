import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  output: 'static',
  integrations: [react(), mdx(), sitemap()],
  site: 'https://oneweblog.cn',
  vite: {
    plugins: [tailwindcss()],
  },
});