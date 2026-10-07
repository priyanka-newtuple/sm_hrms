"""Install a native, tenant-editable staffing-role picklist through public APIs."""

import os

from .catalog import pack_by_type
from .platform import PlatformClient
from .project_catalog import ALLOCATION, ROLE

DEFAULT_PROJECT_ROLES = (
    "Project Manager",
    "Engineer",
    "QA Engineer",
    "Designer",
    "Business Analyst",
    "Consultant",
)
PICKLIST_NAME = "HRMS Project roles"


def install_project_role_picklist(api):
    pack = pack_by_type(ALLOCATION)
    forms = api.call("GET", "/forms/config", params={"entity_type": ALLOCATION})[
        "items"
    ]
    form = next((f for f in forms if f["schema_key"] == pack.schema_key), None)
    if form is None:
        raise RuntimeError(
            "Install the Allocation form before installing project roles"
        )
    field = next((f for f in form["fields"] if f["field"] == "project_role_id"), None)
    if field is None:
        raise RuntimeError("The Allocation form must contain the project_role_id field")
    # A saved binding is tenant configuration, including intentionally emptied picklists.
    # Never repopulate a tenant's list or overwrite its binding on later installs.
    if field.get("picklist_id"):
        return

    picklists = api.call("GET", "/config/picklists")["items"]
    picklist = next((p for p in picklists if p["name"] == PICKLIST_NAME), None)
    if picklist is None:
        if field.get("enum_values"):
            options = [
                {"value": value, "label": value} for value in field["enum_values"]
            ]
        else:
            # Preserve the IDs used by existing allocations and pending requests.
            options = [
                {"value": row["entity_id"], "label": row["data"]["name"]}
                for row in api.records(ROLE, ["name"])
                if row["data"].get("name")
            ]
            names = {option["label"].casefold() for option in options}
            options.extend(
                {"value": name, "label": name}
                for name in DEFAULT_PROJECT_ROLES
                if name.casefold() not in names
            )
        picklist = api.call(
            "POST",
            "/config/picklists",
            json={"name": PICKLIST_NAME, "options": options},
        )

    values = [o["value"] if isinstance(o, dict) else o for o in picklist["options"]]
    updated = {
        **field,
        "type": "enum" if values else "string",
        "picklist_id": picklist["id"],
        "enum_values": values,
        "description": field.get("description") or "Project role",
    }
    api.call(
        "PUT",
        f"/forms/config/{form['schema_key']}",
        json={
            "fields": [
                updated if f["field"] == "project_role_id" else f
                for f in form["fields"]
            ],
        },
    )


def install():
    api = PlatformClient(
        os.environ["PLATFORM_API_URL"],
        os.environ["HRMS_ORGANIZATION_ID"],
        os.environ["HRMS_INSTALL_EMAIL"],
        os.environ["HRMS_INSTALL_PASSWORD"],
    )
    try:
        install_project_role_picklist(api)
    finally:
        api.close()
    print("Project role picklist is configured in the native Allocation form")


if __name__ == "__main__":
    install()
