import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import mdx from '@mdx-js/rollup'
import remarkFrontmatter from 'remark-frontmatter'
import remarkMdxFrontmatter from 'remark-mdx-frontmatter'
import path from 'path'

const devProxyTarget = process.env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:8001'

const customerSkinsPath = process.env.CUSTOMER_SKINS_PATH
  ? path.resolve(process.env.CUSTOMER_SKINS_PATH)
  : path.resolve(__dirname, './src/skins/customer-skins.stub.ts')

const customerSkinDir = path.dirname(customerSkinsPath)

// Groups large, stable vendor packages into their own chunks instead of
// letting them ride along inside whichever route/tab chunk happens to
// import them first — keeps the framework/UI-primitive code cacheable
// across app deploys and lets the browser fetch it in parallel with
// route-specific code.
function vendorChunk(id: string): string | undefined {
  if (!id.includes('node_modules')) return undefined
  const pkgMatch = id.match(/node_modules\/(@[^/]+\/[^/]+|[^/]+)/)
  const pkg = pkgMatch?.[1]
  if (!pkg) return undefined
  if (['react', 'react-dom', 'react-router-dom', 'scheduler', '@tanstack/react-query'].includes(pkg)) {
    return 'vendor-react'
  }
  if (pkg === 'lucide-react' || pkg.startsWith('@hugeicons')) {
    return 'vendor-icons'
  }
  if (pkg === 'radix-ui' || pkg === '@base-ui/react') {
    return 'vendor-ui'
  }
  return undefined
}

// Tailwind v4 only auto-scans the Vite root, but the active customer skin lives
// outside it (mounted via CUSTOMER_SKINS_PATH). Without this its utility classes
// are never generated and the skin's components render unstyled. Inject an
// `@source` into the main stylesheet so Tailwind also scans the skin directory.
function tailwindCustomerSkinSource() {
  return {
    name: 'tailwind-customer-skin-source',
    enforce: 'pre' as const,
    transform(code: string, id: string) {
      const filePath = id.split('?')[0].replace(/\\/g, '/')
      if (filePath.endsWith('/src/index.css')) {
        return { code: `@source "${customerSkinDir}";\n${code}`, map: null }
      }
      return null
    },
  }
}

export default defineConfig({
  plugins: [
    tailwindCustomerSkinSource(),
    // MDX must run before the React plugin so its JSX output is picked up by
    // React Fast Refresh. Frontmatter is exposed as an `export const frontmatter`
    // the Changelogs page reads via import.meta.glob.
    { enforce: 'pre', ...mdx({ remarkPlugins: [remarkFrontmatter, remarkMdxFrontmatter] }) },
    react({ include: /\.(jsx|js|mdx|md|tsx|ts)$/ }),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@customer-skins': customerSkinsPath,
    },
    dedupe: [
      'react',
      'react-dom',
      'react-router-dom',
      'lucide-react',
      'zustand',
      '@tanstack/react-query',
      '@tanstack/react-table',
    ],
  },
  optimizeDeps: {
    // This standalone ESM viewer is loaded only when an Excel preview opens.
    // Serving it directly avoids stale optimized-dependency URLs in dev.
    exclude: ['@js-preview/excel'],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: vendorChunk,
      },
    },
  },
  preview: {
    // Vite's preview server does its own Host-header check, separate from
    // the dev server's — without this, nginx-routed requests to a built/
    // previewed deployment get rejected with "Blocked request".
    allowedHosts: ['state-machine.flowtuple.com', 'resolveriq-dev.cititrends.com'],
    host: true,
  },
  server: {
    // Allow nginx-routed dev hostnames to reach the Vite dev server.
    allowedHosts: ['state-machine.flowtuple.com', 'resolveriq-dev.cititrends.com'],
    host: true,
    fs: {
      // Changelog .mdx files live at the repo root (../changelogs), outside the
      // frontend Vite root — allow the dev server to read the parent directory.
      allow: [
        path.resolve(__dirname, '..'),
        ...(customerSkinsPath ? [path.dirname(customerSkinsPath)] : []),
      ],
    },
    proxy: {
      '/api': {
        target: devProxyTarget,
        changeOrigin: true,
        rewrite: (path) => {
          const strippedPath = path.replace(/^\/api/, '');

          if (
            strippedPath.startsWith('/agent') ||
            strippedPath.startsWith('/agent-traces') ||
            strippedPath.startsWith('/analytics') ||
            strippedPath.startsWith('/auth') ||
            strippedPath.startsWith('/comments') ||
            strippedPath.startsWith('/background_jobs') ||
            strippedPath.startsWith('/bulk-import') ||
            strippedPath.startsWith('/candidate_intake') ||
            strippedPath.startsWith('/collaboration') ||
            strippedPath.startsWith('/communications') ||
            strippedPath.startsWith('/dashboards') ||
            strippedPath.startsWith('/config/file-types') ||
            strippedPath.startsWith('/config/document-types') ||
            strippedPath.startsWith('/config/forms') ||
            strippedPath.startsWith('/config/picklists') ||
            strippedPath.startsWith('/config/seed') ||
            strippedPath.startsWith('/documents') ||
            strippedPath.startsWith('/entities') ||
            strippedPath.startsWith('/entity-types') ||
            strippedPath.startsWith('/field-library') ||
            strippedPath.startsWith('/method-library') ||
            strippedPath.startsWith('/filehandler') ||
            strippedPath.startsWith('/fileprocessor') ||
            strippedPath.startsWith('/forms') ||
            strippedPath.startsWith('/identity_access') ||
            strippedPath.startsWith('/intake') ||
            strippedPath.startsWith('/intake_orchestration') ||
            strippedPath.startsWith('/integrations') ||
            strippedPath.startsWith('/invitations') ||
            strippedPath.startsWith('/integrations_calendar') ||
            strippedPath.startsWith('/llm') ||
            strippedPath.startsWith('/mcp') ||
            strippedPath.startsWith('/metadata_registry') ||
            strippedPath.startsWith('/notifications') ||
            strippedPath.startsWith('/organizations') ||
            strippedPath.startsWith('/playbooks') ||
            strippedPath.startsWith('/playbooks_runtime') ||
            strippedPath.startsWith('/projections') ||
            strippedPath.startsWith('/roles') ||
            strippedPath.startsWith('/schedules') ||
            strippedPath.startsWith('/state-machines') ||
            strippedPath.startsWith('/workflow-state-machines') ||
            strippedPath.startsWith('/tasks') ||
            strippedPath.startsWith('/tenants') ||
            strippedPath.startsWith('/tools') ||
            strippedPath.startsWith('/users') ||
            strippedPath.startsWith('/transcription') ||
            strippedPath.startsWith('/views') ||
            strippedPath.startsWith('/workflow') ||
            strippedPath.startsWith('/entity-records') ||
            strippedPath.startsWith('/entity-relations') ||
            strippedPath.startsWith('/audit-events') ||
            strippedPath.startsWith('/email-templates') ||
            strippedPath.startsWith('/action-definitions') ||
            strippedPath.startsWith('/remote-mcp') ||
            strippedPath.startsWith('/connectors') ||
            strippedPath.startsWith("/permissions")
          ) {
            return `/v1/api${strippedPath}`;
          }

          return strippedPath;
        },
      },
    },
  },
})
