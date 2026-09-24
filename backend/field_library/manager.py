"""Business orchestration for the field library.

Resolves an organization's selectable field types, and owns the create, read
and archive rules for fields.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.enums import ModuleStatus
from exceptions import NotFoundError, ServiceError, ValidationError
from field_library.db_models import (
    DEFAULT_PAGE_LIMIT,
    DuplicateFieldError,
    DuplicateFormFieldLinkError,
    FieldInUseError,
    FormFieldLinkModelService,
)
from field_library.models.interface import FieldWithVersion, FormFieldPlacement
from field_library.models.response import (
    FieldLibraryStatusResponse,
    FieldTypeCatalogueResponse,
    FieldTypeOption,
)

if TYPE_CHECKING:
    from field_library.db_models import FieldLibraryModelService
    from field_library.models.interface import (
        FieldIdentity,
        FieldTypeCatalogueEntry,
        FieldVersion,
        FormFieldLink,
    )
    from field_library.models.request import (
        FieldCreateRequest,
        FieldDescriptionUpdateRequest,
        FieldRenameRequest,
        FieldVersionCreateRequest,
        FormFieldLinkCreateRequest,
        FormFieldLinkRepinRequest,
    )

# Shown against catalogue entries the engine cannot store yet.
NOT_BUILT_REASON = "This field type is not available in this release yet."
# Shown against entries this organization has explicitly switched off.
NOT_ENABLED_REASON = "This field type is not enabled for your organization."
# Boundary for singular vs plural in the in-use message.
SINGLE_REFERENCE = 1


class FieldLibraryServiceManager:
    """Serve the field-type catalogue, scoped to one organization."""

    def __init__(
        self,
        field_library_db_model_service: FieldLibraryModelService,
        database_service_manager: object | None = None,
        config: object | None = None,
        form_field_link_db_model_service: FormFieldLinkModelService | None = None,
    ) -> None:
        self.field_library_db_model_service = field_library_db_model_service
        self.db_model_service = field_library_db_model_service
        # Optional so every existing construction site keeps working; the
        # link endpoints are the only thing that needs it.
        self.form_field_link_db_model_service = form_field_link_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.module_name = "field_library"
        self._started = False

    def start(self) -> None:
        """Mark the module started. No background work to launch."""
        self._started = True

    def stop(self) -> None:
        """Mark the module stopped."""
        self._started = False

    def get_status(self) -> FieldLibraryStatusResponse:
        """Report module status in the shape every module reports."""
        return FieldLibraryStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    @staticmethod
    def _to_option(
        entry: FieldTypeCatalogueEntry, *, enabled_for_org: bool
    ) -> FieldTypeOption:
        """Fold engine availability and org enablement into one flag.

        Availability wins: an unbuilt type is never selectable.
        """
        if not entry.is_available:
            return FieldTypeOption(
                code=entry.code,
                label=entry.label,
                engine_type=entry.engine_type,
                config_kind=entry.config_kind,
                selectable=False,
                unavailable_reason=NOT_BUILT_REASON,
            )
        return FieldTypeOption(
            code=entry.code,
            label=entry.label,
            engine_type=entry.engine_type,
            config_kind=entry.config_kind,
            selectable=enabled_for_org,
            unavailable_reason=None if enabled_for_org else NOT_ENABLED_REASON,
        )

    def list_field_types(self, *, organization_id: str) -> FieldTypeCatalogueResponse:
        """Every catalogue entry, marked selectable for this organization.

        No enablement rows means every available type, which keeps pre-existing
        organizations unchanged. Any row opts into explicit control.
        """
        if not organization_id:
            raise ServiceError("organization_id is required to list field types")
        try:
            catalogue = self.db_model_service.list_catalogue()
            settings = self.db_model_service.list_organization_settings(
                organization_id=organization_id
            )
            if settings:
                enabled_codes = {
                    setting.field_type_code for setting in settings if setting.enabled
                }
                items = [
                    self._to_option(entry, enabled_for_org=entry.code in enabled_codes)
                    for entry in catalogue
                ]
            else:
                items = [self._to_option(entry, enabled_for_org=True) for entry in catalogue]
            return FieldTypeCatalogueResponse(organization_id=organization_id, items=items)
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(f"Unable to list field types: {exc}") from exc

    # ── Field library: create, read, rename, version, archive ──────────────────────────────────

    @staticmethod
    def _require_organization(actor: dict[str, object]) -> str:
        """Take the organization from the actor. Never from a request body."""
        organization_id = actor.get("organization_id")
        if not organization_id:
            raise ServiceError("actor is missing organization_id")
        return str(organization_id)

    def _assert_type_is_selectable(self, *, organization_id: str, field_type: str) -> None:
        """Reject an unsupported type or one the organization has switched off."""
        catalogue = self.list_field_types(organization_id=organization_id)
        match = next((item for item in catalogue.items if item.code == field_type), None)
        if match is None:
            raise ValidationError(f"unknown field type '{field_type}'")
        # Timer values are recorded by the frontend and persisted through the
        # normal entity-field path.  Accept the type even when an older
        # catalogue row still carries the legacy "not built" availability
        # flag.  Organization-level disablement remains enforced below.
        if field_type == "timer_duration" and match.unavailable_reason == NOT_BUILT_REASON:
            return
        if not match.selectable:
            raise ValidationError(
                f"field type '{field_type}' is not available: {match.unavailable_reason}"
            )

    def create_field_for_actor(
        self, actor: dict[str, object], request: FieldCreateRequest
    ) -> FieldWithVersion:
        """Create a field and its version 1.

        Key and type are settable only here; later edits add versions instead.
        """
        organization_id = self._require_organization(actor)
        name = (request.name or "").strip()
        field_key = (request.field_key or "").strip()
        if not name:
            raise ValidationError("field name is required")
        if not field_key:
            raise ValidationError("field key is required")
        self._assert_type_is_selectable(
            organization_id=organization_id, field_type=request.field_type
        )
        try:
            return self.db_model_service.create_field(
                organization_id=organization_id,
                name=name,
                field_key=field_key,
                field_type=request.field_type,
                description=request.description,
                settings=request.settings,
                created_by=str(actor.get("user_id") or "") or None,
            )
        except DuplicateFieldError as exc:
            raise ValidationError(str(exc)) from exc

    def list_fields_for_actor(
        self,
        actor: dict[str, object],
        *,
        include_archived: bool = False,
        search: str | None = None,
        field_type: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[FieldWithVersion], int]:
        """A page of fields with their current version, plus the total match count.

        Filters combine with each other and with `include_archived`; omitted, the
        result is unfiltered. Archived fields are excluded by default, which is
        why a field that `get` still returns can be absent from this list.
        """
        organization_id = self._require_organization(actor)
        return self.db_model_service.list_fields(
            organization_id=organization_id,
            include_archived=include_archived,
            search=search,
            field_type=field_type,
            limit=limit,
            offset=offset,
        )

    def _require_field(self, *, organization_id: str, library_field_id: str) -> FieldIdentity:
        """Load a field or fail. Scoped to the organization, so another org's id
        reads as missing rather than leaking that it exists."""
        identity = self.db_model_service.get_field(
            organization_id=organization_id, library_field_id=library_field_id
        )
        if identity is None:
            raise NotFoundError(f"library field '{library_field_id}' was not found")
        return identity

    def get_field_for_actor(
        self, actor: dict[str, object], library_field_id: str
    ) -> FieldWithVersion:
        """One field with its current version."""
        organization_id = self._require_organization(actor)
        identity = self._require_field(
            organization_id=organization_id, library_field_id=library_field_id
        )
        version = self.db_model_service.get_latest_version(
            organization_id=organization_id, library_field_id=library_field_id
        )
        if version is None:
            raise ServiceError(f"library field '{library_field_id}' has no current version")
        return FieldWithVersion(identity=identity, version=version)

    def list_versions_for_actor(
        self, actor: dict[str, object], library_field_id: str
    ) -> list[FieldVersion]:
        """Every version of one field, so a form can pick which to pin to."""
        organization_id = self._require_organization(actor)
        self._require_field(organization_id=organization_id, library_field_id=library_field_id)
        return self.db_model_service.list_versions(
            organization_id=organization_id, library_field_id=library_field_id
        )

    def rename_field_for_actor(
        self, actor: dict[str, object], library_field_id: str, request: FieldRenameRequest
    ) -> FieldIdentity:
        """Rename a field without creating a version.

        The name is a display label shared by every version, so nothing linked to
        a version is affected and no stored data moves.
        """
        organization_id = self._require_organization(actor)
        name = (request.name or "").strip()
        if not name:
            raise ValidationError("field name is required")
        self._require_field(organization_id=organization_id, library_field_id=library_field_id)
        try:
            identity = self.db_model_service.rename_field(
                organization_id=organization_id,
                library_field_id=library_field_id,
                name=name,
            )
        except DuplicateFieldError as exc:
            raise ValidationError(str(exc)) from exc
        if identity is None:
            raise NotFoundError(f"library field '{library_field_id}' was not found")
        return identity

    def update_description_for_actor(
        self,
        actor: dict[str, object],
        library_field_id: str,
        request: FieldDescriptionUpdateRequest,
    ) -> FieldVersion:
        """Edit the current version's description without creating a version.

        The counterpart to rename: a wording fix should not spawn a version and
        should not disturb anything pinned to an existing one. Real content
        changes still go through create_version_for_actor.
        """
        organization_id = self._require_organization(actor)
        self._require_field(organization_id=organization_id, library_field_id=library_field_id)
        version = self.db_model_service.update_latest_description(
            organization_id=organization_id,
            library_field_id=library_field_id,
            description=request.description,
        )
        if version is None:
            raise ServiceError(f"library field '{library_field_id}' has no current version")
        return version

    def create_version_for_actor(
        self,
        actor: dict[str, object],
        library_field_id: str,
        request: FieldVersionCreateRequest,
    ) -> FieldVersion:
        """Create the next version. Existing links stay on the version they chose.

        A `field_type` in the request is validated the same way creation validates
        it, so an unbuilt or organization-disabled type is refused with the same
        message. Omitted, the type carries on unchanged.

        Description behaves the same way, but needs `model_fields_set` to get
        there: the field is nullable, so a missing key and an explicit null both
        arrive as None. Omitted, the current description carries forward; sent as
        null, it is cleared, because that is a deliberate instruction.
        """
        organization_id = self._require_organization(actor)
        identity = self._require_field(
            organization_id=organization_id, library_field_id=library_field_id
        )
        if identity.is_archived:
            raise ValidationError("an archived field cannot take a new version")
        requested_type = request.field_type
        if requested_type and requested_type != identity.field_type:
            self._assert_type_is_selectable(
                organization_id=organization_id, field_type=requested_type
            )
        else:
            requested_type = None
        description = self._carried_description(
            organization_id=organization_id, library_field_id=library_field_id, request=request
        )
        try:
            return self.db_model_service.add_version(
                organization_id=organization_id,
                library_field_id=library_field_id,
                description=description,
                settings=request.settings,
                created_by=str(actor.get("user_id") or "") or None,
                field_type=requested_type,
            )
        except DuplicateFieldError as exc:
            raise ValidationError(str(exc)) from exc

    def _carried_description(
        self,
        *,
        organization_id: str,
        library_field_id: str,
        request: FieldVersionCreateRequest,
    ) -> str | None:
        """The description the new version should carry.

        Whatever the caller sent when they sent the key at all, including null.
        Otherwise the current version's description, so a settings-only or
        type-only bump does not quietly blank the wording.
        """
        if "description" in request.model_fields_set:
            return request.description
        current = self.db_model_service.get_latest_version(
            organization_id=organization_id, library_field_id=library_field_id
        )
        return current.description if current is not None else None

    def hard_delete_field_for_actor(
        self, actor: dict[str, object], library_field_id: str
    ) -> None:
        """Delete a field outright, but only when nothing references it.

        Distinct from archiving, which is always allowed. A field a form still
        uses must not vanish underneath it, so this refuses and says how many
        forms are involved. The database enforces the same rule independently.
        """
        organization_id = self._require_organization(actor)
        self._require_field(organization_id=organization_id, library_field_id=library_field_id)
        in_use = self.db_model_service.count_referencing_forms(
            organization_id=organization_id, library_field_id=library_field_id
        )
        if in_use:
            form_word = "form" if in_use == SINGLE_REFERENCE else "forms"
            raise ValidationError(
                f"this field is used by {in_use} {form_word} and cannot be deleted. "
                "Archive it instead to retire it without breaking those forms."
            )
        try:
            deleted = self.db_model_service.hard_delete_field(
                organization_id=organization_id, library_field_id=library_field_id
            )
        except FieldInUseError as exc:
            raise ValidationError(str(exc)) from exc
        if not deleted:
            raise NotFoundError(f"library field '{library_field_id}' was not found")

    def archive_field_for_actor(
        self, actor: dict[str, object], library_field_id: str
    ) -> FieldIdentity:
        """Archive a field by stamping its row, freeing its name and key for
        reuse. Nothing is deleted, so existing references keep resolving."""
        organization_id = self._require_organization(actor)
        self._require_field(organization_id=organization_id, library_field_id=library_field_id)
        identity = self.db_model_service.archive_field(
            organization_id=organization_id, library_field_id=library_field_id
        )
        if identity is None:
            raise NotFoundError(f"library field '{library_field_id}' was not found")
        return identity

    def list_field_types_for_actor(self, actor: dict[str, object]) -> FieldTypeCatalogueResponse:
        """Serve the catalogue for the actor's organization, which is taken from
        the actor and never from the request."""
        organization_id = actor.get("organization_id")
        if not organization_id:
            raise ServiceError("actor is missing organization_id")
        return self.list_field_types(organization_id=str(organization_id))

    # ── Form field links ──────────────────────────────────────────────────────

    def _link_service(self) -> FormFieldLinkModelService:
        """The link persistence service, or a clear error when it was not wired."""
        if self.form_field_link_db_model_service is None:
            raise ServiceError("form field links are not available: no link service configured")
        return self.form_field_link_db_model_service

    def _require_form(self, organization_id: str, schema_id: str) -> None:
        """Refuse a form that is not this organization's own."""
        if not self._link_service().form_exists(
            organization_id=organization_id, schema_id=schema_id
        ):
            raise NotFoundError(f"form '{schema_id}' was not found")

    def _resolve_link_version(
        self, organization_id: str, library_field_id: str, version_id: str | None
    ) -> str:
        """The version a new link should pin.

        Omitted means the field's current version, read once, now. A supplied one
        is checked against this field rather than trusted, so a version of some
        other field cannot be pinned to it.
        """
        identity = self.db_model_service.get_field(
            organization_id=organization_id, library_field_id=library_field_id
        )
        if identity is None:
            raise NotFoundError(f"field '{library_field_id}' was not found")
        if version_id is None:
            current = self.db_model_service.get_latest_version(
                organization_id=organization_id, library_field_id=library_field_id
            )
            if current is None:
                raise ValidationError(f"field '{library_field_id}' has no current version")
            return current.version_id
        if not self._link_service().version_belongs_to_field(
            organization_id=organization_id,
            library_field_id=library_field_id,
            version_id=version_id,
        ):
            raise ValidationError(
                f"version '{version_id}' does not belong to field '{library_field_id}'"
            )
        return version_id

    def _placement(self, organization_id: str, link: FormFieldLink) -> FormFieldPlacement:
        """A link resolved into the field and version it points at."""
        identity = self.db_model_service.get_field(
            organization_id=organization_id, library_field_id=link.library_field_id
        )
        if identity is None:
            raise ServiceError(f"link '{link.id}' points at a field that no longer exists")
        version = self.db_model_service.get_version(
            organization_id=organization_id, version_id=link.version_id
        )
        if version is None:
            raise ServiceError(f"link '{link.id}' points at a version that no longer exists")
        return FormFieldPlacement(link=link, identity=identity, version=version)

    def create_link_for_actor(
        self, actor: dict[str, object], request: FormFieldLinkCreateRequest
    ) -> FormFieldPlacement:
        """Put a field on a form, pinned to one of its versions."""
        organization_id = self._require_organization(actor)
        self._require_form(organization_id, request.schema_id)
        version_id = self._resolve_link_version(
            organization_id, request.library_field_id, request.version_id
        )
        try:
            link = self._link_service().create_link(
                organization_id=organization_id,
                schema_id=request.schema_id,
                library_field_id=request.library_field_id,
                version_id=version_id,
                position=request.position,
            )
        except DuplicateFormFieldLinkError as exc:
            raise ValidationError(str(exc)) from exc
        return self._placement(organization_id, link)

    def list_links_for_actor(
        self, actor: dict[str, object], schema_id: str
    ) -> list[FormFieldPlacement]:
        """Every field one form uses, in position order, each with its version."""
        organization_id = self._require_organization(actor)
        self._require_form(organization_id, schema_id)
        return [
            self._placement(organization_id, link)
            for link in self._link_service().list_links(
                organization_id=organization_id, schema_id=schema_id
            )
        ]

    def repin_link_for_actor(
        self, actor: dict[str, object], link_id: str, request: FormFieldLinkRepinRequest
    ) -> FormFieldPlacement:
        """Move a link to a different version of the field it already carries."""
        organization_id = self._require_organization(actor)
        existing = self._link_service().get_link(
            organization_id=organization_id, link_id=link_id
        )
        if existing is None:
            raise NotFoundError(f"form field link '{link_id}' was not found")
        if not self._link_service().version_belongs_to_field(
            organization_id=organization_id,
            library_field_id=existing.library_field_id,
            version_id=request.version_id,
        ):
            raise ValidationError(
                f"version '{request.version_id}' does not belong to field "
                f"'{existing.library_field_id}'"
            )
        link = self._link_service().repin_link(
            organization_id=organization_id, link_id=link_id, version_id=request.version_id
        )
        if link is None:
            raise NotFoundError(f"form field link '{link_id}' was not found")
        return self._placement(organization_id, link)

    def delete_link_for_actor(self, actor: dict[str, object], link_id: str) -> None:
        """Take a field off a form. The field and its versions are untouched."""
        organization_id = self._require_organization(actor)
        if not self._link_service().delete_link(
            organization_id=organization_id, link_id=link_id
        ):
            raise NotFoundError(f"form field link '{link_id}' was not found")
