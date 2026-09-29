from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from hrms.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from hrms.models.employee import Employee
from hrms.models.hr_content import EmployeeReferral, JobDescription, JobOpening, LearningEvent, OrganizationPolicy
from hrms.models.timesheet import Holiday

HR_ROLES = {"HR - Basic", "HR - Full", "Super Admin"}
PUBLISH_ROLES = {"HR - Full", "Super Admin"}
HIRING_ROLES = {"Recruiter", "HR - Full", "Super Admin"}


def role(actor):
    return actor.role.name


def _require(actor, allowed, message="You do not have permission for this action"):
    if role(actor) not in allowed:
        raise PermissionDenied(message)


def _employee(e):
    return {"id": e.id, "name": e.full_name} if e else None


def policy_out(x):
    return {"id": x.id, "title": x.title, "category": x.category, "summary": x.summary, "body": x.body,
            "owner": x.owner, "version": x.version, "effective_date": x.effective_date, "review_date": x.review_date,
            "visibility": x.visibility, "status": x.status, "created_by": _employee(x.created_by),
            "approved_by": _employee(x.approved_by), "published_at": x.published_at}


def event_out(x):
    return {"id": x.id, "title": x.title, "description": x.description, "category": x.category,
            "starts_at": x.starts_at, "ends_at": x.ends_at, "location": x.location, "audience": x.audience,
            "capacity": x.capacity, "registration_url": x.registration_url, "status": x.status,
            "created_by": _employee(x.created_by), "approved_by": _employee(x.approved_by), "published_at": x.published_at}


def jd_out(x):
    return {"id": x.id, "title": x.title, "department": x.department, "level": x.level,
            "responsibilities": x.responsibilities, "requirements": x.requirements,
            "preferred_skills": x.preferred_skills, "experience": x.experience,
            "employment_type": x.employment_type, "is_active": x.is_active}


def opening_out(x):
    return {"id": x.id, "job_description_id": x.job_description_id, "requisition_code": x.requisition_code,
            "hiring_manager": _employee(x.hiring_manager), "openings": x.openings, "location": x.location,
            "work_mode": x.work_mode, "application_deadline": x.application_deadline,
            "referral_bonus": x.referral_bonus, "status": x.status, "job_description": jd_out(x.job_description),
            "created_by": _employee(x.created_by), "published_at": x.published_at}


def referral_out(x):
    return {"id": x.id, "job_opening_id": x.job_opening_id, "referred_by": _employee(x.referred_by),
            "candidate_name": x.candidate_name, "candidate_email": x.candidate_email,
            "candidate_phone": x.candidate_phone, "message": x.message, "status": x.status, "created_at": x.created_at}


def holiday_out(x):
    return {"id": x.id, "holiday_date": x.holiday_date, "name": x.name, "description": x.description,
            "is_optional": x.is_optional, "location": x.location, "status": x.status}


async def dashboard(db, actor):
    _require(actor, HR_ROLES | HIRING_ROLES)
    result = {"role": role(actor), "policies": [], "events": [], "job_descriptions": [], "openings": [], "referrals": [], "holidays": [], "hiring_managers": []}
    if role(actor) in HR_ROLES:
        result["policies"] = [policy_out(x) for x in (await db.execute(select(OrganizationPolicy).options(selectinload(OrganizationPolicy.created_by), selectinload(OrganizationPolicy.approved_by)).order_by(OrganizationPolicy.updated_at.desc()))).scalars()]
        result["events"] = [event_out(x) for x in (await db.execute(select(LearningEvent).options(selectinload(LearningEvent.created_by), selectinload(LearningEvent.approved_by)).order_by(LearningEvent.starts_at))).scalars()]
        result["holidays"] = [holiday_out(x) for x in (await db.execute(select(Holiday).order_by(Holiday.holiday_date))).scalars()]
    if role(actor) in HIRING_ROLES:
        result["hiring_managers"] = [_employee(x) for x in (await db.execute(select(Employee).order_by(Employee.first_name, Employee.last_name))).scalars()]
        result["job_descriptions"] = [jd_out(x) for x in (await db.execute(select(JobDescription).order_by(JobDescription.title))).scalars()]
        result["openings"] = [opening_out(x) for x in (await db.execute(select(JobOpening).options(selectinload(JobOpening.job_description), selectinload(JobOpening.hiring_manager), selectinload(JobOpening.created_by)).order_by(JobOpening.created_at.desc()))).scalars()]
        result["referrals"] = [referral_out(x) for x in (await db.execute(select(EmployeeReferral).options(selectinload(EmployeeReferral.referred_by)).order_by(EmployeeReferral.created_at.desc()))).scalars()]
    return result


async def create_policy(db, actor, payload):
    _require(actor, HR_ROLES)
    x = OrganizationPolicy(**payload.model_dump(), created_by_id=actor.id)
    db.add(x); await db.commit()
    return (await dashboard(db, actor))["policies"][0]


async def create_event(db, actor, payload):
    _require(actor, HR_ROLES)
    x = LearningEvent(**payload.model_dump(), created_by_id=actor.id)
    db.add(x); await db.commit(); await db.refresh(x)
    return event_out((await db.execute(select(LearningEvent).options(selectinload(LearningEvent.created_by), selectinload(LearningEvent.approved_by)).where(LearningEvent.id == x.id))).scalar_one())


async def create_jd(db, actor, payload):
    _require(actor, HIRING_ROLES)
    x = JobDescription(**payload.model_dump(), created_by_id=actor.id)
    db.add(x); await db.commit(); await db.refresh(x)
    return jd_out(x)


async def create_opening(db, actor, payload):
    _require(actor, HIRING_ROLES)
    if await db.get(JobDescription, payload.job_description_id) is None or await db.get(Employee, payload.hiring_manager_id) is None:
        raise ValidationFailed("Choose a valid job description and hiring manager")
    x = JobOpening(**payload.model_dump(), created_by_id=actor.id)
    db.add(x); await db.commit(); await db.refresh(x)
    return opening_out((await db.execute(select(JobOpening).options(selectinload(JobOpening.job_description), selectinload(JobOpening.hiring_manager), selectinload(JobOpening.created_by)).where(JobOpening.id == x.id))).scalar_one())


async def create_holiday(db, actor, payload):
    _require(actor, HR_ROLES)
    if (await db.execute(select(Holiday).where(Holiday.holiday_date == payload.holiday_date))).scalar_one_or_none():
        raise Conflict("A holiday already exists on this date")
    x = Holiday(**payload.model_dump(), status="draft", created_by_id=actor.id, is_active=True)
    db.add(x); await db.commit(); await db.refresh(x)
    return holiday_out(x)


async def submit_content(db, actor, kind, item_id):
    models = {"policies": OrganizationPolicy, "events": LearningEvent, "holidays": Holiday, "openings": JobOpening}
    model = models.get(kind)
    if not model: raise NotFound("Content type not found")
    x = await db.get(model, item_id)
    if not x: raise NotFound("Content not found")
    if kind == "openings": _require(actor, HIRING_ROLES)
    else: _require(actor, HR_ROLES)
    if x.status != "draft": raise Conflict("Only draft content can be submitted")
    x.status = "pending_approval"; await db.commit()
    return {"id": x.id, "status": x.status}


async def approve_or_publish(db, actor, kind, item_id, decision="approve"):
    models = {"policies": OrganizationPolicy, "events": LearningEvent, "holidays": Holiday}
    if kind == "openings":
        x = await db.get(JobOpening, item_id)
        if not x: raise NotFound("Opening not found")
        if x.status == "pending_approval":
            if actor.id != x.hiring_manager_id and role(actor) != "Super Admin": raise PermissionDenied("The hiring manager must approve this requisition")
            x.status = "approved" if decision == "approve" else "draft"; x.approved_by_id = actor.id if decision == "approve" else None
        elif x.status == "approved" and decision == "publish":
            _require(actor, HIRING_ROLES); x.status = "published"; x.published_by_id = actor.id; x.published_at = datetime.now(UTC)
        else: raise Conflict("This opening is not ready for that action")
    else:
        _require(actor, PUBLISH_ROLES)
        model = models.get(kind)
        if not model: raise NotFound("Content type not found")
        x = await db.get(model, item_id)
        if not x: raise NotFound("Content not found")
        if x.status not in ("draft", "pending_approval"): raise Conflict("Content is not ready to publish")
        if decision == "changes_requested": x.status = "draft"; x.approved_by_id = None
        else:
            x.status = "published"; x.approved_by_id = actor.id; x.published_at = datetime.now(UTC)
    await db.commit(); return {"id": x.id, "status": x.status}


async def public_policies(db):
    rows = (await db.execute(select(OrganizationPolicy).options(selectinload(OrganizationPolicy.created_by), selectinload(OrganizationPolicy.approved_by)).where(OrganizationPolicy.status == "published").order_by(OrganizationPolicy.effective_date.desc()))).scalars()
    return [policy_out(x) for x in rows]


async def public_events(db):
    rows = (await db.execute(select(LearningEvent).options(selectinload(LearningEvent.created_by), selectinload(LearningEvent.approved_by)).where(LearningEvent.status == "published").order_by(LearningEvent.starts_at))).scalars()
    return [event_out(x) for x in rows]


async def public_openings(db):
    rows = (await db.execute(select(JobOpening).options(selectinload(JobOpening.job_description), selectinload(JobOpening.hiring_manager), selectinload(JobOpening.created_by)).where(JobOpening.status == "published", JobOpening.application_deadline >= date.today()).order_by(JobOpening.application_deadline))).scalars()
    return [opening_out(x) for x in rows]


async def public_holidays(db):
    rows = (await db.execute(select(Holiday).where(Holiday.status == "published", Holiday.is_active.is_(True)).order_by(Holiday.holiday_date))).scalars()
    return [holiday_out(x) for x in rows]


async def refer(db, actor, opening_id, payload):
    x = await db.get(JobOpening, opening_id)
    if not x or x.status != "published" or x.application_deadline < date.today(): raise NotFound("Open position not found")
    referral = EmployeeReferral(job_opening_id=x.id, referred_by_id=actor.id, **payload.model_dump())
    db.add(referral); await db.commit(); await db.refresh(referral)
    return {"id": referral.id, "status": referral.status}


async def work_items(db, actor, view):
    from hrms.schemas.work import WorkItem
    items = []
    if view == "todo" and role(actor) in PUBLISH_ROLES:
        for model, label in ((OrganizationPolicy, "Policy"), (LearningEvent, "Learning event"), (Holiday, "Holiday")):
            rows = (await db.execute(select(model).where(model.status == "pending_approval"))).scalars()
            for x in rows:
                items.append(WorkItem(id=x.id, source="hr_content", kind="approval", title=f"Publish {label}: {x.title if hasattr(x, 'title') else x.name}", employee_name="People team", department="Human Resources", status=x.status, action_type=f"{model.__tablename__}_publish", assignee_name=actor.full_name, can_act=True, href="/hr-cockpit"))
    opening_query = select(JobOpening).options(selectinload(JobOpening.job_description), selectinload(JobOpening.created_by))
    if view == "todo": opening_query = opening_query.where(JobOpening.status == "pending_approval", JobOpening.hiring_manager_id == actor.id)
    elif view == "waiting": opening_query = opening_query.where(JobOpening.status == "pending_approval", JobOpening.created_by_id == actor.id)
    else: opening_query = opening_query.where(JobOpening.approved_by_id == actor.id, JobOpening.status.in_(["approved", "published"]))
    for x in (await db.execute(opening_query)).scalars():
        items.append(WorkItem(id=x.id, source="hr_content", kind="approval", title=f"Approve requisition: {x.job_description.title}", employee_name=x.created_by.full_name, department=x.job_description.department, status=x.status, due_date=x.application_deadline, action_type="opening_approval", assignee_name=actor.full_name if view == "todo" else "Hiring manager", can_act=view == "todo", href="/hr-cockpit"))
    return items
