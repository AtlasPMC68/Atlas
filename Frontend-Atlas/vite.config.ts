import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,         // 👈 autorise l'accès via IP externe (nécessaire dans Docker)
    port: 5173,         // 👈 par défaut, mais explicite
    watch: {
      usePolling: true  // 👈 important pour que le bind mount détecte les changements !
    }
  }
})
