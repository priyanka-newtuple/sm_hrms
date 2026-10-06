# HRMS branding

The brand components use the supplied Newtuple design guideline: cobalt
`#0047AB`, system typography, restrained outline icons, generous white space,
rounded cards and a geometric-wave footer. Original assets live in
`frontend/public/hrms-brand/`; they are not recolored or distorted.

Public routes (`PublicLayout`: login, public information and authentication pages) share
`PublicHeader`: one quiet bar (logo, text navigation, dark CTA), a sliding cobalt underline on
the hovered or active category, frosted background once scrolled, tighten-on-scroll and hide-while-scrolling-down, and a menu sheet below 1000px.
They have no footer; content ends at the page body. Signed-in pages keep `BrandFooter compact`: the
48px vector `BrandWave` band only. Do not add numbered index labels (01, 02 …) to public pages.

Public-page icons are lucide-animated components in `../animated-icons/` (source:
`https://lucide-animated.com/r/<name>.json`). Render them through `AnimIcon`, which plays
the icon when its nearest link/button is hovered or focused. `PublicLayout` wraps them in
`MotionConfig reducedMotion="user"`. The login is a single, non-scrolling screen in the workspace's light theme over an animated
cobalt line field (`login/Waves`, adapted from React Bits): published information cards on the
left and the sign-in card on the right, with nothing else.

`BrandLogo` clips the whitespace around the original logo canvas using CSS while
preserving its aspect ratio. The geometric image is decorative and omitted from
the accessibility tree.

`BrandedLoginPage` renders the product-owned `login/HrmsSignInForm`, which calls the
same core `useAuth` methods, password rule (`isPasswordValid`) and pending-approval
routing as native `pages/auth/LoginPage.tsx`; only markup and styles differ. When the
native login flow changes, mirror it in `HrmsSignInForm` and check both Sign in and
Create account modes. Motion lives in `login/` (Lenis and the React Bits Silk backdrop — or Unicorn Studio via
`VITE_UNICORN_PROJECT_ID` — on the public information page, adapted React Bits on the login) and is switched off under `prefers-reduced-motion`.
No native platform file is changed.

Public category links use `/public?category=policies|learning|holidays|careers`.
Careers groups published job descriptions and open positions. Data and audience
filtering continue to come from the existing HRMS API.

## Workspace pages

Use `.hrms-workspace-page` and `.hrms-workspace-heading` for page framing,
`.hrms-resource-card` for shortcuts and `.hrms-outline-button` for secondary
navigation. `WorkPanel` provides consistent task headings, authorized counts,
loading/error/retry handling and empty states. Its children supply existing
permission-aware actions; the component never decides authorization.

Quick actions is implemented in `pages/MyWorkPage.tsx`. Its inboxes reuse the
existing cockpit and project APIs and review flows. Future HRMS screens should
follow these patterns and the branded login's typography, spacing and palette.
