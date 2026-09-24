const NUMERIC_FIELD_TYPES = new Set(['integer', 'number', 'currency', 'percent']);

export function parseScheduleConditionValue(
  fieldType: string | undefined,
  rawValue: string,
): string | number | boolean {
  const normalizedType = String(fieldType || 'string').toLowerCase();
  const value = rawValue.trim();

  if (normalizedType === 'boolean') {
    if (value !== 'true' && value !== 'false') {
      throw new Error('Choose true or false for this condition');
    }
    return value === 'true';
  }

  if (NUMERIC_FIELD_TYPES.has(normalizedType)) {
    const parsed = Number(value);
    if (!value || !Number.isFinite(parsed)) {
      throw new Error('Enter a valid number for this condition');
    }
    if (normalizedType === 'integer' && !Number.isInteger(parsed)) {
      throw new Error('Enter a whole number for this condition');
    }
    return parsed;
  }

  return value;
}

export function isNumericScheduleField(fieldType: string | undefined): boolean {
  return NUMERIC_FIELD_TYPES.has(String(fieldType || '').toLowerCase());
}

export function isBooleanScheduleField(fieldType: string | undefined): boolean {
  return String(fieldType || '').toLowerCase() === 'boolean';
}
