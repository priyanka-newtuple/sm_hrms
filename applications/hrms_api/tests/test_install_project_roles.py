from copy import deepcopy

from hrms_app.catalog import pack_by_type
from hrms_app.install_project_roles import (
    DEFAULT_PROJECT_ROLES,
    PICKLIST_NAME,
    install_project_role_picklist,
)
from hrms_app.project_catalog import ALLOCATION, ROLE


class Api:
    def __init__(self):
        self.form = deepcopy(pack_by_type(ALLOCATION).form_request())
        self.picklists = []
        self.roles = [
            {"entity_id": "existing-role", "data": {"name": "Engineer"}},
            {"entity_id": "custom-role", "data": {"name": "Tenant specialist"}},
        ]
        self.writes = []

    def records(self, kind, fields):
        assert kind == ROLE
        return deepcopy(self.roles)

    def call(self, method, path, **kwargs):
        if method == "GET":
            return {
                "items": deepcopy(
                    [self.form] if path == "/forms/config" else self.picklists
                )
            }
        self.writes.append((method, path, kwargs["json"]))
        if method == "POST":
            row = {"id": "picklist-1", **deepcopy(kwargs["json"])}
            self.picklists.append(row)
            return row
        assert path == f"/forms/config/{self.form['schema_key']}"
        self.form.update(deepcopy(kwargs["json"]))


def test_installs_all_six_roles_and_legacy_roles_without_changing_other_fields():
    api = Api()
    original = deepcopy(api.form["fields"])
    install_project_role_picklist(api)
    picklist = api.picklists[0]
    assert picklist["name"] == PICKLIST_NAME
    assert {o["label"] for o in picklist["options"]} == set(DEFAULT_PROJECT_ROLES) | {
        "Tenant specialist"
    }
    assert {"value": "existing-role", "label": "Engineer"} in picklist["options"]
    field = next(f for f in api.form["fields"] if f["field"] == "project_role_id")
    assert field["picklist_id"] == picklist["id"]
    assert field["type"] == "enum"
    assert [f for f in api.form["fields"] if f["field"] != "project_role_id"] == [
        f for f in original if f["field"] != "project_role_id"
    ]


def test_reinstall_preserves_customizations_and_intentionally_empty_picklist():
    api = Api()
    install_project_role_picklist(api)
    api.picklists[0]["options"] = []
    api.writes.clear()
    install_project_role_picklist(api)
    assert api.writes == []
    assert api.picklists[0]["options"] == []


def test_existing_field_binding_is_preserved():
    api = Api()
    field = next(f for f in api.form["fields"] if f["field"] == "project_role_id")
    field["picklist_id"] = "tenant-managed-list"
    install_project_role_picklist(api)
    assert api.writes == []


def test_existing_unbound_enum_choices_are_preserved_as_picklist_options():
    api = Api()
    field = next(f for f in api.form["fields"] if f["field"] == "project_role_id")
    field.update(type="enum", enum_values=["Analyst", "Architect"])
    install_project_role_picklist(api)
    assert api.picklists[0]["options"] == [
        {"value": "Analyst", "label": "Analyst"},
        {"value": "Architect", "label": "Architect"},
    ]


def test_existing_named_picklist_is_reused_after_partial_install():
    api = Api()
    api.picklists = [
        {
            "id": "existing-list",
            "name": PICKLIST_NAME,
            "options": [{"value": "qa", "label": "QA specialist"}],
        }
    ]
    install_project_role_picklist(api)
    assert len(api.picklists) == 1
    assert [write[0] for write in api.writes] == ["PUT"]
    field = next(f for f in api.form["fields"] if f["field"] == "project_role_id")
    assert field["picklist_id"] == "existing-list"
    assert field["enum_values"] == ["qa"]
