"""Additive cockpit installer; preserves existing tenant definitions and grants."""

import os

from .catalog import pack_by_type
from .cockpit_catalog import TYPES
from .errors import AppError
from .form_config import has_method_blocks
from .platform import PlatformClient


def install():
    api = PlatformClient(
        os.environ["PLATFORM_API_URL"],
        os.environ["HRMS_ORGANIZATION_ID"],
        os.environ["HRMS_INSTALL_EMAIL"],
        os.environ["HRMS_INSTALL_PASSWORD"],
    )
    marker = {"field": "hrms_operation_key", "type": "string"}
    machines = {}
    for kind in TYPES:
        pack = pack_by_type(kind)
        desired = pack.entity_request(api.org)
        desired["schema_definition"]["fields"].append(marker)
        try:
            existing = api.call("GET", f"/entity-types/{kind}")
        except AppError as e:
            if e.status != 404:
                raise
            api.call("POST", "/entity-types", json=desired)
        else:
            schema = existing["schema_definition"]
            known = {f["field"] for f in schema["fields"]}
            additions = [
                f
                for f in desired["schema_definition"]["fields"]
                if f["field"] not in known
            ]
            if additions:
                api.call(
                    "PUT",
                    f"/entity-types/{kind}",
                    json={
                        "schema_definition": {
                            **schema,
                            "fields": schema["fields"] + additions,
                        }
                    },
                )
        forms = api.call("GET", "/forms/config", params={"entity_type": kind})["items"]
        form = next((f for f in forms if f["schema_key"] == pack.schema_key), None)
        # A type moved onto method blocks is configured there; leave its legacy Form alone.
        migrated = has_method_blocks(api, kind)
        if not form and not migrated:
            api.call("POST", "/forms/config", json=pack.form_request())
        elif form and not migrated:
            known = {f["field"] for f in form["fields"]}
            additions = [f for f in pack.fields if f["field"] not in known]
            if additions:
                api.call(
                    "PUT",
                    f"/forms/config/{form['schema_key']}",
                    json={"fields": form["fields"] + additions},
                )
        published = api.call(
            "GET", "/workflow-state-machines", params={"scope": "published"}
        )["published_items"]
        match = [w for w in published if w["entity_type"] == kind and w["is_active"]]
        if len(match) > 1:
            raise RuntimeError("Choose one active cockpit workflow")
        if not match:
            draft = api.call(
                "POST", "/workflow-state-machines/draft", json={"name": pack.label}
            )
            match = [
                api.call(
                    "POST",
                    f"/workflow-state-machines/{draft['id']}/publish",
                    json={"definition": pack.workflow_definition()},
                )["state_machine"]
            ]
        machines[kind] = match[0]["machine_name"]
    role = next(
        r for r in api.call("GET", "/roles") if r["name"] == "hrms_application_service"
    )
    existing = api.call("GET", f"/roles/{role['id']}")
    keys = (
        "permissions",
        "entity_permissions",
        "field_permissions",
        "workflow_permissions",
        "transition_permissions",
    )
    spec = {
        k: [{a: b for a, b in v.items() if a != "id"} for v in existing[k]]
        for k in keys
    }

    def add(key, item, identity):
        if not any(all(x.get(k) == item[k] for k in identity) for x in spec[key]):
            spec[key].append(item)

    for kind in TYPES:
        pack = pack_by_type(kind)
        for action in ("view", "create", "edit"):
            add(
                "entity_permissions",
                {"entity_type": kind, "action": action, "allowed": True},
                ("entity_type", "action"),
            )
        for f in (*pack.fields, marker):
            add(
                "field_permissions",
                {
                    "entity_type": kind,
                    "field_name": f["field"],
                    "can_view": True,
                    "can_edit": True,
                    "mask_value": False,
                },
                ("entity_type", "field_name"),
            )
        add("workflow_permissions", {"machine_name": machines[kind]}, ("machine_name",))
        for source, trigger, target in pack.transitions:
            add(
                "transition_permissions",
                {
                    "machine_name": machines[kind],
                    "transition_key": f"{source}_to_{target}",
                },
                ("machine_name", "transition_key"),
            )
    api.call("PUT", f"/roles/{role['id']}", json=spec)
    api.close()
    print("Cockpit configuration installed; existing configuration preserved")


if __name__ == "__main__":
    install()
