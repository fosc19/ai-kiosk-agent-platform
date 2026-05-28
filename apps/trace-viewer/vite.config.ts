import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 9003,
    strictPort: true,
  },
  resolve: {
    alias: {
      '$lib': '/src/lib',
    }
  }
});
