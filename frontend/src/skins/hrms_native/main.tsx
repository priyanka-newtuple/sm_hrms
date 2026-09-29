import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import '../../index.css';
import App from './App';
import { SkinProvider } from '../../skins';
import { queryClient } from '../../core/queryClient';
import { applyCachedTheme, applyMode, getStoredPreference, resolveMode } from '../../core/theme';
import { getAccessToken } from '../../core/auth';
import { TooltipProvider } from '../../components/ui/tooltip.tsx';
import { Toaster } from '../../components/ui/toast.tsx';
import { HelmetProvider } from 'react-helmet-async';
import { ThemeProvider } from '../../core/components/theme-Provider.tsx';

// Paint the light/dark mode before anything else so the cached organization
// theme below derives its colors against the right mode, and so the first frame
// is not a flash of the wrong one.
applyMode(resolveMode(getStoredPreference()));

// Apply the last-known organization theme before first paint to avoid a flash
// of the default styling — but only for an authenticated session. Pre-auth
// pages (e.g. login) have no organization context and must show the default
// theme, so we skip the cached theme when there is no access token.
if (getAccessToken()) {
  applyCachedTheme();
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
    <ThemeProvider defaultTheme="system">
      <HelmetProvider>
        <SkinProvider>
          <Toaster />
          <TooltipProvider>
            <App />
          </TooltipProvider>
        </SkinProvider>
      </HelmetProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
