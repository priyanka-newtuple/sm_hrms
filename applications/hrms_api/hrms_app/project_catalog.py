"""Project product configuration; installed via public platform APIs."""

from dataclasses import replace

PROJECT = "HRMS.Project"
CUSTOMER = "HRMS.Customer"
ROLE = "HRMS.ProjectRole"
ALLOCATION = "HRMS.Allocation"
CHANGE = "HRMS.ProjectChange"
ALLOCATION_CHANGE = "HRMS.AllocationChange"
TYPES = (CUSTOMER, ROLE, PROJECT, CHANGE, ALLOCATION, ALLOCATION_CHANGE)


def fields(strings=(), dates=(), integers=(), numbers=(), jsons=()):
    return tuple(
        {"field": name, "type": kind}
        for kind, names in (
            ("string", strings),
            ("date", dates),
            ("integer", integers),
            ("float", numbers),
            ("json", jsons),
        )
        for name in names
    )


REQUEST_FIELDS = fields(
    strings=(
        "approver_id",
        "approver_name",
        "requested_by_name",
        "decision_comment",
        "decided_by",
        "decided_at",
        "applied",
    ),
    integers=("revision", "expected_revision"),
)


def project_packs(pack, existing):
    change = next(p for p in existing if p.entity_type == CHANGE)
    # A new published family version is installed for withdrawal; existing enrollments stay pinned.
    change = replace(
        change,
        fields=(*change.fields, *REQUEST_FIELDS),
        transitions=(*change.transitions, ("pending", "withdraw", "draft")),
    )
    return (
        pack(
            CUSTOMER,
            "Customer",
            "CUS",
            fields(
                strings=(
                    "name",
                    "contact_name",
                    "contact_email",
                    "created_by",
                    "currency",
                ),
                numbers=("contract_value",),
            ),
            "",
            (),
            frozenset(),
            (),
        ),
        pack(
            ROLE,
            "Project role",
            "PRL",
            fields(strings=("name",)),
            "",
            (),
            frozenset(),
            (),
        ),
        pack(
            PROJECT,
            "Project",
            "PRJ",
            fields(
                strings=(
                    "name",
                    "description",
                    "customer_id",
                    "customer_name",
                    "pm_id",
                    "pm_name",
                    "dm_id",
                    "dm_name",
                    "created_by",
                    "engagement_type",
                    "practice",
                    "currency",
                    "health",
                ),
                dates=("start_date", "end_date"),
                integers=("revision",),
                numbers=("budget_amount", "billing_rate", "planned_hours"),
            ),
            "draft",
            ("draft", "planned", "active", "on_hold", "completed", "archived"),
            frozenset({"archived"}),
            (
                ("draft", "approve", "planned"),
                ("planned", "start", "active"),
                ("active", "hold", "on_hold"),
                ("on_hold", "resume", "active"),
                ("planned", "complete", "completed"),
                ("active", "complete", "completed"),
                ("on_hold", "complete", "completed"),
                ("completed", "archive", "archived"),
            ),
        ),
        change,
        pack(
            ALLOCATION,
            "Allocation",
            "ALC",
            fields(
                strings=(
                    "project_id",
                    "employee_id",
                    "employee_name",
                    "project_role_id",
                    "project_role_name",
                    "billable",
                    "created_by",
                ),
                dates=("start_date", "end_date"),
                integers=("revision",),
                numbers=("percentage", "billing_rate"),
            ),
            "planned",
            ("planned", "active", "completed", "cancelled"),
            frozenset({"completed", "cancelled"}),
            (
                ("planned", "start", "active"),
                ("planned", "complete", "completed"),
                ("active", "complete", "completed"),
                ("planned", "cancel", "cancelled"),
                ("active", "cancel", "cancelled"),
            ),
        ),
        pack(
            ALLOCATION_CHANGE,
            "Allocation approval",
            "ACH",
            (
                *fields(
                    strings=(
                        "project_id",
                        "allocation_id",
                        "requested_by_id",
                        "kind",
                        "note",
                    ),
                    jsons=("proposed",),
                ),
                *REQUEST_FIELDS,
            ),
            "draft",
            ("draft", "pending", "changes_requested", "rejected", "approved"),
            frozenset({"approved"}),
            (
                ("draft", "submit", "pending"),
                ("pending", "approve", "approved"),
                ("pending", "request_changes", "changes_requested"),
                ("pending", "reject", "rejected"),
                ("pending", "withdraw", "draft"),
                ("changes_requested", "revise", "draft"),
                ("rejected", "revise", "draft"),
            ),
        ),
    )
