# Picklist

Picklist is the reusable list of choice which can be used in select, multiselect
and picklist multiselect form fields.

Someone sets up a list in Settings, say a list of project names. Any field can
then point at that list instead of typing the choices out again. Change the list
once and every field using it sees the change.

Each picklist has 2 parts, one is value and other is label. Value is what is
stored in the backend and used everywhere, while label is placeholder which is
shown on the frontend.

## What does Picklist multiselect field does

It holds two-level choice, which normal multiselect can't do.

The field points at 2 picklist. On record it works as a 3-step process:

1. Pick the primary options from the first list. Each one becomes a card.
2. Apply common item to all, tick items from the second list.
3. Fine-tune per card, pick card on left, tick that card's own items on the
   right.

It is saved one row per primary option:

```json
{ "dropdown": "499-Q", "toggles": ["jsi", "perkinelmer"] }
```

## What changes it

Added a third level: each item in second list can carry its own field.

An user attaches field from the field library to specific option when
configuring the field. On a record, ticking that option makes its fields appear
beneath it, unticking removes them and drops the value.

The saved row gained one key:

```json
{
  "dropdown": "499-Q",
  "toggles": ["jsi", "perkinelmer"],
  "extensions": { "jsi": { "client_id": "C-1", "certificate": ["<file id>"] } }
}
```

Not all fields are allowed to an option, following are the list of option which
can not be attached:

section, picklist_multi, reference, auto_number and timer_duration

A document field is allowed. The backend walks the extension values and claims
the uploaded file for the record the same way it does for a normal document
field.

How to configure this in the app: [configuring-picklist.md](./configuring-picklist.md)
