"""Work Order lifecycle state machine, completion guards, and audit diff builder."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from src.core.exceptions import (
    DomainValidationError,
    ErrorDetailItem,
    InvalidStateTransitionError,
)
from src.modules.work_orders.models import WorkOrderStatus

ALLOWED_WORK_ORDER_TRANSITIONS: dict[WorkOrderStatus, frozenset[WorkOrderStatus]] = {
    WorkOrderStatus.PENDING: frozenset({WorkOrderStatus.SCHEDULED, WorkOrderStatus.IN_FIELD}),
    WorkOrderStatus.SCHEDULED: frozenset({WorkOrderStatus.IN_FIELD}),
    WorkOrderStatus.IN_FIELD: frozenset({WorkOrderStatus.COMPLETED}),
    WorkOrderStatus.COMPLETED: frozenset(),
}


@dataclass(frozen=True)
class RequiredHardwareSerialSpec:
    """Specification of required serial count for a serialize-mandatory catalog item."""

    catalog_item_id: UUID
    sku: str
    name_pt_br: str
    required_quantity: int


@dataclass(frozen=True)
class WorkOrderStateTransitionDiff:
    """Structured state diff payload persisted in audit_logs for WorkOrder transitions."""

    previous_status: WorkOrderStatus
    new_status: WorkOrderStatus
    previous_state: dict[str, object]
    new_state: dict[str, object]


class WorkOrderStateMachine:
    """Pure domain state machine enforcing WorkOrder transitions and field completion guards."""

    @staticmethod
    def can_transition(current: WorkOrderStatus, target: WorkOrderStatus) -> bool:
        """Return True if transitioning from current to target is permitted."""
        return target in ALLOWED_WORK_ORDER_TRANSITIONS.get(current, frozenset())

    @classmethod
    def validate_transition(cls, current: WorkOrderStatus, target: WorkOrderStatus) -> None:
        """Raise InvalidStateTransitionError (HTTP 422) if current -> target is illegal."""
        if not cls.can_transition(current, target):
            allowed = sorted(
                s.value for s in ALLOWED_WORK_ORDER_TRANSITIONS.get(current, frozenset())
            )
            allowed_str = ", ".join(allowed) if allowed else "none (terminal state)"
            raise InvalidStateTransitionError(
                detail=(
                    f"Cannot transition WorkOrder from '{current.value}' to '{target.value}'. "
                    f"Allowed target states from '{current.value}': {allowed_str}."
                ),
                errors=[
                    {
                        "entity_type": "WORK_ORDER",
                        "current_status": current.value,
                        "target_status": target.value,
                        "allowed_targets": allowed_str,
                    }
                ],
            )

    @staticmethod
    def build_audit_diff(
        previous_status: WorkOrderStatus,
        new_status: WorkOrderStatus,
        *,
        previous_extra: dict[str, object] | None = None,
        new_extra: dict[str, object] | None = None,
    ) -> WorkOrderStateTransitionDiff:
        """Construct a structured previous_state and new_state snapshot for audit_logs."""
        prev_dict: dict[str, object] = {"status": previous_status.value}
        if previous_extra:
            prev_dict.update(previous_extra)

        new_dict: dict[str, object] = {"status": new_status.value}
        if new_extra:
            new_dict.update(new_extra)

        return WorkOrderStateTransitionDiff(
            previous_status=previous_status,
            new_status=new_status,
            previous_state=prev_dict,
            new_state=new_dict,
        )

    @classmethod
    def transition_to_scheduled(
        cls,
        current: WorkOrderStatus,
        *,
        assigned_technician_id: UUID | None = None,
    ) -> WorkOrderStateTransitionDiff:
        """Validate PENDING -> SCHEDULED transition."""
        cls.validate_transition(current, WorkOrderStatus.SCHEDULED)
        new_extra: dict[str, object] = {}
        if assigned_technician_id is not None:
            new_extra["assigned_technician_id"] = str(assigned_technician_id)
        return cls.build_audit_diff(
            current,
            WorkOrderStatus.SCHEDULED,
            new_extra=new_extra,
        )

    @classmethod
    def transition_to_in_field(
        cls,
        current: WorkOrderStatus,
        *,
        assigned_technician_id: UUID | None = None,
    ) -> WorkOrderStateTransitionDiff:
        """Validate PENDING/SCHEDULED -> IN_FIELD transition when technician starts work."""
        cls.validate_transition(current, WorkOrderStatus.IN_FIELD)
        new_extra: dict[str, object] = {}
        if assigned_technician_id is not None:
            new_extra["assigned_technician_id"] = str(assigned_technician_id)
        return cls.build_audit_diff(
            current,
            WorkOrderStatus.IN_FIELD,
            new_extra=new_extra,
        )

    @staticmethod
    def validate_completion_guards(
        *,
        checklist_json: Sequence[Mapping[str, object]],
        installation_photos_keys: Sequence[str],
        required_serial_specs: Sequence[RequiredHardwareSerialSpec],
        registered_serial_counts: Mapping[UUID, int],
    ) -> None:
        """Enforce all 3 mandatory field guards before a WorkOrder can be marked COMPLETED."""
        # Guard 1: Every checklist item must be checked
        if not checklist_json:
            raise DomainValidationError(
                detail="Cannot complete WorkOrder because the installation checklist is empty.",
                errors=[
                    {
                        "guard": "checklist_complete",
                        "reason": "empty_checklist",
                    }
                ],
            )

        unchecked_steps: list[ErrorDetailItem] = []
        for item in checklist_json:
            is_checked = bool(item.get("is_checked", False))
            if not is_checked:
                step_id = str(item.get("step_id", "unknown"))
                label = str(item.get("label_pt_br", ""))
                unchecked_steps.append(
                    {
                        "guard": "checklist_complete",
                        "step_id": step_id,
                        "label_pt_br": label,
                        "reason": "unchecked_checklist_step",
                    }
                )

        if unchecked_steps:
            missing_ids = ", ".join(str(e["step_id"]) for e in unchecked_steps)
            raise DomainValidationError(
                detail=(
                    f"Cannot complete WorkOrder: {len(unchecked_steps)} checklist step(s) "
                    f"remain unchecked ({missing_ids})."
                ),
                errors=unchecked_steps,
            )

        # Guard 2: At least 1 installation photo key must be uploaded
        valid_photo_keys = [key.strip() for key in installation_photos_keys if key.strip()]
        if len(valid_photo_keys) < 1:
            raise DomainValidationError(
                detail=(
                    "Cannot complete WorkOrder: at least 1 installation photo must be uploaded "
                    "before completion."
                ),
                errors=[
                    {
                        "guard": "installation_photos",
                        "uploaded_photos_count": 0,
                        "minimum_required": 1,
                        "reason": "missing_installation_photos",
                    }
                ],
            )

        # Guard 3: All serialize-mandatory hardware units must be registered in installed_serials
        missing_serial_errors: list[ErrorDetailItem] = []
        first_missing_msg: str | None = None
        for spec in required_serial_specs:
            registered_qty = registered_serial_counts.get(spec.catalog_item_id, 0)
            if registered_qty < spec.required_quantity:
                if first_missing_msg is None:
                    first_missing_msg = (
                        f"Hardware item '{spec.name_pt_br}' (SKU: {spec.sku}) requires "
                        f"{spec.required_quantity} registered serial number(s), "
                        f"but only {registered_qty} were registered."
                    )
                missing_serial_errors.append(
                    {
                        "guard": "serial_number_vault",
                        "catalog_item_id": str(spec.catalog_item_id),
                        "sku": spec.sku,
                        "required_quantity": spec.required_quantity,
                        "registered_quantity": registered_qty,
                        "reason": "missing_serial_numbers",
                    }
                )

        if missing_serial_errors:
            raise DomainValidationError(
                detail=first_missing_msg
                or "Cannot complete WorkOrder: missing mandatory hardware serial numbers.",
                errors=missing_serial_errors,
            )

    @classmethod
    def transition_to_completed(
        cls,
        current: WorkOrderStatus,
        *,
        checklist_json: Sequence[Mapping[str, object]],
        installation_photos_keys: Sequence[str],
        required_serial_specs: Sequence[RequiredHardwareSerialSpec],
        registered_serial_counts: Mapping[UUID, int],
        completed_at: datetime,
        warranty_expires_at: date,
    ) -> WorkOrderStateTransitionDiff:
        """Validate IN_FIELD -> COMPLETED transition and all 3 field completion guards."""
        cls.validate_transition(current, WorkOrderStatus.COMPLETED)
        cls.validate_completion_guards(
            checklist_json=checklist_json,
            installation_photos_keys=installation_photos_keys,
            required_serial_specs=required_serial_specs,
            registered_serial_counts=registered_serial_counts,
        )
        total_serials = sum(registered_serial_counts.values())
        return cls.build_audit_diff(
            current,
            WorkOrderStatus.COMPLETED,
            new_extra={
                "completed_at": completed_at.isoformat(),
                "warranty_expires_at": warranty_expires_at.isoformat(),
                "photos_count": len(installation_photos_keys),
                "registered_serials_count": total_serials,
            },
        )
