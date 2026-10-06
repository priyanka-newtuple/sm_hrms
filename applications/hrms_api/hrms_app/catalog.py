"""Versioned HRMS entity, form, and workflow definitions.

The platform is the intended state owner. These definitions are deliberately
separate from the legacy ORM compatibility layer in ``backend/hrms``.
"""

from dataclasses import dataclass

@dataclass(frozen=True)
class HrmsEntityPack:
    entity_type: str
    label: str
    identifier_prefix: str
    fields: tuple[dict, ...]
    initial_state: str
    states: tuple[str, ...]
    terminal_states: frozenset[str]
    transitions: tuple[tuple[str, str, str], ...]  # source, trigger, target

    @property
    def machine_name(self) -> str:
        return self.entity_type.lower().replace(".", "_")

    @property
    def schema_key(self) -> str:
        revision = 2 if self.entity_type in {"HRMS.Employee", "HRMS.ProjectChange"} else 1
        return f"{self.machine_name}_form_v{revision}"

    def entity_request(self, organization_id: str) -> dict:
        return dict(organization_id=organization_id, name=self.entity_type,
                    description=f"{self.label} records managed by the HRMS product pack",
                    schema_definition={"fields": list(self.fields),
                                       "identifier_template": f"{self.identifier_prefix}-{{{{seq}}}}"}, version=1)

    def form_request(self) -> dict:
        return dict(schema_key=self.schema_key, name=f"{self.label} form",
                    entity_type=self.entity_type, fields=list(self.fields))

    def workflow_definition(self) -> dict:
        return dict(machine_key=self.machine_name, name=self.label, entity_type=self.entity_type,
            entity_schema={"entity_type": self.entity_type, "fields": list(self.fields)},
            initial_state=self.initial_state,
            states=[dict(name=name, tags=(["initial"] if name == self.initial_state else []) +
                         (["terminal"] if name in self.terminal_states else [])) for name in self.states],
            transitions=[{"key": f"{source}_to_{target}", "trigger": trigger,
                          "label": trigger.replace("_", " ").title(), "from": source, "to_state": target}
                         for source, trigger, target in self.transitions])


EMPLOYEE_V1_FIELDS = (
    {"field": "employee_code", "type": "string", "required": True},
    {"field": "first_name", "type": "string", "required": True},
    {"field": "last_name", "type": "string", "required": True},
    {"field": "work_email", "type": "email", "required": True},
    {"field": "department", "type": "string", "required": True},
    {"field": "designation", "type": "string", "required": True},
    {"field": "employment_status", "type": "string", "required": True},
    {"field": "reports_to_employee_code", "type": "string"},
    {"field": "platform_user_id", "type": "string"},
)


PACKS = (
    HrmsEntityPack(
        entity_type="HRMS.OnboardingStep", label="Onboarding Step", identifier_prefix="STP",
        fields=(
            {"field": "case_id", "type": "string", "required": True},
            {"field": "sequence", "type": "integer", "required": True},
            {"field": "title", "type": "string", "required": True},
            {"field": "description", "type": "text"},
            {"field": "assigned_to", "type": "string"},
            {"field": "due_date", "type": "string"},
            {"field": "legacy_task_id", "type": "string"},
            {"field": "legacy_completed_at", "type": "string"},
        ),
        initial_state="open", states=("open", "completed", "cancelled"),
        terminal_states=frozenset({"completed", "cancelled"}),
        transitions=(("open", "complete", "completed"), ("open", "cancel", "cancelled")),
    ),
    HrmsEntityPack(
        entity_type="HRMS.Employee",
        label="Employee",
        identifier_prefix="EMP",
        fields=(
            *EMPLOYEE_V1_FIELDS,
            {"field": "employment_type", "type": "string"},
            {"field": "date_joined", "type": "date"},
            {"field": "work_location", "type": "string"},
            {"field": "notice_period_days", "type": "integer"},
            {"field": "phone", "type": "string"},
            {"field": "hrms_role", "type": "string"},
        ),
        initial_state="",
        states=(),
        terminal_states=frozenset(),
        transitions=(),
    ),
    HrmsEntityPack(
        entity_type="HRMS.OnboardingCase",
        label="Onboarding Case",
        identifier_prefix="ONB",
        fields=(
            {"field": "employee_id", "type": "string", "required": True},
            {"field": "template_key", "type": "string", "required": True},
            {"field": "template_version", "type": "integer", "required": True},
        ),
        initial_state="in_progress",
        states=("in_progress", "completed"),
        terminal_states=frozenset({"completed"}),
        transitions=(("in_progress", "complete", "completed"),),
    ),
    HrmsEntityPack(
        entity_type="HRMS.LeaveRequest",
        label="Leave Request",
        identifier_prefix="LVE",
        fields=(
            {"field": "employee_id", "type": "string", "required": True},
            {"field": "manager_id", "type": "string"},
            {"field": "start_date", "type": "date", "required": True},
            {"field": "end_date", "type": "date", "required": True},
            {
                "field": "leave_type",
                "type": "enum",
                "required": True,
                "enum_values": ["annual", "sick", "casual", "unpaid", "other"],
            },
            {"field": "reason", "type": "text"},
            {"field": "decision_comment", "type": "text"},
        ),
        initial_state="pending",
        states=("pending", "approved", "rejected", "cancelled"),
        terminal_states=frozenset({"approved", "rejected", "cancelled"}),
        transitions=(
            ("pending", "approve", "approved"),
            ("pending", "reject", "rejected"),
            ("pending", "cancel", "cancelled"),
        ),
    ),
    HrmsEntityPack(
        entity_type="HRMS.TimesheetEntry",
        label="Timesheet Entry",
        identifier_prefix="TSE",
        fields=(
            {"field": "employee_id", "type": "string", "required": True},
            {"field": "project_id", "type": "string", "required": True},
            {"field": "work_date", "type": "date", "required": True},
            {"field": "week_start_date", "type": "date", "required": True},
            {"field": "hours", "type": "float", "required": True},
            {"field": "notes", "type": "text"},
            {"field": "task_details", "type": "text"},
        ),
        initial_state="draft",
        states=("draft", "submitted", "approved", "rejected"),
        terminal_states=frozenset({"approved"}),
        transitions=(
            ("draft", "submit", "submitted"),
            ("submitted", "approve", "approved"),
            ("submitted", "reject", "rejected"),
            ("rejected", "revise", "draft"),
            ("rejected", "resubmit", "submitted"),
        ),
    ),
    HrmsEntityPack(
        entity_type="HRMS.ProjectChange",
        label="Project Approval",
        identifier_prefix="PCH",
        fields=(
            {"field": "project_id", "type": "string", "required": True},
            {"field": "requested_by_id", "type": "string", "required": True},
            {
                "field": "kind",
                "type": "enum",
                "required": True,
                "enum_values": ["initial", "amendment"],
            },
            {"field": "proposed", "type": "json", "required": True},
            {"field": "note", "type": "text"},
        ),
        initial_state="draft",
        states=("draft", "pending", "changes_requested", "rejected", "approved"),
        terminal_states=frozenset({"approved"}),
        transitions=(
            ("draft", "submit", "pending"),
            ("pending", "approve", "approved"),
            ("pending", "request_changes", "changes_requested"),
            ("pending", "reject", "rejected"),
            ("changes_requested", "revise", "draft"),
            ("rejected", "revise", "draft"),
        ),
    ),
    HrmsEntityPack(
        entity_type="HRMS.JobOpening",
        label="Job Opening",
        identifier_prefix="JOB",
        fields=(
            {"field": "job_description_id", "type": "string", "required": True},
            {"field": "requisition_code", "type": "string", "required": True},
            {"field": "hiring_manager_id", "type": "string", "required": True},
            {"field": "openings", "type": "integer", "required": True},
            {"field": "location", "type": "string"},
            {"field": "work_mode", "type": "string"},
            {"field": "application_deadline", "type": "date"},
        ),
        initial_state="draft",
        states=(
            "draft",
            "pending_approval",
            "approved",
            "published",
            "paused",
            "closed",
            "archived",
        ),
        terminal_states=frozenset({"archived"}),
        transitions=(
            ("draft", "submit", "pending_approval"),
            ("pending_approval", "approve", "approved"),
            ("pending_approval", "request_changes", "draft"),
            ("approved", "publish", "published"),
            ("published", "pause", "paused"),
            ("paused", "resume", "published"),
            ("published", "close", "closed"),
            ("closed", "archive", "archived"),
        ),
    ),
)


from .performance_catalog import performance_packs

PACKS += performance_packs(HrmsEntityPack)

from .project_catalog import project_packs
PROJECT_PACKS = project_packs(HrmsEntityPack, PACKS)
PACKS = tuple(p for p in PACKS if p.entity_type != "HRMS.ProjectChange") + PROJECT_PACKS


from .cockpit_catalog import cockpit_packs, TYPES as COCKPIT_TYPES
COCKPIT_PACKS = cockpit_packs(HrmsEntityPack, PACKS)
PACKS = tuple(p for p in PACKS if p.entity_type not in COCKPIT_TYPES) + COCKPIT_PACKS

from .wfh_catalog import wfh_packs
PACKS += wfh_packs(HrmsEntityPack)

def pack_by_type(entity_type: str) -> HrmsEntityPack:
    return next(pack for pack in PACKS if pack.entity_type == entity_type)
