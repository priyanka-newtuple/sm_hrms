
## **1\. Introduction**

**Purpose:** This document defines Newtuple’s unified design language — a living, system-driven guide ensuring visual and experiential consistency across **all touchpoints**: website, dashboards, presentations, booths, videos, and marketing material.

**Scope:** Applicable to all brand expressions \- digital (web, UI, dashboards, slides, social) and physical (print, booth design, environmental graphics).

**Core Principles:**

·   	**Minimalism** – Remove the unnecessary; design for clarity and focus.

·   	**Clarity** – Prioritize readable hierarchy and clean information flow.

·   	**Sophistication** – Express technical mastery through visual restraint.

·   	**Reliability** – Build trust through consistent patterns and tone.

·   	**Human \+ Technical Balance** – Combine empathy with precision.

·   	**Cobalt Signature** – The cobalt blue logo color (\#0047AB) anchors every visual system.

## **2\. Brand Identity Overview**

**Brand Essence:** Building the agentic enterprise future where humans pilot and AI agents execute.

**Brand Personality:** Professional, intelligent, reliable, technically sophisticated, and warmly human.

**Voice & Tone:**

·   	**Visual Voice:** Minimal, open, and precise: less decoration, more purpose.

·   	**Copy Tone:** Confident yet conversational; authoritative, never arrogant.

·   	**Interaction Style:** Predictable, smooth, and intentional.

**Mission Tagline:** *Build Your Agentic Enterprise.*

**Design Philosophy:** Each design decision reflects *calm precision*. Motion and contrast guide attention rather than demand it.

## **3\. Logo Guidelines**

**Primary Logo:** The official **Newtuple logo** in **Cobalt Blue (\#0047AB)** as shown above. This is the master mark: it must not be altered, recolored, or distorted.

**Usage Rules:**

·   	Maintain clear space equal to the height of the “N” on all sides.

·   	Logo should appear on white or neutral backgrounds only.

·   	Never apply effects, gradients, or shadows.

**Variants:**

·   	**Primary:** Blue on white (default for all digital and print media).

·   	**Inverse:** White on blue (use for dark or Cobalt backgrounds).

·   	**Monogram:** The “N” can be used alone for icons or favicons.

**Minimum Sizes:**

·   	Digital: 32px height.

·   	Print: 10mm height.

## **4\. Color Palette**

**Primary Palette:**

·   	**Cobalt Blue:** \#0047AB — Signature brand color, symbolizing intelligence and trust.
    - `cobalt-light`: \#0055CC — Hover states
    - `cobalt-dark`: \#003380 — Active/pressed states

·   	**Cyan:** \#00B8D9 — Secondary accent, used in gradients with cobalt.
    - `cyan-light`: \#00D4FF — Highlights

·   	**Violet:** \#8B5CF6 — AI accent color, used for AI-powered features.
    - `violet-light`: \#A78BFA
    - `violet-dark`: \#7C3AED

·   	**White:** \#FFFFFF — Primary background and whitespace.

·   	**Black:** \#000000 — Strong accents and typography.

·   	**Gray 900 / 600 / 50:** Supporting neutrals for depth and accessibility.

**AI Gradient:**

·   	`from-cobalt via-cyan to-violet` — Used for AI-powered elements, active navigation states, and emphasis.

·   	Background: `linear-gradient(135deg, #0047AB 0%, #00B8D9 50%, #8B5CF6 100%)`

**Functional Colors:**

·   	**Emerald:** \#10B981 — Success states, online indicators.

·   	**Amber:** \#F59E0B — Warning states, pending actions.

·   	**Rose:** \#F43F5E — Error states, destructive actions, alerts.

**Usage Notes:**

·   	Cobalt Blue is the primary interactive color for buttons, links, and active states.

·   	The AI gradient (cobalt → cyan → violet) is used for AI-powered features and premium interactions.

·   	White/light backgrounds dominate; glassmorphism effects add depth where needed.

·   	Gradients are used purposefully for active states, AI indicators, and visual hierarchy.

## **5\. Typography**

**Primary Font:** Inter — A modern, highly legible typeface optimized for screens.

**Font Stack:** `'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`

**Font Weights:**

·   	ExtraLight – Hero and key statements.

·   	Light – Body and descriptions.

·   	Medium – Buttons, labels.

·   	SemiBold – Section headers.

·   	Bold – Numeric data or emphasis.

**Hierarchy:**

·   	**H1:** Large, extra-light, tracking-tight.

·   	**H2:** Light, wide-spaced section headers.

·   	**H3:** Compact, elegant, light.

·   	**Body:** Relaxed line height, gray-600.

·   	**Labels:** Uppercase, small, tracking-wider.

**Cross-Medium Guidance:**

·   	**Web/UI:** Responsive sizing with rem units.

·   	**Slides:** Larger type ratios for distant readability.

·   	**Print:** Adjust contrast, slightly tighter spacing.

## **6\. Imagery & Illustration**

**Style:** Abstract and geometric; avoid photography unless storytelling demands it.

**Icons:**

·   	Lucide React icons (outline only).

·   	Stroke: 1px, color inherits or Cobalt Blue.

**Illustrations:**

·   	Simple, flat geometry. Symbolize flow, connection, and intelligence.

**Do’s:**

·   	Use monochrome imagery with selective Cobalt highlights.

·   	Use icons to clarify, not decorate.

**Don’ts:**

·   	Mix icon styles or colors.

·   	Use literal photography for technical products.

## **7\. Layout & Composition**

**Grid:** 12-column grid for web; modular for slides and print.

**Spacing:** Generous vertical rhythm (`py-20`–`py-32`), consistent internal spacing (`p-8`–`p-12`).

**Whitespace Philosophy:** White is as important as content; it allows sophistication and clarity to breathe.

**Alignment:**

·   	Text: Left-aligned for readability.

·   	Hero/Key visuals: Centered or balanced asymmetry.

·   	Booths: Centered for impact, grid-aligned signage.

**Corners & Radius:**
- `rounded-full` — Buttons, badges, pills
- `rounded-2xl` — Cards, modals, large containers
- `rounded-xl` — Inputs, nav items, avatars, dropdowns
- `rounded-lg` — Small interactive elements

## **8\. Motion & Interaction**

**Principle:** Motion \= clarity. Always purposeful, never decorative.

**Durations:**
- 200ms — Micro-interactions (button press, icon scale)
- 300ms — Standard transitions (hover, focus, color changes)
- 500ms — Page transitions, slide-overs
- 2-3s — Continuous animations (shimmer, gradient flow)

**Easing:** `ease-out` for entrances, `ease-in-out` for continuous animations.

**Named Animations (Tailwind):**

| Animation | Duration | Use Case |
| --------- | -------- | -------- |
| `gradient-x` | 3s | AI button gradient movement |
| `shimmer` | 2s | Loading skeletons, AI button shine |
| `pulse-soft` | 2s | Subtle pulsing for indicators |
| `float` | 3s | Floating decorative elements |
| `glow` | 2s | Glowing button effects |
| `border-flow` | 3-4s | Animated gradient borders |
| `fade-in` | 0.3s | Element entrance |
| `slide-up` | 0.3s | Content reveal |
| `scale-in` | 0.2s | Modal/dropdown entrance |

**Applications:**

·   	Hover → subtle scale (`group-hover:scale-110`) or lift (`-translate-y-1`).

·   	Active nav items → gradient background with glow shadow.

·   	AI elements → continuous gradient animation with shimmer overlay.

·   	Cards → hover lift with shadow transition.

·   	Buttons → scale down on press (`active:scale-[0.97]`).

**Cross-Medium Consistency:** Motion tempo should remain consistent between website, videos, and on-screen loops at exhibitions.

## **9\. Component Patterns**

### **Buttons**

| Variant | Style | Use Case |
| ------- | ----- | -------- |
| **Primary** | Cobalt background, white text, rounded-full | Main actions |
| **Secondary** | White background, gray text, gray border | Secondary actions |
| **Ghost** | Transparent, gray text, hover bg-gray-100 | Tertiary actions |
| **Danger** | Rose background, white text | Destructive actions |
| **AI** | Animated gradient (cobalt→cyan→violet), shimmer effect | AI-powered actions |

- All buttons scale down slightly on click (`scale-[0.97]`)
- Optional `glow` prop adds blur glow effect on hover

### **Cards**

| Elevation | Shadow | Use Case |
| --------- | ------ | -------- |
| **none** | No shadow | Flat content |
| **sm** | `shadow-sm` | Subtle elevation |
| **md** | `shadow-md`, hover lift | Default cards |
| **lg** | `shadow-lg` | Prominent cards |

- Cards use `rounded-2xl` corners
- Hover state: `-translate-y-1` lift effect
- High-match cards: animated gradient border (`.gradient-border` class)

### **Badges**

| Variant | Style | Use Case |
| ------- | ----- | -------- |
| **default** | Gray background | Neutral labels |
| **success** | Emerald/10 bg, emerald text | Success states |
| **warning** | Amber/10 bg, amber text | Warning states |
| **error** | Rose/10 bg, rose text | Error states |
| **cobalt** | Cobalt/10 bg, cobalt text | Primary highlight |
| **ai** | Gradient bg, violet text, sparkle icon | AI-powered indicators |
| **gradient** | Solid gradient bg, white text | Premium labels |

### **Form Inputs**

- Rounded-xl corners
- Focus: cobalt ring with subtle glow (`box-shadow: 0 0 0 3px rgba(0,71,171,0.1)`)
- Error state: rose border and text
- Helper text below inputs for guidance

### **Navigation**

- **Header:** Fixed top, glassmorphism (`bg-white/80 backdrop-blur-xl`)
- **Sidebar:** Light glass effect, gradient active states with glow shadow
- **Mobile nav:** Bottom-fixed, glass backdrop, gradient icons for active state

### **Modals & Slide-overs**

- Glassmorphism backdrop (`bg-gray-900/20 backdrop-blur-sm`)
- Scale-in animation for modals
- Slide-in animation for slide-overs
- Rounded-2xl corners

### **Loading States**

- Skeleton components with shimmer animation
- `SkeletonCard`, `SkeletonTableRow`, `SkeletonKanbanColumn` variants

**Slide & Booth Parallels:**

·   	CTA → Key message card.

·   	Card → Content panel.

·   	Navigation → Slide header strip.

·   	Footer → Closing statement / contact band.

---

## **10\. Accessibility & Responsiveness**

·   	Minimum contrast ratio AA.

·   	Font size scales across screen types.

·   	Interactive elements include hover/focus states.

·   	Large text and high contrast in physical signage.

## **11\. Verbal & Copy Guidelines**

**Voice:** Calm authority. Speak like a practitioner, not a vendor.

**Tone per Medium:**

·   	**Web:** Direct, informative.

·   	**Slides:** Narrative, crisp, confident.

·   	**UI:** Clear and minimal.

·   	**Booth/Print:** Impactful, declarative.

**Language Mechanics:**

·   	Use active voice.

·   	Avoid buzzwords; use precise technical vocabulary.

·   	Always align copy with design tone: clarity \> flair.

## **12\. Signature Visual Elements**

### **Gradients**

·   	**AI Gradient:** `from-cobalt via-cyan to-violet` — Primary AI indicator.

·   	**Gradient Text:** `.text-gradient` class for emphasized headings.

·   	**Gradient Borders:** `.gradient-border` class with animated flow effect.

### **Glassmorphism**

·   	**Glass Light:** `bg-white/80 backdrop-blur-xl` — Headers, sidebars.

·   	**Glass Dark:** `bg-gray-900/20 backdrop-blur-sm` — Modal backdrops.

·   	Used to create depth and layering without heavy shadows.

### **Glow Effects**

·   	**Button Glow:** `.btn-glow` class adds blur glow on hover.

·   	**Shadow Glow:** `shadow-cobalt/30`, `shadow-violet/30` for colored shadows.

·   	**Box Shadow Glow:** `glow-sm`, `glow-md`, `glow-lg` utilities.

### **Visual Indicators**

·   	**Status Dots:** `.status-dot` with glow effect for online/status indicators.

·   	**AI Pulse:** `.ai-pulse` for pulsing AI indicators.

·   	**Sparkle Icon:** Used with AI badges and features (Lucide `Sparkles`).

### **Decorative Elements**

·   	**Floating Circles:** Cobalt/violet with blur, used sparingly for depth.

·   	**Chevron Connector:** Represents process flow and transformation.

·   	**Bottom Highlight:** Gradient line on card hover (`scale-x-0` to `scale-x-100`).

## **13\. Brand Expression Across Mediums**

| Medium | Primary Colors | Layout Behavior | Motion/Interaction | Example Use |
| ----- | ----- | ----- | ----- | ----- |
| **Website/UI** | White \+ Cobalt | 12-column responsive | Subtle fade/hover | Product page, case study grid |
| **Slide Decks** | White base, Cobalt headers | 16:9 modular grid | Appear by line | Case study storytelling |
| **Print Collateral** | Matte white, Cobalt ink | Symmetric margins | None | Brochures, one-pagers |
| **Booth/Exhibition** | Cobalt background, white text | Center-aligned | Ambient fade motion | LED wall, signage |
| **Dashboards** | Glass white, AI gradients | Card-based grid, glass nav | Gradient hover, glow effects | ATS pipeline, analytics |

## **14\. Summary**

The **Newtuple Design Language** unites brand, product, and environment into a single, scalable identity system. It reflects the intelligence and precision of a company shaping the agentic enterprise era — calm, consistent, and confidently blue.

The **Cobalt Blue** from the logo is a symbol of clarity, trust, and technology in harmony with human design.
