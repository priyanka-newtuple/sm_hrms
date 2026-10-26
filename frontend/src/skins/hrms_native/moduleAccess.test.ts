import { expect, it } from 'vitest';
import { canOpenModule } from './moduleAccess';

it('fails closed while grants are unavailable and when module grants are revoked', () => {
  for (const module of ['leave', 'performance'] as const) {
    expect(canOpenModule(module)).toBe(false);
    expect(canOpenModule(module, { capabilities: [], employee_profile: true })).toBe(false);
  }
});
it('employee linkage alone never grants leave access', () => {
  expect(canOpenModule('leave', {capabilities: [], employee_profile: true})).toBe(false);
  expect(canOpenModule('leave', {capabilities: ['leave:create'], employee_profile: true})).toBe(true);
  expect(canOpenModule('leave', {capabilities: ['leave:decide'], employee_profile: true})).toBe(true);
  expect(canOpenModule('leave', {capabilities: ['leave:create'], employee_profile: false})).toBe(false);
});
it('performance module follows its configured management or approval grants', () => {
  expect(canOpenModule('performance', {capabilities: ['employee:read', 'cockpit:view']})).toBe(false);
  expect(canOpenModule('performance', {capabilities: ['performance:manage']})).toBe(true);
  expect(canOpenModule('performance', {capabilities: ['performance:approve_cycle']})).toBe(true);
});
