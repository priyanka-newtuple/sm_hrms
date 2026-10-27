"""Migrate optional legacy stickers using native versioned configuration APIs."""
import os
from copy import deepcopy

from .asset_catalog import ASSET
from .catalog import pack_by_type
from .errors import AppError
from .form_config import configured_form, has_method_blocks, active_workflow
from .platform import PlatformClient


def install(api):
    entity = api.call('GET', '/entity-types/' + ASSET)
    schema = deepcopy(entity['schema_definition'])
    if '{{seq}}' not in (schema.get('identifier_template') or ''):
        raise AppError(409, 'Configure a native Asset identifier template before bulk entry')
    presentation = configured_form(api, ASSET)
    tag = next((f for f in presentation['fields'] if f['field'] == 'asset_tag'), None)
    legacy = None
    if tag and tag.get('required'):
        if presentation.get('workflow_versioned') or has_method_blocks(api, ASSET):
            migrate_method_form(api)
        else:
            forms = api.call('GET', '/forms/config', params={'entity_type': ASSET})['items']
            legacy = next((f for f in forms if f['schema_key'] == pack_by_type(ASSET).schema_key), None)
            if legacy is None:
                raise AppError(409, 'Asset form configuration was not found')
    changed = False
    for field in schema.get('fields', []):
        if field['field'] == 'asset_tag' and field.get('required'):
            field['required'] = False
            changed = True
    if changed:
        api.call('PATCH', '/entity-types/' + ASSET, json={'schema_definition': schema})
    if legacy:
        fields = deepcopy(legacy['fields'])
        for field in fields:
            if field['field'] == 'asset_tag':
                field['required'] = False
        api.call('PUT', '/forms/config/' + legacy['schema_key'], json={'fields': fields})
    print('Native asset identifier and optional sticker configuration verified')


def migrate_method_form(api):
    current = active_workflow(api, ASSET)
    if not current:
        raise AppError(409, 'Publish the Asset workflow before bulk entry')
    machine = current['machine_name']
    drafts = api.call('GET', '/workflow-state-machines', params={'scope': 'draft', 'machine_name': machine})['draft_items']
    if drafts:
        raise AppError(409, 'Resolve the existing Asset workflow draft before bulk entry migration')
    definition = deepcopy(current['definition'])
    refs = [r for s in definition['states'] for r in s.get('method_refs', [])]
    methods = {r['method_id']: api.call('GET', '/method-library/methods/' + r['method_id']) for r in refs}
    # Never publish unrelated, unpublished method edits or alter a shared method.
    for ref in refs:
        detail = methods[ref['method_id']]
        if ref.get('version_id') and ref['version_id'] != detail['version']['version_id']:
            raise AppError(409, 'Publish or reconcile pending Asset form edits before migration')
        if any(f['field_key'] == 'asset_tag' and f.get('required') for f in detail['fields']):
            if set(detail['identity'].get('entity_types', [])) != {ASSET}:
                raise AppError(409, 'Shared asset form requires a reviewed configuration migration')
    for mid, detail in methods.items():
        if not any(f['field_key'] == 'asset_tag' and f.get('required') for f in detail['fields']):
            continue
        fields = [{'library_field_id': f['library_field_id'], 'version_id': f['field_version_id'],
                   **{k: f.get(k) for k in ('label', 'placeholder', 'position', 'required', 'inherit_from', 'source_entity_type', 'source_field_key', 'ownership')}} for f in detail['fields']]
        for source, field in zip(detail['fields'], fields):
            if source['field_key'] == 'asset_tag':
                field['required'] = False
        updated = api.call('PUT', '/method-library/methods/' + mid + '/fields', json={'fields': fields})
        for ref in refs:
            if ref['method_id'] == mid:
                ref['version_id'] = updated['version']['version_id']
    draft = api.call('POST', '/workflow-state-machines/' + machine + '/draft')
    api.call('POST', '/workflow-state-machines/' + draft['id'] + '/publish',
             json={'definition': definition, 'canvas_metadata': current.get('canvas_metadata')})


if __name__ == '__main__':
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        install(api)
    finally:
        api.close()
