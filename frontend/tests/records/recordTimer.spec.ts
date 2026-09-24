import { expect, test } from '@playwright/test';

import { calculateRecordedTimerSeconds } from '../../src/shared/hooks/useRecordTimer';

test('records a fresh frontend timer in whole seconds', () => {
  expect(
    calculateRecordedTimerSeconds({
      startedAt: 1_000,
      pausedAt: null,
      pausedMs: 0,
      nowMs: 11_999,
    }),
  ).toBe(10);
});

test('resuming adds the new run to the previously saved duration', () => {
  expect(
    calculateRecordedTimerSeconds({
      baseSeconds: 90,
      startedAt: 1_000,
      pausedAt: null,
      pausedMs: 0,
      nowMs: 11_000,
    }),
  ).toBe(100);
});

test('paused time is excluded from the final duration', () => {
  expect(
    calculateRecordedTimerSeconds({
      baseSeconds: 5,
      startedAt: 1_000,
      pausedAt: null,
      pausedMs: 4_000,
      nowMs: 15_000,
    }),
  ).toBe(15);
});

test('a currently paused timer stays frozen at the pause instant', () => {
  expect(
    calculateRecordedTimerSeconds({
      baseSeconds: 5,
      startedAt: 1_000,
      pausedAt: 8_000,
      pausedMs: 2_000,
      nowMs: 20_000,
    }),
  ).toBe(10);
});

test('an idle timer preserves the already saved value', () => {
  expect(
    calculateRecordedTimerSeconds({
      baseSeconds: 42,
      startedAt: null,
      pausedAt: null,
      pausedMs: 0,
      nowMs: 99_000,
    }),
  ).toBe(42);
});
