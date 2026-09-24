import { describe, expect, it } from 'vitest';
import type { FormField } from '../../types';
import { extensionWording } from './extensionWording';
import { WIZARD_COPY_KEYS, clearedWizardCopy, pickWizardCopy } from '../../types/wizardCopy';
import {
  assignmentCount,
  makeItemBadge,
  withItemsRemovedEverywhere,
  withOptionsAdded,
  withSelected,
  type Row,
} from './rows';

describe('withItemsRemovedEverywhere', () => {
  const rows: Row[] = [
    { dropdown: '499-Q', toggles: ['jsi', 'voip'], extensions: { jsi: { client_id: 'C-1' } } },
    { dropdown: 'az', toggles: ['voip'] },
  ];

  it('clears several items from every row in one pass', () => {
    expect(withItemsRemovedEverywhere(rows, ['jsi', 'voip'])).toEqual([
      { dropdown: '499-Q', toggles: [] },
      { dropdown: 'az', toggles: [] },
    ]);
  });

  it('drops the extension values of a removed item only', () => {
    expect(withItemsRemovedEverywhere(rows, ['voip'])[0]).toEqual({
      dropdown: '499-Q',
      toggles: ['jsi'],
      extensions: { jsi: { client_id: 'C-1' } },
    });
  });

  it('is a no-op for an empty removal', () => {
    expect(withItemsRemovedEverywhere(rows, [])).toBe(rows);
  });
});

describe('withOptionsAdded', () => {
  it('adds every missing option, keeping the existing order', () => {
    expect(withOptionsAdded(['voip'], ['jsi', 'voip', 'fiber'])).toEqual(['voip', 'jsi', 'fiber']);
  });

  it('never drops a selection the options no longer list', () => {
    expect(withOptionsAdded(['retired'], ['jsi'])).toEqual(['retired', 'jsi']);
  });
});

describe('assignmentCount', () => {
  it('totals the items assigned across every row', () => {
    expect(
      assignmentCount([
        { dropdown: '499-Q', toggles: ['jsi', 'voip'] },
        { dropdown: 'az', toggles: ['voip'] },
        { dropdown: 'eu', toggles: [] },
      ]),
    ).toBe(3);
  });

  it('is zero when nothing is assigned, so an unselect-all skips the confirm', () => {
    expect(assignmentCount([{ dropdown: '499-Q', toggles: [] }])).toBe(0);
  });
});

describe('makeItemBadge', () => {
  const field = {
    enum_values_2: ['jsi', 'voip', 'fiber'],
    extensions: {
      jsi: { fields: [{ id: 'client_id', label: 'Client ID', type: 'text', required: false }] },
      voip: { fields: [] },
    },
  } as unknown as FormField;

  it('badges an option that reveals fields, required or not', () => {
    expect(makeItemBadge(field)('jsi')).toBe("Details Req'd");
  });

  it('leaves an option with an empty or absent config unbadged', () => {
    expect(makeItemBadge(field)('voip')).toBeUndefined();
    expect(makeItemBadge(field)('fiber')).toBeUndefined();
  });

  it('badges nothing when Extend Field is off', () => {
    expect(makeItemBadge({} as FormField)('jsi')).toBeUndefined();
  });
});

describe('withSelected', () => {
  const rows: Row[] = [{ dropdown: 'az', toggles: ['jsi'], extensions: { jsi: { id: 'C-1' } } }];

  it('seeds a newly picked option with everything staged in step 2', () => {
    expect(withSelected(rows, ['az', 'eu'], ['jsi', 'voip'])[1]).toEqual({
      dropdown: 'eu',
      toggles: ['jsi', 'voip'],
    });
  });

  it('leaves an existing row alone, keeping its per-card unticking', () => {
    expect(withSelected(rows, ['az'], ['jsi', 'voip'])[0]).toBe(rows[0]);
  });

  it('creates an empty row when nothing is staged yet', () => {
    expect(withSelected([], ['az'])).toEqual([{ dropdown: 'az', toggles: [] }]);
  });
});

describe('extensionWording', () => {
  it('falls back to the generic wording every field had before the setting', () => {
    const wording = extensionWording(undefined);
    expect(wording.required).toBe('Details required');
    expect(wording.none).toBe('No details required');
    expect(wording.heading).toBe('Extended details');
  });

  it('cuts a long word for the list pill but not the card wording', () => {
    const wording = extensionWording('Certificate');
    expect(wording.listBadge).toBe("Cert Req'd");
    expect(wording.required).toBe('Certificate required');
    expect(wording.none).toBe('No certificate required');
    expect(wording.heading).toBe('Certificate details');
  });

  it('leaves a word already short enough alone', () => {
    expect(extensionWording('Permit').listBadge).toBe("Permit Req'd");
  });

  it('keeps the first word of a multi-word label', () => {
    expect(extensionWording('Certificate of Authority').listBadge).toBe("Cert Req'd");
  });

  it('drives the step 2 badge off the configured label', () => {
    const field = {
      extension_label: 'Certificate',
      extensions: { jsi: { fields: [{ id: 'a', label: 'A', type: 'text', required: false }] } },
    } as unknown as FormField;
    expect(makeItemBadge(field)('jsi')).toBe("Cert Req'd");
  });
});

describe('pickWizardCopy', () => {
  it('carries every wizard copy key a field declares', () => {
    expect(
      pickWizardCopy({
        step1_label: 'Choose jurisdictions',
        step3_description: 'Tune each one.',
        picklist_id: 'ignored',
      }),
    ).toEqual({ step1_label: 'Choose jurisdictions', step3_description: 'Tune each one.' });
  });

  it('drops blanks so the component falls back to its own wording', () => {
    expect(pickWizardCopy({ step1_label: '   ', step2_label: '' })).toEqual({});
  });

  it('survives a field that declares none of it', () => {
    expect(pickWizardCopy(undefined)).toEqual({});
  });

  it('clears every key it knows about, so a type change leaves nothing behind', () => {
    const cleared = clearedWizardCopy();
    expect(Object.keys(cleared).sort()).toEqual([...WIZARD_COPY_KEYS].sort());
    expect(Object.values(cleared).every((value) => value === undefined)).toBe(true);
  });
});
