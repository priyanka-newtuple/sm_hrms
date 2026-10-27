"""Ensure the configured native asset relationship exists before enabling issuance."""
import os
import re

from .errors import AppError
from .platform import PlatformClient


def install(api):
    relation = os.environ.get('HRMS_ASSET_EMPLOYEE_RELATION', '')
    if not relation:
        print('Onboarding asset integration disabled')
        return
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,99}', relation):
        raise AppError(422, 'Invalid onboarding asset relationship name')
    if api.call('GET', '/organizations/current')['id'] != api.org:
        raise AppError(403, 'Asset configuration organization mismatch')
    asset = api.call('GET', '/entity-types/HRMS.Asset')['entity_type_id']
    employee = api.call('GET', '/entity-types/HRMS.Employee')['entity_type_id']
    path = f'/entity-types/{asset}/relations'
    relations = api.call('GET', path)['items']
    if not any(r['relation_name'] == relation and r['to_entity_type_id'] == employee for r in relations):
        api.call('POST', path, json={'to_entity_type_id': employee, 'relation_name': relation})
    assert any(r['relation_name'] == relation and r['to_entity_type_id'] == employee
               for r in api.call('GET', path)['items']), 'Onboarding asset relationship missing'
    print('Onboarding asset relationship verified; forms and enrolled workflows unchanged')


if __name__ == '__main__':
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        install(api)
    finally:
        api.close()
