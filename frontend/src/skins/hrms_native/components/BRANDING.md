# HRMS branding

The brand components use the supplied Newtuple design guideline: cobalt
`#0047AB`, system typography, restrained outline icons, generous white space,
rounded cards and a geometric-wave footer. Original assets live in
`frontend/public/hrms-brand/`; they are not recolored or distorted.

`BrandFooter` is mounted once per shared layout: `PublicLayout` covers login,
public information and authentication routes; the authenticated layout covers
HRMS modules and the authorized native Settings surface. New routes under these
layouts inherit the footer. The footer stays in document flow and never covers
forms, tables or actions. Signed-in pages use `compact`: a 48px curve (one-third of the public footer’s maximum height). The footer has no copyright section, blue text strip,
promotional text or sign-in links on either public or signed-in pages. The original full-resolution
PNG remains unchanged on public pages. Signed-in pages use `BrandWave`, a
vector rendition of the blue/grey curves, drawn for a shallow 48px band. This
avoids compressing a raster image and stays sharp on high-density displays.

`BrandLogo` clips the whitespace around the original logo canvas using CSS while
preserving its aspect ratio. The geometric image is decorative and omitted from
the accessibility tree.

`BrandedLoginPage` reuses the native login component, including validation,
registration and SSO. The `.hrms-auth-form` CSS adapter hides only its original
branding block and removes the outer container decoration. When upgrading the
native login component, verify these selectors against its markup and check
both Sign In and Sign Up modes. No native platform file is changed.

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
