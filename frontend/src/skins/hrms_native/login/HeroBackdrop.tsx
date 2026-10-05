import { lazy, Suspense, useState } from 'react';

const SilkBackdrop = lazy(() => import('./SilkBackdrop'));
const UnicornScene = lazy(() => import('unicornstudio-react'));

// Optional Unicorn Studio scene. Without a project ID the React Bits Silk backdrop is used.
const UNICORN_PROJECT_ID = (import.meta.env.VITE_UNICORN_PROJECT_ID as string | undefined)?.trim();

/**
 * Animated hero background. WebGL code loads in its own chunk after the form is interactive.
 * Reduced motion and loading states keep the static cobalt gradient underneath.
 */
export function HeroBackdrop({ animate }: { animate: boolean }) {
  const [unicornFailed, setUnicornFailed] = useState(false);
  const useUnicorn = Boolean(UNICORN_PROJECT_ID) && !unicornFailed;
  return <div className="hrms-login-backdrop" aria-hidden="true">
    {animate && <Suspense fallback={null}>
      {useUnicorn
        ? <UnicornScene projectId={UNICORN_PROJECT_ID} width="100%" height="100%" scale={1} dpi={1.5} fps={60} lazyLoad className="hrms-login-canvas" onError={() => setUnicornFailed(true)} />
        : <SilkBackdrop />}
    </Suspense>}
    <div className="hrms-login-backdrop-veil" />
  </div>;
}
