// @ts-check
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://micromagic.tv',
  output: 'static',
  build: { format: 'directory' },   // /composicion/ -> conserva las URLs de WordPress
  trailingSlash: 'always',
});
