import { useAuth } from '@/core/auth';
import { useSkin } from '@/skins';
import { getCachedTheme, themeFromSettings, type NavLayout } from '@/core/theme';

/**
 * Resolves the effective main-nav placement: org setting (Settings → Branding),
 * falling back to the cached theme before the org has loaded. A skin that owns
 * its full nav chrome only knows how to render one way, so it forces that
 * layout regardless of the org's preference — otherwise the layout renders
 * with no nav at all. A `components.sidebar` skin forces 'sidebar'; a
 * `components.topbar` skin forces 'topbar'.
 */
export function useNavLayout(): NavLayout {
  const { organization } = useAuth();
  const { skin } = useSkin();

  if (skin.components?.sidebar) return 'sidebar';
  if (skin.components?.topbar) return 'topbar';

  return (
    (organization
      ? themeFromSettings(organization.settings, skin.defaultTheme)
      : getCachedTheme()
    ).navLayout ?? 'sidebar'
  );
}
