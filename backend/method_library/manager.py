"""Business orchestration for the method library.

Reads only in this pass. The rules that will govern writes are recorded here so
whoever builds them does not have to rediscover the intent:

* Name, description and category are live editable state. Editing any of them is
  an in-place update on the identity and must never create a version.
* The field list is versioned. Adding, removing or reordering a field, or
  changing a field's label, placeholder or required flag, creates a new version.

TODO: that versioning is still unconditional, matching how field settings version
today. workflow_method_pins now records which method versions a published
workflow references, so the check this was waiting on is possible: edit in place
while nothing pins the method, and start versioning once something does. Left as
a follow-up on purpose, because changing when versions are created is a behaviour
change of its own rather than part of adding the pins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.enums import ModuleStatus
from exceptions import NotFoundError, ServiceError, ValidationError
from method_library.db_models import (
    DEFAULT_PAGE_LIMIT,
    CategoryInUseError,
    DuplicateCategoryNameError,
    DuplicateMethodFieldError,
    MethodInUseError,
    UnknownMethodCategoryError,
    UnknownMethodFieldError,
    UnknownMethodFieldVersionError,
)
from method_library.models.interface import MethodWithFields
from method_library.models.response import MethodLibraryStatusResponse

if TYPE_CHECKING:
    from method_library.db_models import MethodLibraryModelService
    from method_library.models.interface import MethodCategory, MethodIdentity, MethodVersion
    from method_library.models.request import (
        MethodCategoryCreateRequest,
        MethodCategoryRenameRequest,
        MethodCloneRequest,
        MethodCreateRequest,
        MethodFieldListUpdateRequest,
        MethodFieldRepinRequest,
        MethodMetadataUpdateRequest,
    )


class MethodLibraryServiceManager:
    """Serve methods and their resolved field lists, scoped to one organization."""

    def __init__(
        self,
        method_library_db_model_service: MethodLibraryModelService,
        database_service_manager: object | None = None,
        config: object | None = None,
    ) -> None:
        self.method_library_db_model_service = method_library_db_model_service
        self.db_model_service = method_library_db_model_service
        self.database_service_manager = database_service_manager
        self.config = config
        self.module_name = "method_library"
        self._started = False

    def start(self) -> None:
        """Mark the module started. No background work to launch."""
        self._started = True

    def stop(self) -> None:
        """Mark the module stopped."""
        self._started = False

    def get_status(self) -> MethodLibraryStatusResponse:
        """Report module status in the shape every module reports."""
        return MethodLibraryStatusResponse(
            module=self.module_name,
            status=ModuleStatus.READY.value,
            started=self._started,
        )

    @staticmethod
    def _require_organization(actor: dict[str, object]) -> str:
        """Take the organization from the actor. Never from a request body."""
        organization_id = actor.get("organization_id")
        if not organization_id:
            raise ServiceError("actor is missing organization_id")
        return str(organization_id)

    def list_methods_for_actor(
        self,
        actor: dict[str, object],
        *,
        include_archived: bool = False,
        search: str | None = None,
        entity_type: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[MethodIdentity], int]:
        """A page of methods, plus the total match count across every page.

        `search` matches part of a method's name or its category name, case
        insensitively, and combines with `include_archived`. `entity_type`
        narrows the page to methods tagged for it, excluding untagged methods.
        """
        organization_id = self._require_organization(actor)
        return self.db_model_service.list_methods(
            organization_id=organization_id,
            include_archived=include_archived,
            search=search,
            entity_type=entity_type,
            limit=limit,
            offset=offset,
        )

    def list_method_versions_for_actor(
        self,
        actor: dict[str, object],
        method_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[MethodVersion], int]:
        """A page of one method's version history, newest first, plus the total.

        An id from another organization, or no organization at all, raises
        NotFoundError from the read below rather than returning an empty page that
        would read as a method with no history.
        """
        organization_id = self._require_organization(actor)
        return self.db_model_service.list_method_versions(
            organization_id=organization_id,
            method_id=method_id,
            limit=limit,
            offset=offset,
        )

    def get_method_with_fields_for_actor(
        self, actor: dict[str, object], method_id: str
    ) -> MethodWithFields:
        """One method resolved into its ordered field list.

        Resolves the method's current version, which stands in for "the pinned
        version" until workflows can pin one. Each field carries the method's own
        label, placeholder, required flag and position, merged with the type and
        settings of the Field Library version it pins, so the shape is the one the
        method was built against rather than the field's current state.
        """
        organization_id = self._require_organization(actor)
        identity = self.db_model_service.get_method(
            organization_id=organization_id, method_id=method_id
        )
        if identity is None:
            raise NotFoundError(f"method '{method_id}' was not found")
        version = self.db_model_service.get_latest_version(
            organization_id=organization_id, method_id=method_id
        )
        if version is None:
            raise ServiceError(f"method '{method_id}' has no current version")
        fields = self.db_model_service.list_version_fields(
            organization_id=organization_id, method_version_id=version.version_id
        )
        return MethodWithFields(identity=identity, version=version, fields=fields)

    def _resolved(self, organization_id: str, method_id: str) -> MethodWithFields:
        """Re-read a method after a write, so callers get one consistent shape."""
        identity = self.db_model_service.get_method(
            organization_id=organization_id, method_id=method_id
        )
        if identity is None:
            raise NotFoundError(f"method '{method_id}' was not found")
        version = self.db_model_service.get_latest_version(
            organization_id=organization_id, method_id=method_id
        )
        if version is None:
            raise ServiceError(f"method '{method_id}' has no current version")
        fields = self.db_model_service.list_version_fields(
            organization_id=organization_id, method_version_id=version.version_id
        )
        return MethodWithFields(identity=identity, version=version, fields=fields)

    def create_method_for_actor(
        self, actor: dict[str, object], request: MethodCreateRequest
    ) -> MethodWithFields:
        """Create a method with its opening field list.

        `method_code` is assigned by the database, and each field is pinned to
        its current latest Field Library version at this moment.
        """
        organization_id = self._require_organization(actor)
        try:
            identity, _version = self.db_model_service.create_method_with_fields(
                organization_id=organization_id,
                name=request.name.strip(),
                description=request.description,
                category_id=request.category_id,
                field_inputs=list(request.fields),
                created_by=str(actor.get("user_id") or "") or None,
            )
        except (
            DuplicateMethodFieldError,
            UnknownMethodFieldError,
            UnknownMethodFieldVersionError,
            UnknownMethodCategoryError,
        ) as exc:
            raise ValidationError(str(exc)) from exc
        if request.entity_types:
            self.db_model_service.replace_entity_types(
                organization_id=organization_id,
                method_id=identity.method_id,
                entity_types=request.entity_types,
                actor_id=str(actor.get("user_id") or "") or None,
            )
        return self._resolved(organization_id, identity.method_id)

    def clone_method_for_actor(
        self, actor: dict[str, object], method_id: str, request: MethodCloneRequest
    ) -> MethodWithFields:
        """Copy one version of a method into a new, independent method.

        The clone keeps the exact field versions the source version pinned, so
        cloning an old version reproduces it rather than upgrading it. An omitted
        `source_version_id` means the source's current latest version, and an
        omitted `category_id` means the source's category.
        """
        organization_id = self._require_organization(actor)
        try:
            identity, _version = self.db_model_service.clone_method(
                organization_id=organization_id,
                source_method_id=method_id,
                source_version_id=request.source_version_id,
                name=request.name.strip(),
                category_id=request.category_id,
                created_by=str(actor.get("user_id") or "") or None,
            )
        except UnknownMethodCategoryError as exc:
            raise ValidationError(str(exc)) from exc
        return self._resolved(organization_id, identity.method_id)

    def update_method_metadata_for_actor(
        self,
        actor: dict[str, object],
        method_id: str,
        request: MethodMetadataUpdateRequest,
    ) -> MethodIdentity:
        """Edit name, description or category in place. Never versions the method.

        Only the members present in the request are applied, so omitting one
        leaves it as it was rather than clearing it.
        """
        organization_id = self._require_organization(actor)
        changes = request.model_dump(exclude_unset=True)
        # Tags live in their own table, so they are pulled out before `changes`
        # is handed to the method-row update.
        entity_types = changes.pop("entity_types", None)
        if not changes and entity_types is None:
            raise ValidationError("no changes were supplied")
        if "name" in changes:
            # None first: the column is NOT NULL, and str(None) would rename the
            # method to the literal "None" instead of refusing the request.
            name = changes["name"]
            if name is None or not str(name).strip():
                raise ValidationError("method name is required")
            changes["name"] = str(name).strip()
        if entity_types is not None:
            self.db_model_service.replace_entity_types(
                organization_id=organization_id,
                method_id=method_id,
                entity_types=list(entity_types),
                actor_id=str(actor.get("user_id") or "") or None,
            )
        if changes:
            try:
                identity = self.db_model_service.update_method_metadata(
                    organization_id=organization_id, method_id=method_id, changes=changes
                )
            except UnknownMethodCategoryError as exc:
                raise ValidationError(str(exc)) from exc
            if identity is None:
                raise NotFoundError(f"method '{method_id}' was not found")
            if entity_types is None:
                return identity
        # Tags were written, and `update_method_metadata` does not carry them, so
        # the response is re-read rather than echoing the pre-write tag list.
        identity = self.db_model_service.get_method(
            organization_id=organization_id, method_id=method_id
        )
        if identity is None:
            raise NotFoundError(f"method '{method_id}' was not found")
        return identity

    def replace_method_fields_for_actor(
        self,
        actor: dict[str, object],
        method_id: str,
        request: MethodFieldListUpdateRequest,
    ) -> MethodWithFields:
        """Replace the field list, producing a new version.

        Additions, removals and reordering all arrive as the list the method
        should now have. The superseded version is kept, so anything already
        pinned to it is undisturbed.
        """
        organization_id = self._require_organization(actor)
        if self.db_model_service.get_method(
            organization_id=organization_id, method_id=method_id
        ) is None:
            raise NotFoundError(f"method '{method_id}' was not found")
        if request.connector_id and request.fields:
            raise ValidationError(
                "a method with a connector cannot also declare fields: "
                "remove the fields, or remove the connector"
            )
        try:
            self.db_model_service.replace_method_field_list(
                organization_id=organization_id,
                method_id=method_id,
                field_inputs=list(request.fields),
                connector_id=request.connector_id,
                created_by=str(actor.get("user_id") or "") or None,
            )
        except (
            DuplicateMethodFieldError,
            UnknownMethodFieldError,
            UnknownMethodFieldVersionError,
            UnknownMethodCategoryError,
        ) as exc:
            raise ValidationError(str(exc)) from exc
        return self._resolved(organization_id, method_id)

    def repin_method_field_for_actor(
        self,
        actor: dict[str, object],
        method_id: str,
        link_id: str,
        request: MethodFieldRepinRequest,
    ) -> MethodWithFields:
        """Move one field on a method to a different version of that field."""
        organization_id = self._require_organization(actor)
        if self.db_model_service.get_method(
            organization_id=organization_id, method_id=method_id
        ) is None:
            raise NotFoundError(f"method '{method_id}' was not found")
        try:
            self.db_model_service.repin_method_field(
                organization_id=organization_id,
                method_id=method_id,
                link_id=link_id,
                version_id=request.version_id,
                created_by=str(actor.get("user_id") or "") or None,
            )
        except UnknownMethodFieldVersionError as exc:
            raise ValidationError(str(exc)) from exc
        return self._resolved(organization_id, method_id)

    def create_category_for_actor(
        self, actor: dict[str, object], request: MethodCategoryCreateRequest
    ) -> MethodCategory:
        """Create a category in the actor's organization.

        A name already taken in this organization is a 400, the same way the field
        library treats a duplicate field name, rather than a 409.
        """
        organization_id = self._require_organization(actor)
        name = request.name.strip()
        if not name:
            raise ValidationError("category name is required")
        try:
            return self.db_model_service.create_category(
                organization_id=organization_id, name=name
            )
        except DuplicateCategoryNameError as exc:
            raise ValidationError(str(exc)) from exc

    def list_categories_for_actor(self, actor: dict[str, object]) -> list[MethodCategory]:
        """Every category in the actor's organization, ordered by name."""
        organization_id = self._require_organization(actor)
        return self.db_model_service.list_categories(organization_id=organization_id)

    def rename_category_for_actor(
        self,
        actor: dict[str, object],
        category_id: str,
        request: MethodCategoryRenameRequest,
    ) -> MethodCategory:
        """Rename a category in place, keeping its methods where they are."""
        organization_id = self._require_organization(actor)
        name = request.name.strip()
        if not name:
            raise ValidationError("category name is required")
        try:
            category = self.db_model_service.rename_category(
                organization_id=organization_id, category_id=category_id, name=name
            )
        except DuplicateCategoryNameError as exc:
            raise ValidationError(str(exc)) from exc
        if category is None:
            raise NotFoundError(f"category '{category_id}' was not found")
        return category

    def delete_category_for_actor(self, actor: dict[str, object], category_id: str) -> None:
        """Delete a category that no method is filed under.

        Refusing while methods still reference it is the database's own guarantee;
        it surfaces as a 400 rather than a 500.
        """
        organization_id = self._require_organization(actor)
        try:
            deleted = self.db_model_service.delete_category(
                organization_id=organization_id, category_id=category_id
            )
        except CategoryInUseError as exc:
            raise ValidationError(str(exc)) from exc
        if not deleted:
            raise NotFoundError(f"category '{category_id}' was not found")

    def delete_method_for_actor(self, actor: dict[str, object], method_id: str) -> None:
        """Hard delete a method, along with its versions and version fields.

        Refused while a published workflow state pins any of the method's
        versions, which surfaces as a 400 rather than a 500.
        """
        organization_id = self._require_organization(actor)
        try:
            deleted = self.db_model_service.delete_method(
                organization_id=organization_id, method_id=method_id
            )
        except MethodInUseError as exc:
            raise ValidationError(str(exc)) from exc
        if not deleted:
            raise NotFoundError(f"method '{method_id}' was not found")

    def archive_method_for_actor(
        self, actor: dict[str, object], method_id: str
    ) -> MethodIdentity:
        """Archive a method. Unconditional, even while a workflow uses it."""
        organization_id = self._require_organization(actor)
        identity = self.db_model_service.archive_method(
            organization_id=organization_id, method_id=method_id
        )
        if identity is None:
            raise NotFoundError(f"method '{method_id}' was not found")
        return identity

    def unarchive_method_for_actor(
        self, actor: dict[str, object], method_id: str
    ) -> MethodIdentity:
        """Reverse an archive, making the method appear in default listings again."""
        organization_id = self._require_organization(actor)
        identity = self.db_model_service.unarchive_method(
            organization_id=organization_id, method_id=method_id
        )
        if identity is None:
            raise NotFoundError(f"method '{method_id}' was not found")
        return identity
