# Changelog authoring rules

Every `.mdx` file in this folder becomes one entry on the in-app **What's New**
page (`/changelogs`). There is no registry — add a file, it shows up. Follow
these rules when creating a new changelog.

## 1. File location & name

- Put the file directly in `/changelogs` (repo root, **not** inside `frontend/`).
- Name it `YYYY-MM-DD-slug.mdx`, e.g. `2026-07-16-in-app-changelog.mdx`.
  The date prefix keeps the folder sorted and readable; the page itself sorts by
  the `date` frontmatter field, not the filename.

## 2. Frontmatter (required at top of every file)

```yaml
---
title: "Short entry title"          # REQUIRED — shown as the heading
date: "2026-07-16"                  # REQUIRED — ISO YYYY-MM-DD, drives sort order
version: "0.17.0"                   # optional — shown as the version badge
tags: ["Feature", "Docs"]           # optional — shown as pills
description: "One-line summary."    # optional — metadata only, not rendered
---
```

- `date` **must** be `YYYY-MM-DD`. Entries render newest-first by this value.
- Keep `title` under ~60 chars. Use real product-facing wording, not commit-speak.
- `tags`: 1–3 short labels (`Feature`, `Fix`, `Improvement`, `Docs`, `UI`…).

## 3. Body content

Standard Markdown works: headings, **bold**, lists, links, images.

- **Images**: use full `https://` URLs. Keep them optional — most entries don't
  need one. They render rounded/bordered via the page's `prose` styles.
- **Lead with impact**: one sentence on what changed and why it matters, then a
  bulleted list of specifics.

## 4. Components (MDX)

Only components **registered in the page's component map** may be used in an
entry. Currently registered (see `frontend/src/pages/Changelogs/index.tsx`,
`mdxComponents`):

- `Accordion`, `AccordionItem`, `AccordionTrigger`, `AccordionContent`

To use a new component, first add it to `mdxComponents` in that file — otherwise
MDX renders nothing for that tag.

### Accordion usage

```mdx
<Accordion type="multiple" className="w-full not-prose">
  <AccordionItem value="details" className="border-b-0">
    <AccordionTrigger>Section title</AccordionTrigger>
    <AccordionContent className="flex flex-col gap-4 text-balance">
      ...content...
    </AccordionContent>
  </AccordionItem>
</Accordion>
```

- Add `className="not-prose"` on the `Accordion` so prose styles don't fight it.
- Add `className="border-b-0"` on each `AccordionItem` to drop the divider line
  (the shared component adds `border-b` by default).
- Each `AccordionItem` needs a unique `value`.

## 5. Visibility

The What's New page is **hidden by default** (`hideWhatsNew` feature flag). An
org opts in via **Settings → Display → What's New**. Adding an entry does not
make the page visible on its own.

## 6. Docker note

`/changelogs` lives outside the frontend Vite root, so it is:
- mounted into the frontend container in `docker-compose.local.yml`
  (`./changelogs:/app/changelogs`), and
- allowed via `server.fs.allow` in `frontend/vite.config.ts`.

If you change either, **recreate** the frontend container
(`docker compose -f docker-compose.local.yml up -d --force-recreate modular-frontend`) —
`server.fs` changes don't hot-reload.

## Checklist

- [ ] File in `/changelogs`, named `YYYY-MM-DD-slug.mdx`
- [ ] Frontmatter has `title` + `date` (ISO); `version`/`tags` if relevant
- [ ] Body leads with impact, then specifics
- [ ] Any non-Markdown component is registered in `mdxComponents`
- [ ] Accordions use `not-prose` + `border-b-0` + unique `value`
