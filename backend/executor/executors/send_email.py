"""Executor: send an email and immediately fire the outcome trigger."""

from __future__ import annotations

from typing import Any

from background_jobs.db_models import ActionRunModel
from common.logger import logger
from common.security import create_form_link_token
from executor.executors.base import (
    apply_template_placeholders,
    fail,
    get_field,
    get_frontend_url,
)
from executor.models.interface import (
    BaseExecutor,
    ExecutorData,
    ExecutorDefinition,
    ExecutorInput,
    ExecutorResponse,
)


class SendEmailExecutor(BaseExecutor):
    """Send an email and immediately fire the outcome trigger — no form wait."""

    def __init__(
        self,
        mail_service: Any = None,
        database_service_manager: Any = None,
        config: Any = None,
        notifications_service: Any = None,
    ) -> None:
        self._mail = mail_service
        self._database_service_manager = database_service_manager
        self._config = config

    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name="mail.send_email",
            description="Send an email and immediately fire the trigger on success.",
            supported_outcomes=["sent", "failed"],
        )

    def execute(self, input_payload: ExecutorInput, db: Any = None) -> ExecutorResponse:
        try:
            fields = input_payload.fields
            org_id = get_field(fields, "org_id")
            entity_id = get_field(fields, "entity_id") or input_payload.entity_id
            to_email = get_field(fields, "to")

            if not all([org_id, to_email]):
                return fail("missing required field: org_id or to")

            base_url = get_frontend_url(self._config)

            template_id = get_field(fields, "template_id")
            subject = get_field(fields, "subject")
            body_html = get_field(fields, "body_html")

            if template_id and self._mail and db:
                template = (
                    self._mail.email_config_model_service.get_email_template(
                        db, org_id, template_id
                    )
                    if self._mail.email_config_model_service
                    else None
                )
                if template:
                    subject = subject or str(template.get("subject") or "")
                    body_html = body_html or str(template.get("body_html") or "")

            if not all([subject, body_html]):
                return fail("missing subject or body_html (no template found)")

            subject = apply_template_placeholders(subject, fields)
            body_html = apply_template_placeholders(body_html, fields)

            org_id_for_token = get_field(fields, "org_id") or org_id or ""
            has_form_link = entity_id and "{{form_link}}" in (body_html or "")
            receive_data_run = None
            if has_form_link and db:
                query = (
                    db.query(ActionRunModel)
                    .filter(ActionRunModel.entity_id == entity_id)
                    .filter(ActionRunModel.action_kind == "form.receive_data")
                    .filter(ActionRunModel.status.in_(["pending", "pending_external"]))
                )
                if org_id:
                    query = query.filter(ActionRunModel.organization_id == org_id)
                receive_data_run = query.order_by(ActionRunModel.created_at.desc()).first()
                form_run_id = str(receive_data_run.run_id) if receive_data_run else ""
                token = create_form_link_token(
                    entity_id=entity_id,
                    run_id=form_run_id,
                    org_id=org_id_for_token,
                )
                form_url = f"{base_url}/forms/submit/{token}"
                body_html = body_html.replace("{{form_link}}", form_url)

            result = self._mail.send_email(
                db=db,
                org_id=org_id,
                to=to_email,
                subject=subject,
                body_html=body_html,
            )

            if not result.success:
                return fail(result.message)

            if has_form_link and not receive_data_run:
                return ExecutorResponse(
                    success=True,
                    message="Email sent, form link active",
                    is_external_wait=True,
                    fire_trigger_immediately=True,
                    timeout_hours=24,
                    data=ExecutorData(
                        outcome="sent",
                        fields={},
                        meta={"to": to_email},
                    ),
                )

            return ExecutorResponse(
                success=True,
                message="Email sent successfully",
                data=ExecutorData(
                    outcome="sent",
                    fields={},
                    meta={"to": to_email},
                ),
            )
        except Exception as exc:
            logger.error(
                "send_email executor failed entity=%s error=%s", input_payload.entity_id, exc
            )
            return fail(str(exc))
