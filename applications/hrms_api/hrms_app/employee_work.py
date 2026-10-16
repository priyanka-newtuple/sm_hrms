"""Employee workflow inbox projected from native, human-authorized enrollments."""

import os

from .errors import AppError


def feedback_stage(workflow, state):
    """Project feedback from the pinned native graph, without a second lifecycle."""
    transitions = workflow['definition'].get('transitions', [])
    returns = [t for t in transitions if any(
        f['field'] == 'hr_verification_notes' and f.get('required')
        for f in t.get('required_fields', [])) and (
            is_employee_profile_step(workflow, t.get('to_state')) or any(
                g.get('type') == 'field_present' and g.get('field') == 'hr_verification_notes'
                for g in t.get('guards', [])))]
    review = {t.get('from') for t in returns
              if is_employee_profile_step(workflow, t.get('to_state'))}
    if not review:
        return None
    if state in {t.get('to_state') for t in returns}:
        return 'requested'
    if state in review:
        return 'submitted'
    # Only forward paths after verification count as resolved. Return edges
    # never prove approval, and the traversal stops at correction/review states.
    blocked = review | {t.get('to_state') for t in returns}
    pending = list(review)
    visited = set(review)
    resolved = set()
    while pending:
        source = pending.pop()
        for t in transitions:
            target = t.get('to_state')
            if t in returns or t.get('from') != source or not target or target in blocked:
                continue
            resolved.add(target)
            if target not in visited:
                visited.add(target)
                pending.append(target)
    return 'resolved' if state in resolved else None


def is_owner_signoff_step(workflow, state):
    form_id = os.getenv("HRMS_EMPLOYEE_SIGNOFF_FORM_ID")
    return bool(form_id) and any(
        s["name"] == state and any(r["method_id"] == form_id for r in s.get("method_refs", []))
        for s in workflow["definition"].get("states", [])
    )


def is_employee_profile_step(workflow, state):
    form_id = os.getenv("HRMS_EMPLOYEE_PROFILE_FORM_ID")
    return bool(form_id) and any(
        s["name"] == state
        and any(r["method_id"] == form_id for r in s.get("method_refs", []))
        for s in workflow["definition"].get("states", [])
    )


def employee_enrollments(platform, actor):
    result, offset = [], 0
    while True:
        page = platform.request(
            "GET",
            "/workflow-enrollments",
            token=actor.token,
            params={
                "entity_type_name": "HRMS.Employee",
                "fields": "first_name,last_name,identifier,platform_user_id,hr_verification_notes",
                "limit": 200,
                "offset": offset,
            },
        )
        for row in page["items"]:
            if (
                row["organization_id"] != actor.organization_id
                or row["entity_type"] != "HRMS.Employee"
            ):
                raise AppError(502, "Unexpected workflow scope returned by platform")
            if (
                "hrms_onboarding_employee" in actor.roles
                and (row.get("summary_fields") or {}).get("platform_user_id")
                != actor.user_id
            ):
                continue
            result.append(row)
        if page.get("scan_truncated"):
            raise AppError(502, "Employee workflow results were truncated")
        if not page["has_more"]:
            return result
        if not page["items"]:
            raise AppError(502, "Employee workflow page is incomplete")
        offset += len(page["items"])


def employee_work(platform, actor):
    result = []
    grants = transition_grants(platform, actor)
    for row in employee_enrollments(platform, actor):
        workflow = platform.request(
            "GET", f"/workflow-state-machines/{row['workflow_id']}", token=actor.token
        )
        permitted = {
            t["trigger"]
            for t in workflow["definition"]["transitions"]
            if grants is None or (workflow["machine_name"], t["key"]) in grants
        }
        requirements = {
            t["trigger"]: t.get("required_fields", [])
            for t in workflow["definition"]["transitions"]
            if t.get("from", row["current_state"]) == row["current_state"]
        }
        options = [
            {**t, "required_fields": requirements.get(t["trigger"], [])}
            for t in row.get("transition_options", []) if t["trigger"] in permitted
        ]
        if is_owner_signoff_step(workflow, row["current_state"]):
            record = platform.request("GET", f"/entity-records/{row['entity_id']}", token=actor.token)
            if record["organization_id"] != actor.organization_id:
                raise AppError(403, "Employee organization mismatch")
            if record.get("owner_id") != actor.user_id:
                options = []
        data = row.get("summary_fields") or {}
        own = data.get("platform_user_id") == actor.user_id
        if is_employee_profile_step(workflow, row["current_state"]) and not own:
            options = []
        if (not options and not own) or row.get("archived_at"):
            continue
        result.append(
            {
                "entity_id": row["entity_id"],
                "workflow_id": row["workflow_id"],
                "title": " ".join(
                    str(data.get(k) or "") for k in ("first_name", "last_name")
                ).strip()
                or row["display_name"],
                "workflow_label": row["machine_display_name"],
                "current_state": row["current_state"],
                "due_date": row.get("sla_due_at") or row.get("due_date"),
                "actions": options,
                "is_own_onboarding": own,
                "feedback_status": feedback_stage(workflow, row["current_state"])
                if data.get("hr_verification_notes") else None,
                # Native enrollment projection applies the human's field visibility.
                "verifier_feedback": (data.get("hr_verification_notes") or None)
                if is_employee_profile_step(workflow, row["current_state"]) else None,
            }
        )
    return result


def transition_employee(
    platform, actor, entity_id, workflow_id, trigger, idempotency_key
):
    item = next(
        (
            r
            for r in employee_work(platform, actor)
            if r["entity_id"] == entity_id and r["workflow_id"] == workflow_id
        ),
        None,
    )
    if item is None or trigger not in {a["trigger"] for a in item["actions"]}:
        raise AppError(403, "This employee workflow action is not available to you")
    selected = next(a for a in item["actions"] if a["trigger"] == trigger)
    if any(f["field"] == "hr_verification_notes" and f.get("required")
           for f in selected.get("required_fields", [])):
        form = employee_form(platform, actor, entity_id, workflow_id)
        reason = form["values"].get("hr_verification_notes")
        if not isinstance(reason, str) or not reason.strip():
            raise AppError(422, "Enter verification notes / a correction reason before continuing")
    from .onboarding_assets import ASSET_FIELD, enabled, evidence
    if enabled() and any(f['field'] == ASSET_FIELD for f in selected.get('required_fields', [])):
        value = evidence(platform, entity_id)
        if not value and any(f['field'] == ASSET_FIELD and f.get('required') for f in selected['required_fields']):
            raise AppError(422, 'Issue the required asset before completing provisioning')
        platform.request('PUT', f'/entity-records/{entity_id}', token=actor.token, json={'data': {ASSET_FIELD:value}})
    # The native engine rechecks role grants, guards, required fields and state.
    return platform.request(
        "POST",
        f"/entities/{entity_id}/transitions",
        token=actor.token,
        json={
            "entity_id": entity_id,
            "workflow_id": workflow_id,
            "trigger": trigger,
            "idempotency_key": idempotency_key,
        },
    )


def employee_form(platform, actor, entity_id, workflow_id):
    """Resolve the enrollment's pinned version, including completed/older workflows."""
    from .form_config import _presentation, state_form

    enrollment = next(
        (
            e
            for e in employee_enrollments(platform, actor)
            if e["entity_id"] == entity_id and e["workflow_id"] == workflow_id
        ),
        None,
    )
    if not enrollment:
        raise AppError(404, "Employee workflow is not available")
    record = platform.request("GET", f"/entity-records/{entity_id}", token=actor.token)
    if record["organization_id"] != actor.organization_id:
        raise AppError(403, "Employee belongs to another organization")
    if (
        "hrms_onboarding_employee" in actor.roles
        and record["data"].get("platform_user_id") != actor.user_id
    ):
        raise AppError(403, "You can access only your own onboarding")
    workflow = platform.request(
        "GET", f"/workflow-state-machines/{workflow_id}", token=actor.token
    )
    definition = workflow["definition"]
    form = state_form(platform, workflow, enrollment["current_state"])
    permissions = platform.request("GET", "/roles/my-permissions", token=actor.token)
    grants = {
        g["field_name"]: g
        for g in permissions.get("field_permissions", [])
        if g["entity_type"] == "HRMS.Employee"
    }
    admin = "superadmin" in actor.roles
    other_employee_profile = (
        is_employee_profile_step(workflow, enrollment["current_state"])
        and record["data"].get("platform_user_id") != actor.user_id
    )

    def visible(key):
        return admin or bool(
            grants.get(key, {}).get("can_view")
            and not grants.get(key, {}).get("mask_value")
        )

    form["fields"] = [
        {
            **f,
            "read_only": f.get("read_only")
            or other_employee_profile
            or (is_owner_signoff_step(workflow, enrollment["current_state"])
                and record.get("owner_id") != actor.user_id)
            or (not admin and not grants.get(f["field"], {}).get("can_edit")),
        }
        for f in form["fields"]
        if visible(f["field"])
    ]
    stage = feedback_stage(workflow, enrollment['current_state'])
    # Resolved feedback is historical even when Super Admin can edit the field.
    form["fields"] = [f for f in form["fields"]
                      if not (f["field"] == "hr_verification_notes"
                              and (f.get("read_only") or stage == 'resolved'))]
    from .onboarding_assets import ASSET_FIELD, enabled
    asset_field = next((f for f in form['fields'] if f['field'] == ASSET_FIELD), None)
    form['asset_section'] = bool(enabled() and asset_field)
    form['asset_field_editable'] = bool(asset_field and not asset_field.get('read_only'))
    if form['asset_section']:
        form['fields'] = [{**f, 'read_only': True} if f['field'] == ASSET_FIELD else f for f in form['fields']]
    current_keys = {f["field"] for f in form["fields"]}
    configured_fields = {
        f["field"]: f
        for block in definition.get("method_schemas", [])
        for f in block["fields"]
    }
    prior = [
        {**f, "read_only": True}
        for f in configured_fields.values()
        if f["field"] not in current_keys
        and f["field"] in record["data"]
        and visible(f["field"])
    ]
    form["previous_fields"] = _presentation(platform, prior)
    form["values"] = {
        f["field"]: record["data"].get(f["field"])
        for f in [*form["fields"], *form["previous_fields"]]
    }
    form["current_state"] = enrollment["current_state"]
    note = form['values'].get('hr_verification_notes')
    form['feedback_status'] = stage if note else None
    form['previous_feedback'] = note if note and stage == 'resolved' else None
    if form['previous_feedback']:
        form['previous_fields'] = [f for f in form['previous_fields']
                                   if f['field'] != 'hr_verification_notes']
    form["verifier_feedback"] = (
        form["values"].get("hr_verification_notes")
        if is_employee_profile_step(workflow, enrollment["current_state"]) else None
    )
    form["workflow_id"] = workflow_id
    form["entity_id"] = entity_id
    return form


def save_employee_form(platform, actor, entity_id, workflow_id, values):
    from .custom_fields import _typed

    form = employee_form(platform, actor, entity_id, workflow_id)
    editable = {f["field"]: f for f in form["fields"] if not f.get("read_only")}
    if set(values) - set(editable):
        raise AppError(
            403, "Only editable fields on the current native form can be changed"
        )
    checked = {}
    for key, value in values.items():
        field = editable[key]
        if value is None and field.get("required"):
            raise AppError(422, f"{key} is required")
        checked[key] = (
            None
            if value is None
            else _typed(field.get("description") or key, field, value)
        )
    # Native update enforces the human's field and entity permissions; omitted fields are retained.
    return platform.request(
        "PUT", f"/entity-records/{entity_id}", token=actor.token, json={"data": checked}
    )


def transition_grants(platform, actor):
    if "superadmin" in actor.roles:
        return None
    grants = set()
    for membership in platform.call("GET", f"/roles/users/{actor.user_id}/roles"):
        if membership["organization_id"] != actor.organization_id:
            raise AppError(403, "Role organization mismatch")
        role = platform.call("GET", f"/roles/{membership['role_id']}")
        if role["organization_id"] != actor.organization_id:
            raise AppError(403, "Role organization mismatch")
        grants.update(
            (p["machine_name"], p["transition_key"])
            for p in role["transition_permissions"]
        )
    return grants


def authorize_employee_file(platform, actor, method, path, query):
    import json

    if method == "GET" and path == "config/file-types":
        if "workflow:read" not in actor.permissions:
            raise AppError(403, "Workflow access is required")
        return
    upload = method == "POST" and path == "filehandler/upload"
    if upload:
        entity_id = query.get("owner_entity_id")
        try:
            field_key = json.loads(query.get("metadata", "{}")).get("field_key")
        except (ValueError, AttributeError):
            raise AppError(422, "Document field metadata is required") from None
    elif method == "GET" and len(path.split("/")) in {2, 3}:
        parts = path.split("/")
        if len(parts) == 3 and parts[2] not in {"download", "download-url"}:
            raise AppError(403, "Unsupported document operation")
        metadata = platform.request(
            "GET", f"/filehandler/{parts[1]}", token=actor.token
        )
        entity_id = metadata.get("owner_entity_id")
        field_key = (metadata.get("metadata") or {}).get("field_key")
    else:
        raise AppError(403, "Use the employee document field")
    enrollment = next(
        (
            e
            for e in employee_enrollments(platform, actor)
            if e["entity_id"] == entity_id
        ),
        None,
    )
    if not enrollment:
        raise AppError(403, "Employee document is not available")
    form = employee_form(platform, actor, entity_id, enrollment["workflow_id"])
    fields = form["fields"] if upload else [*form["fields"], *form["previous_fields"]]
    field = next(
        (f for f in fields if f["field"] == field_key and f.get("type") == "document"),
        None,
    )
    if not field or (upload and field.get("read_only")):
        raise AppError(403, "Document field is not accessible in this step")


def onboarding_tracker(platform, actor):
    """Read-only overview of native enrollments, including work owned by others."""
    from .policy import require
    require(actor, 'onboarding:view')
    actionable = {(i['entity_id'], i['workflow_id']): i for i in employee_work(platform, actor)}
    users = {u['id']: u.get('full_name') or u['email'] for u in platform.users()
             if u['organization_id'] == actor.organization_id}
    result = []
    for row in employee_enrollments(platform, actor):
        if row.get('archived_at'):
            continue
        workflow = platform.request('GET', f"/workflow-state-machines/{row['workflow_id']}", token=actor.token)
        record = platform.request('GET', f"/entity-records/{row['entity_id']}", token=actor.token)
        if record['organization_id'] != actor.organization_id:
            raise AppError(403, 'Employee organization mismatch')
        state = next(s for s in workflow['definition']['states'] if s['name'] == row['current_state'])
        summary = row.get('summary_fields') or {}
        item = actionable.get((row['entity_id'], row['workflow_id']), {
            'entity_id': row['entity_id'], 'workflow_id': row['workflow_id'],
            'title': ' '.join(str(summary.get(k) or '') for k in ('first_name','last_name')).strip() or row['display_name'],
            'workflow_label': row['machine_display_name'], 'current_state': row['current_state'],
            'actions': [], 'due_date': row.get('sla_due_at') or row.get('due_date'),
        })
        result.append({**item, 'completed': 'terminal' in state.get('tags', []),
                       'workflow_version': workflow.get('version'),
                       'states': [s['name'] for s in sorted(workflow['definition']['states'], key=lambda s:s.get('order', 0))],
                       'assigned_to': users.get(record.get('assignee_id')),
                       'started_by': users.get(record.get('owner_id'))})
    return result
