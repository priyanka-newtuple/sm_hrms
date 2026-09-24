"""Source-permission resolution for inherited fields on entity records — see design_docs/tony_inherited_field_source_permission_resolution_notes.md."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from common.logger import logger
from common.protocols import MASKED_FIELD_VALUE, record_satisfies_any_condition
from entities.models.interface import local_field_name, parent_id_field_name
from exceptions import AuthorizationError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from common.protocols import EntityReadPolicy
    from entities.manager import EntitiesServiceManager
    from entities.models.interface import EntityRecord
    from entities.models.response import EntityRecordResponse


@dataclass(frozen=True)
class InheritedFieldSource:
    """Where one inherited (target) field's real permission decision must be checked."""

    source_entity_type_id: str
    source_field_name: str
    # Extra (source type id, source field name) pairs the SAME target field is
    # inherited from, because two active workflows on this entity type pin it
    # from different sources. Normally empty. A type-level lookup cannot know
    # which workflow a given record is enrolled in, so rather than gating
    # against an arbitrary one of them, the field is gated against every one
    # and the most restrictive answer wins.
    alternate_sources: tuple[tuple[str, str], ...] = ()

    def all_sources(self) -> tuple[tuple[str, str], ...]:
        """Every (type id, field name) this target field may really come from."""
        return (
            (self.source_entity_type_id, self.source_field_name),
            *self.alternate_sources,
        )


class InheritedFieldPermissionsService:
    """Resolves inherited-field visibility against the real source entity type, not the target's synthetic copy of it."""

    def __init__(self, manager: EntitiesServiceManager) -> None:
        self.manager = manager
        self.db = manager.db_model_service

    def get_field_sources(
        self, organization_id: str, entity_type_id: str
    ) -> dict[str, InheritedFieldSource]:
        """Map each field on this (target) entity type that is inherited via a relation
        declaration to its real source entity type and source field name.

        Metadata-only — reads `entity_type_relations.relation_metadata`, never touches
        an actual entity record. Used by both the per-record (`apply`) and page-batched
        (`apply_from_policies`) resolution paths.
        """
        declarations = self.db.get_active_relation_declarations_by_to_type(
            organization_id=organization_id, to_entity_type_id=entity_type_id
        )
        sources: dict[str, InheritedFieldSource] = {}
        for declaration in declarations:
            for source_key, target_key in dict(declaration.relation_metadata or {}).items():
                if not isinstance(source_key, str) or not isinstance(target_key, str):
                    continue
                sources[local_field_name(target_key)] = InheritedFieldSource(
                    source_entity_type_id=declaration.from_entity_type_id,
                    source_field_name=local_field_name(source_key),
                )
        self._add_pinned_sources(sources, organization_id=organization_id, entity_type_id=entity_type_id)
        return sources

    def _add_pinned_sources(
        self,
        sources: dict[str, InheritedFieldSource],
        *,
        organization_id: str,
        entity_type_id: str,
        pinned_by_type: dict[str, dict[str, tuple[str, str]]] | None = None,
    ) -> None:
        """Merge in fields inherited at the METHOD BLOCK level.

        These live on the published workflow's entity_schema (ownership=
        'inherited' + source), never in relation_metadata, so the loop above
        cannot see them. Without this they would be neither requested from the
        resolver nor gated against the actor's access to the real source type
        — the second half is the one that matters: a per-block client_name
        must be masked exactly as a metadata-mapped client_name is.

        `setdefault`: a relation_metadata mapping for the same target field
        stays authoritative, so nothing already resolving changes.

        A field pinned from more than one source (two active workflows on this
        type disagreeing) carries the extras in `alternate_sources` and is
        gated against all of them — see `InheritedFieldSource`.
        """
        if pinned_by_type is None:
            pinned_by_type = self.db.pinned_inherited_sources_by_type(
                organization_id=organization_id, entity_type_ids={entity_type_id}
            )
        for field, pinned in pinned_by_type.get(entity_type_id, {}).items():
            if not pinned:
                continue
            (source_type_id, source_field), *alternates = pinned
            sources.setdefault(
                field,
                InheritedFieldSource(
                    source_entity_type_id=source_type_id,
                    source_field_name=source_field,
                    alternate_sources=tuple(alternates),
                ),
            )

    def apply(
        self,
        db: Session,
        user_id: str,
        organization_id: str,
        data: dict[str, object],
        field_sources: dict[str, InheritedFieldSource],
    ) -> dict[str, object]:
        """Keep, mask, or drop every inherited field in `data` based on its real source
        field's permission — never the target entity type's own (synthetic) field-permission
        row for that field name.

        Caller must already have ruled out the roles_manager-None / system-actor bypass
        (same precondition as `_apply_field_permissions`, which is the only current caller).
        """
        if not field_sources:
            return data
        roles_manager = self.manager.roles_manager
        result = dict(data)
        source_type_names: dict[str, str | None] = {}

        for field_name, source in field_sources.items():
            if field_name not in result:
                continue
            drop = False
            mask = False
            # Every source this field may really come from must clear the gate.
            # Normally there is exactly one; see `InheritedFieldSource`.
            for source_type_id, source_field_name in source.all_sources():
                if source_type_id not in source_type_names:
                    source_type_names[source_type_id] = self.db.get_entity_type_name_by_id(
                        organization_id=organization_id, entity_type_id=source_type_id, db=db
                    )
                source_type_name = source_type_names.get(source_type_id)
                if not source_type_name:
                    logger.warning(
                        "inherited field's source entity type no longer exists — dropping field",
                        extra={"field_name": field_name, "source_entity_type_id": source_type_id},
                    )
                    drop = True
                    break
                access = roles_manager.evaluate_entity_access(
                    db, user_id, organization_id, source_type_name, "view"
                )
                if not access.allowed:
                    drop = True
                    break
                visible = roles_manager.get_visible_fields(
                    db, user_id, organization_id, source_type_name
                )
                if visible is not None and source_field_name not in visible:
                    drop = True
                    break
                masked = roles_manager.get_masked_fields(
                    db, user_id, organization_id, source_type_name
                )
                if source_field_name in masked:
                    mask = True
            if drop:
                del result[field_name]
            elif mask:
                result[field_name] = MASKED_FIELD_VALUE
        return result

    def apply_from_policies(
        self,
        data: dict[str, object],
        field_sources: dict[str, InheritedFieldSource],
        policies_by_source_type_id: dict[str, EntityReadPolicy],
    ) -> dict[str, object]:
        """Same decision as `apply`, but sourced entirely from an already-resolved
        per-page policy dict — no database calls at all.

        Used by the summary/list-browser endpoint, which batches one `EntityReadPolicy`
        per distinct entity type for the whole page (see
        `list_entity_record_summaries_for_actor`) rather than resolving permissions per
        record. A source type missing from `policies_by_source_type_id` means the actor
        has no `view` access to it at all (`resolve_entity_read_policies` only includes
        types the actor can access) — dropped, same as `apply`'s entity-access gate.
        """
        if not field_sources:
            return data
        result = dict(data)
        for field_name, source in field_sources.items():
            if field_name not in result:
                continue
            drop = False
            mask = False
            # Every source must clear the gate — same rule as `apply`.
            for source_type_id, source_field_name in source.all_sources():
                policy = policies_by_source_type_id.get(source_type_id)
                if policy is None:
                    drop = True
                    break
                if (
                    policy.visible_fields is not None
                    and source_field_name not in policy.visible_fields
                ):
                    drop = True
                    break
                if source_field_name in policy.masked_fields:
                    mask = True
            if drop:
                del result[field_name]
            elif mask:
                result[field_name] = MASKED_FIELD_VALUE
        return result

    def get_field_sources_for_types(
        self, organization_id: str, entity_type_ids: set[str]
    ) -> dict[str, dict[str, InheritedFieldSource]]:
        """Batched sibling of `get_field_sources` — one query for every target entity
        type in `entity_type_ids` at once, grouped by `to_entity_type_id`. Used by
        `resolve_records_for_actor` so a page/batch with several distinct target types still
        costs one query, not one per type."""
        if not entity_type_ids:
            return {}
        declarations = self.db.get_active_relation_declarations_by_to_types(
            organization_id=organization_id, to_entity_type_ids=entity_type_ids
        )
        sources_by_type: dict[str, dict[str, InheritedFieldSource]] = {}
        for declaration in declarations:
            target_map = sources_by_type.setdefault(declaration.to_entity_type_id, {})
            for source_key, target_key in dict(declaration.relation_metadata or {}).items():
                if not isinstance(source_key, str) or not isinstance(target_key, str):
                    continue
                target_map[local_field_name(target_key)] = InheritedFieldSource(
                    source_entity_type_id=declaration.from_entity_type_id,
                    source_field_name=local_field_name(source_key),
                )
        # One query for every type in the batch, then merged per type.
        pinned_by_type = self.db.pinned_inherited_sources_by_type(
            organization_id=organization_id, entity_type_ids=entity_type_ids
        )
        for type_id in entity_type_ids:
            self._add_pinned_sources(
                sources_by_type.setdefault(type_id, {}),
                organization_id=organization_id,
                entity_type_id=type_id,
                pinned_by_type=pinned_by_type,
            )
        return sources_by_type

    def resolve_records_for_actor(
        self,
        actor: dict[str, object],
        organization_id: str,
        records: list[EntityRecord],
        *,
        enforce_condition: bool,
        raise_on_denied_target: bool = False,
        known_target_type_ids: set[str] | None = None,
    ) -> list[EntityRecordResponse]:
        """Resolve inherited values + apply RBAC for one or many records of one or more
        entity types — the one shared core behind every actor-gated entity-record
        endpoint (list, get-one, create, update, assignee, archive, restore). Fixed,
        small number of DB calls regardless of how many records are passed.

        `enforce_condition=False` skips the row-condition gate (Gate 4) — for a write
        formatting its own response, which must never be hidden by a read-only row
        condition. `raise_on_denied_target=True` raises immediately if any record's own
        entity type has no `view` access at all, instead of silently excluding those
        records — list needs this (today's guard_write pre-check behavior);
        single-record callers get the same outcome for free from their own empty-result
        check, so they leave this `False`.

        `known_target_type_ids` (optional): the entity type(s) the caller is actually
        asking about, independent of `records`. List must pass this — otherwise, when
        the fetch legitimately returns zero rows (nothing exists yet for that type), this
        function would have no way to know which type to check `raise_on_denied_target`
        against, and a denied actor would silently get an empty 200 instead of a 403 —
        inconsistent with (and a real regression from) the pre-redesign behavior, where
        the entity-level check ran unconditionally, before the fetch, every time. Falls
        back to whatever's present in `records` if not given, so single-record callers
        (which always have a real record already) don't need to pass this at all."""
        manager = self.manager
        target_type_ids = set(known_target_type_ids or ()) | {
            record.entity_type_id for record in records
        }
        if not target_type_ids:
            return []
        field_sources_by_type = self.get_field_sources_for_types(organization_id, target_type_ids)
        source_type_ids = {
            source_type_id
            for sources in field_sources_by_type.values()
            for source in sources.values()
            for source_type_id, _ in source.all_sources()
        }

        type_names_by_id: dict[str, str] = {}
        for type_id in target_type_ids | source_type_ids:
            name = self.db.get_entity_type_name_by_id(
                organization_id=organization_id, entity_type_id=type_id
            )
            if name:
                type_names_by_id[type_id] = name
            else:
                logger.warning(
                    "entity type referenced by resolve_records_for_actor no longer exists",
                    extra={"organization_id": organization_id, "entity_type_id": type_id},
                )

        policies = manager.resolve_read_policies(actor, organization_id, type_names_by_id)

        denied_target_type_ids = target_type_ids - policies.keys()
        if raise_on_denied_target and denied_target_type_ids:
            logger.warning(
                "actor denied view access to entity type(s) requested",
                extra={
                    "organization_id": organization_id,
                    "denied_entity_type_ids": sorted(denied_target_type_ids),
                },
            )
            raise AuthorizationError("You do not have permission to view this record.")

        if not records:
            return []

        field_names: set[str] = {
            name
            for policy in policies.values()
            for condition in policy.conditions
            for name in condition.field_names
        }
        for sources in field_sources_by_type.values():
            field_names.update(sources.keys())
        for source_type_id in source_type_ids:
            source_type_name = type_names_by_id.get(source_type_id)
            if source_type_name:
                field_names.add(parent_id_field_name(source_type_name))

        inherited_values = self.db.resolve_inherited_fields_for_records(
            organization_id=organization_id, records=records, field_names=field_names
        )

        results: list[EntityRecordResponse] = []
        for record in records:
            policy = policies.get(record.entity_type_id)
            if policy is None:
                continue
            combined = {**dict(record.data or {}), **inherited_values.get(record.entity_id, {})}
            # Gate 4 must run on the raw merged data before field masking strips anything (e.g. eye_nurse's condition on inherited doctor_department must see the real value).
            if enforce_condition and not record_satisfies_any_condition(
                policy.conditions, combined, entity_id=record.entity_id
            ):
                continue
            field_sources = field_sources_by_type.get(record.entity_type_id)
            if field_sources:
                combined = self.apply_from_policies(combined, field_sources, policies)
            projected = manager.apply_read_policy_to_data(
                policy,
                entity_id=record.entity_id,
                data=combined,
                projected_fields=None,
                exclude_from_target_check=field_sources.keys() if field_sources else None,
                enforce_condition=False,  # already checked above, against the pre-masking data
            )
            if projected is None:
                continue
            response = manager._entity_record_response(record)
            response.data = projected
            results.append(response)
        return results
