"""Native form responses for employee provisioning fixtures."""
from hrms_app.catalog import pack_by_type

ROUTES = {
 '/workflow-state-machines': {'published_items': []},
 '/method-library/methods': {'items': []},
 '/config/picklists': {'items': []},
 '/forms/config': {'items': [{'schema_key': pack_by_type('HRMS.Employee').schema_key, 'name': 'Employee', 'fields': [
     {'field': 'department', 'type': 'enum', 'enum_values': ['Engineering', 'Finance', 'People']},
     {'field': 'designation', 'type': 'enum', 'enum_values': ['Engineer', 'Senior Software Engineer', 'Software Engineer', 'Project Manager']},
 ]}]},
}
