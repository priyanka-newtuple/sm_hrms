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
`MotionConfig reducedMotion="user"`. The login uses the approved bright office composition: the Newtuple office photo with
“MAKE IT HAPPEN” on the red pillar fades into a compact discovery grid on the left, with
a white sign-in panel on the right. Tiffin Tuple and Templates share the same cards
as the four information categories. Wide screens use three columns; additional
options wrap into rows within a scrollable area. Smaller screens use two or one
columns and expand naturally. On phones the photo precedes the login form, then discovery.
The existing logo asset and its rendering are unchanged. Public pages have no footer.


`BrandLogo` clips the whitespace around the original logo canvas using CSS while
preserving its aspect ratio. The geometric image is decorative and omitted from
the accessibility tree.

`BrandedLoginPage` renders the product-owned `login/HrmsSignInForm`, which calls the
same core `useAuth` methods, password rule (`isPasswordValid`) and pending-approval
routing as native `pages/auth/LoginPage.tsx`; only markup and styles differ. When the
native login flow changes, mirror it in `HrmsSignInForm` and check both Sign in and
Create account modes. Public-page motion is the `login/Waves` line background (login and the
compact light information banner) plus adapted React Bits pieces, all switched off under
`prefers-reduced-motion`.
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


The portal name is **MyHub**. Reuse `MyHubWordmark` beside the unchanged Newtuple
logo in the public header and as the login heading. Its system-font lettering
pairs a light navy My with a bold cobalt Hub; scale the same wordmark rather
than creating separate treatments. The sign-in form no longer offers self-registration.


The approved MyHub wordmark now uses `public/hrms-brand/myhub-wordmark-3d.png`:
bold upright navy/cobalt lettering, shallow 3D perspective and a soft bottom
shadow. `MyHubWordmark` renders the same approved artwork at both sizes with
accessible alternative text; CSS trims only surrounding whitespace. Do not
italicize or replace it with the earlier light-weight text treatment. The
original Newtuple logo is unchanged.


Login discovery contains social cards (LinkedIn, YouTube, Instagram, X), not
repeated information navigation. Templates joins Policies/Learning/Holidays/Careers
in the header; a separate community group contains Tiffin Tuple and a clearly
unavailable Create survey / poll entry. Survey creation is intended for everyone
but remains unimplemented. Mobile navigation exposes the same destinations.
SocialDiscovery uses owner-supplied profile URLs and bundled SVG platform marks;
All four cards link to owner-provided Newtuple accounts. Cards link
out without embedding third-party feeds or loading social tracking scripts.
