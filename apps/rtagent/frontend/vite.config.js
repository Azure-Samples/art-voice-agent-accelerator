import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  
  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: parseInt(env.PORT) || 5173
    },
    preview: {
      host: '0.0.0.0', 
      port: parseInt(env.PORT) || 4173
    },
    build: {
      outDir: 'dist',
      sourcemap: mode === 'development',
      assetsDir: 'assets',
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom'],
            azure: ['@azure/communication-calling', '@azure/communication-common', 'microsoft-cognitiveservices-speech-sdk']
          },
          assetFileNames: (assetInfo) => {
            const info = assetInfo.name.split('.')
            const ext = info[info.length - 1]
            if (/png|jpe?g|svg|gif|tiff|bmp|ico/i.test(ext)) {
              return `assets/images/[name]-[hash][extname]`
            }
            return `assets/[name]-[hash][extname]`
          }
        }
      }
    },
    // Ensure proper asset handling
    assetsInclude: ['**/*.png', '**/*.jpg', '**/*.jpeg', '**/*.svg', '**/*.gif'],
    // Environment variable handling
    define: {
      // Ensure environment variables are available at build time
      'process.env.NODE_ENV': JSON.stringify(mode === 'production' ? 'production' : 'development')
    }
  }
});