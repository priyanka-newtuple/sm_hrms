# HRMS branding

The brand components use the supplied Newtuple design guideline: cobalt
`#0047AB`, system typography, restrained outline icons, generous white space,
rounded cards and a geometric-wave footer. Original assets live in
`frontend/public/hrms-brand/`; they are not recolored or distorted.

`BrandFooter` is mounted once per shared layout: `PublicLayout` covers login,
public information and authentication routes; the authenticated layout covers
HRMS modules and the authorized native Settings surface. New routes under these
layouts inherit the footer. The footer stays in document flow and never covers
forms, tables or actions. Signed-in pages use `compact`: a 10.67px curve. The footer has no copyright section, blue text strip,
promotional text or sign-in links on either public or signed-in pages. The original full-resolution
PNG remains unchanged; sizing is handled entirely by CSS.

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
