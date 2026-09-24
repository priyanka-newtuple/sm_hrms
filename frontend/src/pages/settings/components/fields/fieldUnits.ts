export const UNIT_OTHER_VALUE = '__other_unit__';

export interface FieldUnitGroup {
  label: string;
  options: { value: string; label: string }[];
}

/** Units available to Integer fields in the Field Library. Values are kept
 * short and stable because they are persisted in the field version settings. */
export const FIELD_UNIT_GROUPS: FieldUnitGroup[] = [
  {
    label: 'Volume',
    options: [
      { value: 'L', label: 'L - litre' },
      { value: 'mL', label: 'mL - millilitre' },
      { value: 'uL', label: 'uL - microlitre' },
      { value: 'dL', label: 'dL - decilitre' },
      { value: 'cL', label: 'cL - centilitre' },
      { value: 'm3', label: 'm3 - cubic metre' },
      { value: 'cm3 / cc', label: 'cm3 / cc - cubic centimetre' },
    ],
  },
  {
    label: 'Mass and weight',
    options: [
      { value: 'kg', label: 'kg - kilogram' },
      { value: 'g', label: 'g - gram' },
      { value: 'mg', label: 'mg - milligram' },
      { value: 'ug', label: 'ug - microgram' },
      { value: 'ng', label: 'ng - nanogram' },
      { value: 't', label: 't - tonne' },
      { value: 'lb', label: 'lb - pound' },
      { value: 'oz', label: 'oz - ounce' },
    ],
  },
  {
    label: 'Temperature',
    options: [
      { value: 'degC', label: 'degC - degrees Celsius' },
      { value: 'degF', label: 'degF - degrees Fahrenheit' },
      { value: 'K', label: 'K - kelvin' },
    ],
  },
  {
    label: 'Concentration',
    options: [
      { value: 'M', label: 'M - molar (mol/L)' },
      { value: 'mM', label: 'mM - millimolar' },
      { value: 'uM', label: 'uM - micromolar' },
      { value: 'nM', label: 'nM - nanomolar' },
      { value: 'mg/mL', label: 'mg/mL - milligram per millilitre' },
      { value: 'ug/mL', label: 'ug/mL - microgram per millilitre' },
      { value: 'g/L', label: 'g/L - gram per litre' },
      { value: '% w/v', label: '% w/v - percent weight per volume' },
      { value: '% v/v', label: '% v/v - percent volume per volume' },
      { value: 'ppm', label: 'ppm - parts per million' },
      { value: 'ppb', label: 'ppb - parts per billion' },
    ],
  },
  { label: 'Acidity', options: [{ value: 'pH', label: 'pH - pH' }] },
  {
    label: 'Time and duration',
    options: [
      { value: 's', label: 's - second' },
      { value: 'min', label: 'min - minute' },
      { value: 'h', label: 'h - hour' },
      { value: 'day', label: 'day - day' },
      { value: 'week', label: 'week - week' },
    ],
  },
  {
    label: 'Count and quantity',
    options: [
      { value: 'items', label: 'items - items' },
      { value: 'pcs', label: 'pcs - pieces' },
      { value: 'units', label: 'units - units' },
      { value: 'vials', label: 'vials - vials' },
      { value: 'plates', label: 'plates - plates' },
      { value: 'wells', label: 'wells - wells' },
      { value: 'samples', label: 'samples - samples' },
      { value: 'aliquots', label: 'aliquots - aliquots' },
    ],
  },
  {
    label: 'Length and distance',
    options: [
      { value: 'm', label: 'm - metre' },
      { value: 'cm', label: 'cm - centimetre' },
      { value: 'mm', label: 'mm - millimetre' },
      { value: 'um', label: 'um - micrometre' },
      { value: 'nm', label: 'nm - nanometre' },
      { value: 'km', label: 'km - kilometre' },
    ],
  },
  {
    label: 'Pressure',
    options: [
      { value: 'bar', label: 'bar - bar' },
      { value: 'psi', label: 'psi - pounds per square inch' },
      { value: 'kPa', label: 'kPa - kilopascal' },
      { value: 'Pa', label: 'Pa - pascal' },
      { value: 'atm', label: 'atm - atmosphere' },
      { value: 'mmHg', label: 'mmHg - millimetres of mercury' },
      { value: 'torr', label: 'torr - torr' },
    ],
  },
  {
    label: 'Speed and rotation',
    options: [
      { value: 'rpm', label: 'rpm - revolutions per minute' },
      { value: 'xg / rcf', label: 'xg / rcf - relative centrifugal force' },
      { value: 'm/s', label: 'm/s - metres per second' },
    ],
  },
  {
    label: 'Flow rate',
    options: [
      { value: 'mL/min', label: 'mL/min - millilitre per minute' },
      { value: 'uL/min', label: 'uL/min - microlitre per minute' },
      { value: 'L/h', label: 'L/h - litre per hour' },
    ],
  },
  {
    label: 'Amount of substance',
    options: [
      { value: 'mol', label: 'mol - mole' },
      { value: 'mmol', label: 'mmol - millimole' },
      { value: 'umol', label: 'umol - micromole' },
      { value: 'nmol', label: 'nmol - nanomole' },
    ],
  },
  {
    label: 'Density',
    options: [
      { value: 'g/mL', label: 'g/mL - gram per millilitre' },
      { value: 'g/cm3', label: 'g/cm3 - gram per cubic centimetre' },
      { value: 'kg/m3', label: 'kg/m3 - kilogram per cubic metre' },
    ],
  },
  {
    label: 'Optical and instrument readings',
    options: [
      { value: 'AU', label: 'AU - absorbance units' },
      { value: 'OD', label: 'OD - optical density' },
      { value: '%T', label: '%T - percent transmittance' },
      { value: 'V', label: 'V - volt' },
      { value: 'mV', label: 'mV - millivolt' },
      { value: 'A', label: 'A - ampere' },
      { value: 'mA', label: 'mA - milliampere' },
    ],
  },
  {
    label: 'Ratio and multiples',
    options: [
      { value: '%', label: '% - percent' },
      { value: 'x', label: 'x - fold or times' },
      { value: 'ratio', label: 'ratio - ratio' },
    ],
  },
];

export const FIELD_UNIT_VALUES = new Set(
  FIELD_UNIT_GROUPS.flatMap((group) => group.options.map((option) => option.value)),
);
