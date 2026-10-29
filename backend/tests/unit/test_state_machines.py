"""Unit tests for QuoteStateMachine and WorkOrderStateMachine transitions and guards."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from src.core.exceptions import DomainValidationError, InvalidStateTransitionError
from src.modules.quotes.models import QuoteStatus
from src.modules.quotes.state_machine import QuoteStateMachine
from src.modules.work_orders.models import WorkOrderStatus
from src.modules.work_orders.state_machine import (
    RequiredHardwareSerialSpec,
    WorkOrderStateMachine,
)


def test_quote_state_machine_happy_path_lifecycle_transitions() -> None:
    """Verify DRAFT -> SENT -> APPROVED -> IN_PROGRESS -> COMPLETED transitions and diffs."""
    now = datetime.now(UTC)
    future = now + timedelta(days=15)

    # 1. DRAFT -> SENT
    send_diff = QuoteStateMachine.transition_to_sent(
        QuoteStatus.DRAFT,
        item_count=5,
        current_version=1,
    )
    assert send_diff.previous_status == QuoteStatus.DRAFT
    assert send_diff.new_status == QuoteStatus.SENT
    assert send_diff.previous_state == {"status": "DRAFT", "version": 1}
    assert send_diff.new_state == {"status": "SENT", "version": 1, "item_count": 5}

    # 2. SENT -> APPROVED
    approve_diff = QuoteStateMachine.transition_to_approved(
        QuoteStatus.SENT,
        valid_until=future,
        now=now,
        current_version=1,
        approved_by_ip="189.40.10.15",
    )
    assert approve_diff.previous_status == QuoteStatus.SENT
    assert approve_diff.new_status == QuoteStatus.APPROVED
    assert approve_diff.previous_state == {"status": "SENT", "version": 1}
    assert approve_diff.new_state == {
        "status": "APPROVED",
        "version": 2,
        "approved_by_ip": "189.40.10.15",
    }

    # 3. APPROVED -> IN_PROGRESS
    in_progress_diff = QuoteStateMachine.transition_to_in_progress(
        QuoteStatus.APPROVED,
        current_version=2,
    )
    assert in_progress_diff.previous_status == QuoteStatus.APPROVED
    assert in_progress_diff.new_status == QuoteStatus.IN_PROGRESS
    assert in_progress_diff.new_state["version"] == 3

    # 4. IN_PROGRESS -> COMPLETED
    completed_diff = QuoteStateMachine.transition_to_completed(
        QuoteStatus.IN_PROGRESS,
        current_version=3,
    )
    assert completed_diff.previous_status == QuoteStatus.IN_PROGRESS
    assert completed_diff.new_status == QuoteStatus.COMPLETED
    assert completed_diff.new_state["version"] == 4


def test_quote_state_machine_revision_expiration_and_cancellation_rules() -> None:
    """Verify revise (SENT->DRAFT), expire (SENT->EXPIRED), reopen, and cancel stock release."""
    now = datetime.now(UTC)
    past = now - timedelta(hours=2)

    # SENT -> DRAFT (revise)
    revise_diff = QuoteStateMachine.transition_to_draft(
        QuoteStatus.SENT,
        current_version=1,
    )
    assert revise_diff.new_status == QuoteStatus.DRAFT
    assert revise_diff.new_state["version"] == 2

    # SENT -> EXPIRED
    expire_diff = QuoteStateMachine.transition_to_expired(
        QuoteStatus.SENT,
        valid_until=past,
        now=now,
        current_version=2,
    )
    assert expire_diff.new_status == QuoteStatus.EXPIRED
    assert expire_diff.new_state["version"] == 3

    # EXPIRED -> DRAFT (reopen)
    reopen_diff = QuoteStateMachine.transition_to_draft(
        QuoteStatus.EXPIRED,
        current_version=3,
    )
    assert reopen_diff.new_status == QuoteStatus.DRAFT
    assert reopen_diff.new_state["version"] == 4

    # DRAFT -> CANCELED (no stock release needed)
    cancel_draft = QuoteStateMachine.transition_to_canceled(
        QuoteStatus.DRAFT,
        current_version=4,
    )
    assert cancel_draft.new_status == QuoteStatus.CANCELED
    assert cancel_draft.requires_stock_release is False
    assert cancel_draft.new_state["released_reserved_stock"] is False

    # SENT -> CANCELED (no stock release needed)
    cancel_sent = QuoteStateMachine.transition_to_canceled(
        QuoteStatus.SENT,
        current_version=1,
    )
    assert cancel_sent.new_status == QuoteStatus.CANCELED
    assert cancel_sent.requires_stock_release is False

    # APPROVED -> CANCELED (MUST release reserved stock)
    cancel_approved = QuoteStateMachine.transition_to_canceled(
        QuoteStatus.APPROVED,
        current_version=2,
    )
    assert cancel_approved.new_status == QuoteStatus.CANCELED
    assert cancel_approved.requires_stock_release is True
    assert cancel_approved.new_state["released_reserved_stock"] is True


def test_quote_state_machine_rejects_empty_items_expired_approval_and_illegal_transitions() -> None:
    """Verify InvalidStateTransitionError (HTTP 422) on all illegal transitions and guards."""
    now = datetime.now(UTC)
    past = now - timedelta(days=1)
    future = now + timedelta(days=5)

    # Guard 1: Cannot send a quote with 0 items
    with pytest.raises(InvalidStateTransitionError) as empty_exc:
        QuoteStateMachine.transition_to_sent(QuoteStatus.DRAFT, item_count=0)
    assert empty_exc.value.http_status == 422
    assert empty_exc.value.errors is not None
    assert empty_exc.value.errors[0]["reason"] == "empty_quote_items"

    # Guard 2: Cannot approve an expired quote
    with pytest.raises(InvalidStateTransitionError) as expired_exc:
        QuoteStateMachine.transition_to_approved(
            QuoteStatus.SENT,
            valid_until=past,
            now=now,
        )
    assert expired_exc.value.http_status == 422
    assert expired_exc.value.errors is not None
    assert expired_exc.value.errors[0]["reason"] == "quote_expired"

    # Guard 3: Cannot mark as EXPIRED if valid_until is still in the future
    with pytest.raises(InvalidStateTransitionError) as not_expired_exc:
        QuoteStateMachine.transition_to_expired(
            QuoteStatus.SENT,
            valid_until=future,
            now=now,
        )
    assert not_expired_exc.value.http_status == 422
    assert not_expired_exc.value.errors is not None
    assert not_expired_exc.value.errors[0]["reason"] == "quote_not_yet_expired"

    # Illegal direct transitions
    illegal_pairs: list[tuple[QuoteStatus, QuoteStatus]] = [
        (QuoteStatus.DRAFT, QuoteStatus.APPROVED),
        (QuoteStatus.DRAFT, QuoteStatus.COMPLETED),
        (QuoteStatus.SENT, QuoteStatus.IN_PROGRESS),
        (QuoteStatus.APPROVED, QuoteStatus.DRAFT),
        (QuoteStatus.IN_PROGRESS, QuoteStatus.CANCELED),
        (QuoteStatus.COMPLETED, QuoteStatus.CANCELED),
        (QuoteStatus.COMPLETED, QuoteStatus.DRAFT),
        (QuoteStatus.CANCELED, QuoteStatus.DRAFT),
        (QuoteStatus.CANCELED, QuoteStatus.SENT),
    ]
    for current, target in illegal_pairs:
        assert QuoteStateMachine.can_transition(current, target) is False
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            QuoteStateMachine.validate_transition(current, target)
        assert exc_info.value.http_status == 422
        assert exc_info.value.errors is not None
        assert exc_info.value.errors[0]["current_status"] == current.value
        assert exc_info.value.errors[0]["target_status"] == target.value


def test_work_order_state_machine_lifecycle_and_completion_guards() -> None:
    """Verify WorkOrderStateMachine transitions and all 3 field completion guards."""
    tech_id = uuid4()
    dvr_id = uuid4()
    hdd_id = uuid4()
    now = datetime.now(UTC)
    warranty_end = date.today() + timedelta(days=365)

    # 1. PENDING -> SCHEDULED -> IN_FIELD
    sched_diff = WorkOrderStateMachine.transition_to_scheduled(
        WorkOrderStatus.PENDING,
        assigned_technician_id=tech_id,
    )
    assert sched_diff.new_status == WorkOrderStatus.SCHEDULED
    assert sched_diff.new_state["assigned_technician_id"] == str(tech_id)

    start_diff = WorkOrderStateMachine.transition_to_in_field(
        WorkOrderStatus.SCHEDULED,
        assigned_technician_id=tech_id,
    )
    assert start_diff.new_status == WorkOrderStatus.IN_FIELD

    # Also allow direct PENDING -> IN_FIELD
    direct_start = WorkOrderStateMachine.transition_to_in_field(WorkOrderStatus.PENDING)
    assert direct_start.new_status == WorkOrderStatus.IN_FIELD

    required_specs = [
        RequiredHardwareSerialSpec(
            catalog_item_id=dvr_id,
            sku="MHDX-1108",
            name_pt_br="DVR Intelbras MHDX 1108",
            required_quantity=1,
        ),
        RequiredHardwareSerialSpec(
            catalog_item_id=hdd_id,
            sku="WD20PURZ",
            name_pt_br="HD WD Purple 2TB",
            required_quantity=1,
        ),
    ]

    complete_checklist: list[dict[str, object]] = [
        {"step_id": "step_1", "label_pt_br": "Fixação das câmeras", "is_checked": True},
        {"step_id": "step_2", "label_pt_br": "Configuração Cloud P2P", "is_checked": True},
    ]

    # Guard 1 failure: Unchecked step
    with pytest.raises(DomainValidationError) as chk_exc:
        WorkOrderStateMachine.transition_to_completed(
            WorkOrderStatus.IN_FIELD,
            checklist_json=[
                {"step_id": "step_1", "label_pt_br": "Fixação das câmeras", "is_checked": True},
                {"step_id": "step_2", "label_pt_br": "Configuração Cloud P2P", "is_checked": False},
            ],
            installation_photos_keys=["photos/wo/rack.jpg"],
            required_serial_specs=required_specs,
            registered_serial_counts={dvr_id: 1, hdd_id: 1},
            completed_at=now,
            warranty_expires_at=warranty_end,
        )
    assert chk_exc.value.http_status == 422
    assert chk_exc.value.errors is not None
    assert chk_exc.value.errors[0]["reason"] == "unchecked_checklist_step"

    # Guard 2 failure: Missing installation photos
    with pytest.raises(DomainValidationError) as photo_exc:
        WorkOrderStateMachine.transition_to_completed(
            WorkOrderStatus.IN_FIELD,
            checklist_json=complete_checklist,
            installation_photos_keys=[],
            required_serial_specs=required_specs,
            registered_serial_counts={dvr_id: 1, hdd_id: 1},
            completed_at=now,
            warranty_expires_at=warranty_end,
        )
    assert photo_exc.value.http_status == 422
    assert photo_exc.value.errors is not None
    assert photo_exc.value.errors[0]["reason"] == "missing_installation_photos"

    # Guard 3 failure: Missing HDD serial number
    with pytest.raises(DomainValidationError) as serial_exc:
        WorkOrderStateMachine.transition_to_completed(
            WorkOrderStatus.IN_FIELD,
            checklist_json=complete_checklist,
            installation_photos_keys=["photos/wo/rack.jpg"],
            required_serial_specs=required_specs,
            registered_serial_counts={dvr_id: 1},
            completed_at=now,
            warranty_expires_at=warranty_end,
        )
    assert serial_exc.value.http_status == 422
    assert serial_exc.value.errors is not None
    assert serial_exc.value.errors[0]["reason"] == "missing_serial_numbers"
    assert serial_exc.value.errors[0]["sku"] == "WD20PURZ"

    # Happy path: All 3 guards pass -> COMPLETED
    complete_diff = WorkOrderStateMachine.transition_to_completed(
        WorkOrderStatus.IN_FIELD,
        checklist_json=complete_checklist,
        installation_photos_keys=["photos/wo/rack.jpg"],
        required_serial_specs=required_specs,
        registered_serial_counts={dvr_id: 1, hdd_id: 1},
        completed_at=now,
        warranty_expires_at=warranty_end,
    )
    assert complete_diff.new_status == WorkOrderStatus.COMPLETED
    assert complete_diff.new_state["registered_serials_count"] == 2

    # Illegal transitions (e.g., PENDING -> COMPLETED directly, COMPLETED -> IN_FIELD)
    with pytest.raises(InvalidStateTransitionError):
        WorkOrderStateMachine.validate_transition(
            WorkOrderStatus.PENDING,
            WorkOrderStatus.COMPLETED,
        )
    with pytest.raises(InvalidStateTransitionError):
        WorkOrderStateMachine.validate_transition(
            WorkOrderStatus.COMPLETED,
            WorkOrderStatus.IN_FIELD,
        )
