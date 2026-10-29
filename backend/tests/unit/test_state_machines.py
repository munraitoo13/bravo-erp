"""Unit tests for QuoteStateMachine transitions, guards, and audit diff generation."""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.exceptions import InvalidStateTransitionError
from src.modules.quotes.models import QuoteStatus
from src.modules.quotes.state_machine import QuoteStateMachine


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
