import { expect, it } from 'vitest';
import { buildPermissionsConfig } from './permissions-data';

it('keeps registered permission keys in the native editor and presets', () => {
 const key = 'tenant.org.hrms.project:approve';
 const config = buildPermissionsConfig([{key,resource:'hrms.project',action:'approve',description:'Approve projects'},
   {key:'role:read',resource:'role',action:'read',description:'Read roles'}]);
 expect(config.PERMISSION_KEYS['hrms.project:approve']).toBe(key);
 expect(config.ALL_PERMISSION_KEYS).toContain(key);
 expect(config.PERMISSION_PRESETS.full().has(key)).toBe(true);
 expect(config.PERMISSION_PRESETS.read().has(key)).toBe(false);
 expect(config.RESOURCE_META['hrms.project'].label).toBe('Hrms Project');
});
