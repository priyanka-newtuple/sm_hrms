# Configuring a picklist field (frontend)

Companion to [picklist.md](./picklist.md), which explains what a picklist is and
what gets stored. This one is the click path: how an admin sets one up in the
app, and what the end user sees afterwards.

Everything here is configuration. No code, no deploy.

## 1. Make the list

Settings has two tabs that both show the same **Picklists** panel: **Fields**
and **Forms**. Expand it and hit **Add Picklist**.

A picklist is a name and a list of `{ value, label }` pairs. Value is stored on
the record, label is what people read. Pick a value you can live with, changing
it later does not rewrite records already saved against the old one. The pencil
edits the options in a form, the `{}` button edits the raw JSON when you are
pasting a long list in.

One list can back any number of fields. That is the point of it, change the
options once and every field using the list picks them up.

## 2. Make the field

Two places, same editor underneath:

- **Settings -> Forms**, on the entity type's form. The field lives on that form
  only.
- **Settings -> Fields** (Field Library). The field is reusable and pinning it
  into a Method carries the config along.

Set **Field Type** and the rest of the block appears:

| Type | What you choose |
| --- | --- |
| Select | one picklist, single choice |
| Multi Select | one picklist, many choices |
| Picklist Multi (Dropdown Add) | two picklists |

For Picklist Multi you get two dropdowns:

- **Dropdown picklist** is the primary list. Each option the user picks becomes
  a card.
- **Multi-select picklist** is the secondary list. Its options are the items
  ticked inside each card.

Save is refused until both are chosen.

Note the snapshot: on save the field stores the picklist's values and labels as
they are at that moment. Editing the picklist later and re-saving the field
refreshes them.

## 3. Extend Field

Under the two dropdowns there is an **Extend Field** switch, off by default. Off
means the field behaves exactly as it always did.

The switch stays disabled until a multi-select picklist is chosen, since its
options are the things being extended. Turn it on and you get one row per option
of that list.

```
Extend Field                                              [ on ]
Reveal extra Field Library fields when a specific option is selected.

  Broadband     Bandwidth x   Provider x            [ + Add fields ]
  VoIP          Phone Number* x   Lines x           [ + Add fields ]
  Fiber         No extended fields                  [ + Add fields ]
```

**Add fields** opens the Field Library browser, the same one the Methods editor
uses, with search, type filter and multi-select. Tick what you want and add.
Fields are never authored here, if the one you want does not exist yet use the
link to the Field Library, create it, come back.

Each pick is copied into the field as a snapshot, with the library id it came
from. That means a later edit in the Field Library does not silently change
forms already configured. If you want the newer shape, remove the chip and add
it again.

The `x` on a chip removes that field from that option. A `*` on a chip means the
library field is required, and it will be required on the record too, but only
when its option is selected.

Turning the switch back off asks for confirmation and discards the whole
configuration.

### What you cannot attach

The picker filters these out: Section, Picklist Multi, Reference, Auto Number,
Timer / Duration. Sections hold no value, a picklist multi inside a picklist
multi is a wizard inside a wizard, and the last three are resolved or generated
by the backend for top-level fields only. Everything else the form renders is
allowed, including Table and Document.

### Pruning on save

Saving the field cleans up after you:

- options that are no longer in the second picklist are dropped, so editing or
  swapping the list cannot leave stale config behind
- options with no fields are dropped
- switching the field to any other type drops the extension config entirely
- once nothing is left, Extend Field reads as off again

So an option you configured, then removed from the picklist, quietly disappears
from the field the next time you save it. Check the rows after editing a
picklist.

## 4. What the end user gets

On the record form the field is a three-step wizard:

1. **Choose** the primary options. One card per option.
2. Tick items from the second list, and optionally **Apply selected items to
   all** to seed every card at once.
3. **Assign items per option**, cards on the left, item grid on the right, with
   All / Clear / Copy from another card / filter.

With Extend Field on, step 3 grows an **Extended details** block under the item
grid. One card per item ticked in the active row, in picklist order, each headed
by the item and a badge:

| Badge | Means |
| --- | --- |
| No details required | nothing configured for that option |
| Details required | at least one configured field is required |
| Optional details | fields configured, none required |

The cards are per row. The same item under two different primary options holds
two different sets of values, which is the whole reason the feature exists.
Unticking an item removes its card and drops the values that were typed into it,
there is no undo, so it is worth saying so to users who treat checkboxes
casually.

Validation runs only on what is visible. A required extended field blocks save
only while its option is selected. A blank one reports against the parent field
("Services is required"), so the user has to open the wizard and look for the
card with the warning badge. A badly typed one is more helpful and names the
row and option, by their stored values rather than their labels:

```
"Services" - az / voip: "Number of Lines" must be a whole number
```

Extension values also appear in the slide-over and in CSV/PDF exports. They are
not filterable and do not show on pipeline cards.

## 5. Things that catch people out

- **Permissions are per top-level field.** Extended values inherit the read and
  write permission of the picklist multi field that owns them. You cannot
  permission one extended field on its own.
- **Two library fields sharing a field key** cannot sit on the same option, the
  value map is keyed by that key. The picker tells you which pick it skipped.
- **Grid forms** cannot carry this config, their cells treat picklist multi as
  text.
- **Blob size.** Every option's fields are snapshotted into the form schema.
  Many options times many fields makes a large schema. Nothing breaks today,
  but do not configure twenty fields on twenty options and expect it to stay
  tidy.

## Where the code lives

| Piece | File |
| --- | --- |
| Extend Field block | `frontend/src/pages/settings/components/form-config/components/PicklistExtensionsEditor.tsx` |
| Field Library picker | `.../form-config/components/ExtensionFieldPickerModal.tsx` |
| Disallowed types | `.../form-config/constants.ts` |
| Save-time pruning | `.../form-config/fieldSaveValidation.ts` |
| Forms configurator | `.../form-config/components/FieldRow.tsx` |
| Field Library configurator | `frontend/src/pages/settings/components/fields/LibraryFieldEditor.tsx` |
| Runtime wizard | `frontend/src/core/components/PicklistMultiWizard.tsx` |
| Runtime extended cards | `frontend/src/core/components/PicklistExtensionCards.tsx` |
| Validation | `frontend/src/shared/utils/entityForm.ts` |
