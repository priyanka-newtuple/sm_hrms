"""HR content is native configuration; the core runtime remains generic."""

TYPES = (
    "HRMS.Policy",
    "HRMS.LearningEvent",
    "HRMS.HolidayCalendar",
    "HRMS.JobDescription",
    "HRMS.JobOpening",
)
LABELS = (
    "Policy",
    "Learning event",
    "Holiday calendar",
    "Job description",
    "Open position",
)
COMMON = (
    {"field": "title", "type": "string", "required": True},
    {"field": "body", "type": "text", "required": True},
    {
        "field": "audience",
        "type": "enum",
        "enum_values": ["employees", "public"],
        "required": True,
    },
    {"field": "location", "type": "string"},
    {"field": "publish_from", "type": "date"},
    {"field": "publish_until", "type": "date"},
    {
        "field": "public_url",
        "type": "string",
        "description": "Public document / registration / application URL",
    },
    {"field": "approver_id", "type": "string", "required": True},
    {"field": "author_id", "type": "string"},
    {"field": "approver_name", "type": "string"},
    {"field": "author_name", "type": "string"},
    {"field": "publication_id", "type": "string"},
    {"field": "published_at", "type": "string"},
    {"field": "revision", "type": "integer"},
)
EXTRA = {
    TYPES[0]: ({"field": "effective_date", "type": "date"},),
    TYPES[1]: (
        {"field": "event_date", "type": "date", "required": True},
        {"field": "end_date", "type": "date"},
        {"field": "trainer", "type": "string"},
    ),
    TYPES[2]: (
        {"field": "year", "type": "integer", "required": True},
        {
            "field": "holidays",
            "type": "text",
            "required": True,
            "description": "Holidays: one YYYY-MM-DD | Holiday name per line",
        },
    ),
    TYPES[3]: (
        {"field": "department", "type": "string"},
        {"field": "skills", "type": "text"},
    ),
    TYPES[4]: ({"field": "department", "type": "string"},),
}
INTERNAL = {
    "approver_id",
    "author_id",
    "approver_name",
    "author_name",
    "publication_id",
    "published_at",
    "revision",
    "hrms_operation_key",
    "identifier",
}


def cockpit_packs(cls, existing):
    result = []
    for index, kind in enumerate(TYPES):
        old = next((p for p in existing if p.entity_type == kind), None)
        fields = {
            f["field"]: f for f in ((old.fields if old else ()) + COMMON + EXTRA[kind])
        }
        result.append(
            cls(
                entity_type=kind,
                label=LABELS[index],
                identifier_prefix=("POL", "LND", "HOL", "JDS", "JOB")[index],
                fields=tuple(fields.values()),
                initial_state="draft",
                states=old.states
                if old
                else (
                    "draft",
                    "pending_approval",
                    "approved",
                    "published",
                    "paused",
                    "closed",
                    "archived",
                ),
                terminal_states=frozenset({"archived"}),
                transitions=old.transitions
                if old
                else (
                    ("draft", "submit", "pending_approval"),
                    ("pending_approval", "approve", "approved"),
                    ("pending_approval", "request_changes", "draft"),
                    ("approved", "publish", "published"),
                    ("published", "pause", "paused"),
                    ("paused", "resume", "published"),
                    ("published", "close", "closed"),
                    ("closed", "archive", "archived"),
                ),
            )
        )
    return tuple(result)
