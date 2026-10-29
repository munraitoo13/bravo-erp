"""Quote lifecycle state machine, transition guards, and audit log diff builder."""

from dataclasses import dataclass
from datetime import UTC, datetime

from src.core.exceptions import InvalidStateTransitionError
from src.modules.quotes.models import QuoteStatus

ALLOWED_QUOTE_TRANSITIONS: dict[QuoteStatus, frozenset[QuoteStatus]] = {
    QuoteStatus.DRAFT: frozenset({QuoteStatus.SENT, QuoteStatus.CANCELED}),
    QuoteStatus.SENT: frozenset(
        {
            QuoteStatus.APPROVED,
            QuoteStatus.DRAFT,
            QuoteStatus.EXPIRED,
            QuoteStatus.CANCELED,
        }
    ),
    QuoteStatus.APPROVED: frozenset({QuoteStatus.IN_PROGRESS, QuoteStatus.CANCELED}),
    QuoteStatus.IN_PROGRESS: frozenset({QuoteStatus.COMPLETED}),
    QuoteStatus.EXPIRED: frozenset({QuoteStatus.DRAFT}),
    QuoteStatus.COMPLETED: frozenset(),
    QuoteStatus.CANCELED: frozenset(),
}


@dataclass(frozen=True)
class QuoteStateTransitionDiff:
    """Structured state diff payload persisted in audit_logs."""

    previous_status: QuoteStatus
    new_status: QuoteStatus
    previous_state: dict[str, object]
    new_state: dict[str, object]
    requires_stock_release: bool = False


class QuoteStateMachine:
    """Pure domain state machine enforcing Quote lifecycle transitions and invariants."""

    @staticmethod
    def can_transition(current: QuoteStatus, target: QuoteStatus) -> bool:
        """Return True if transitioning from current to target is permitted."""
        return target in ALLOWED_QUOTE_TRANSITIONS.get(current, frozenset())

    @classmethod
    def validate_transition(cls, current: QuoteStatus, target: QuoteStatus) -> None:
        """Raise InvalidStateTransitionError (HTTP 422) if current -> target is illegal."""
        if not cls.can_transition(current, target):
            allowed = sorted(s.value for s in ALLOWED_QUOTE_TRANSITIONS.get(current, frozenset()))
            allowed_str = ", ".join(allowed) if allowed else "none (terminal state)"
            raise InvalidStateTransitionError(
                detail=(
                    f"Cannot transition Quote from '{current.value}' to '{target.value}'. "
                    f"Allowed target states from '{current.value}': {allowed_str}."
                ),
                errors=[
                    {
                        "entity_type": "QUOTE",
                        "current_status": current.value,
                        "target_status": target.value,
                        "allowed_targets": allowed_str,
                    }
                ],
            )

    @staticmethod
    def build_audit_diff(
        previous_status: QuoteStatus,
        new_status: QuoteStatus,
        *,
        previous_extra: dict[str, object] | None = None,
        new_extra: dict[str, object] | None = None,
        requires_stock_release: bool = False,
    ) -> QuoteStateTransitionDiff:
        """Construct a structured previous_state and new_state snapshot for audit_logs."""
        prev_dict: dict[str, object] = {"status": previous_status.value}
        if previous_extra:
            prev_dict.update(previous_extra)

        new_dict: dict[str, object] = {"status": new_status.value}
        if new_extra:
            new_dict.update(new_extra)

        return QuoteStateTransitionDiff(
            previous_status=previous_status,
            new_status=new_status,
            previous_state=prev_dict,
            new_state=new_dict,
            requires_stock_release=requires_stock_release,
        )

    @classmethod
    def transition_to_sent(
        cls,
        current: QuoteStatus,
        *,
        item_count: int,
        current_version: int = 1,
    ) -> QuoteStateTransitionDiff:
        """Validate DRAFT -> SENT transition requiring at least 1 quote line item."""
        cls.validate_transition(current, QuoteStatus.SENT)
        if item_count < 1:
            raise InvalidStateTransitionError(
                detail="Cannot send a Quote with 0 line items. Add at least 1 item first.",
                errors=[
                    {
                        "entity_type": "QUOTE",
                        "current_status": current.value,
                        "target_status": QuoteStatus.SENT.value,
                        "item_count": item_count,
                        "reason": "empty_quote_items",
                    }
                ],
            )
        return cls.build_audit_diff(
            current,
            QuoteStatus.SENT,
            previous_extra={"version": current_version},
            new_extra={"version": current_version, "item_count": item_count},
        )

    @classmethod
    def transition_to_approved(
        cls,
        current: QuoteStatus,
        *,
        valid_until: datetime,
        now: datetime | None = None,
        current_version: int = 1,
        approved_by_ip: str | None = None,
    ) -> QuoteStateTransitionDiff:
        """Validate SENT -> APPROVED transition and ensure proposal has not expired."""
        cls.validate_transition(current, QuoteStatus.APPROVED)
        effective_now = now or datetime.now(UTC)
        if valid_until < effective_now:
            raise InvalidStateTransitionError(
                detail=(
                    f"Cannot approve Quote because its validity expired at "
                    f"{valid_until.isoformat()}."
                ),
                errors=[
                    {
                        "entity_type": "QUOTE",
                        "current_status": current.value,
                        "target_status": QuoteStatus.APPROVED.value,
                        "valid_until": valid_until.isoformat(),
                        "reason": "quote_expired",
                    }
                ],
            )
        new_extra: dict[str, object] = {"version": current_version + 1}
        if approved_by_ip is not None:
            new_extra["approved_by_ip"] = approved_by_ip
        return cls.build_audit_diff(
            current,
            QuoteStatus.APPROVED,
            previous_extra={"version": current_version},
            new_extra=new_extra,
        )

    @classmethod
    def transition_to_draft(
        cls,
        current: QuoteStatus,
        *,
        current_version: int = 1,
    ) -> QuoteStateTransitionDiff:
        """Validate SENT -> DRAFT (revise) or EXPIRED -> DRAFT (reopen) transition."""
        cls.validate_transition(current, QuoteStatus.DRAFT)
        return cls.build_audit_diff(
            current,
            QuoteStatus.DRAFT,
            previous_extra={"version": current_version},
            new_extra={"version": current_version + 1},
        )

    @classmethod
    def transition_to_expired(
        cls,
        current: QuoteStatus,
        *,
        valid_until: datetime,
        now: datetime | None = None,
        current_version: int = 1,
    ) -> QuoteStateTransitionDiff:
        """Validate SENT -> EXPIRED transition when valid_until < now()."""
        cls.validate_transition(current, QuoteStatus.EXPIRED)
        effective_now = now or datetime.now(UTC)
        if valid_until >= effective_now:
            raise InvalidStateTransitionError(
                detail=(
                    f"Cannot mark Quote as EXPIRED while valid_until ({valid_until.isoformat()}) "
                    f"is still in the future."
                ),
                errors=[
                    {
                        "entity_type": "QUOTE",
                        "current_status": current.value,
                        "target_status": QuoteStatus.EXPIRED.value,
                        "valid_until": valid_until.isoformat(),
                        "reason": "quote_not_yet_expired",
                    }
                ],
            )
        return cls.build_audit_diff(
            current,
            QuoteStatus.EXPIRED,
            previous_extra={"version": current_version},
            new_extra={"version": current_version + 1},
        )

    @classmethod
    def transition_to_canceled(
        cls,
        current: QuoteStatus,
        *,
        current_version: int = 1,
    ) -> QuoteStateTransitionDiff:
        """Validate DRAFT/SENT/APPROVED -> CANCELED and flag if reserved stock must be released."""
        cls.validate_transition(current, QuoteStatus.CANCELED)
        requires_release = current == QuoteStatus.APPROVED
        return cls.build_audit_diff(
            current,
            QuoteStatus.CANCELED,
            previous_extra={"version": current_version},
            new_extra={
                "version": current_version + 1,
                "released_reserved_stock": requires_release,
            },
            requires_stock_release=requires_release,
        )

    @classmethod
    def transition_to_in_progress(
        cls,
        current: QuoteStatus,
        *,
        current_version: int = 1,
    ) -> QuoteStateTransitionDiff:
        """Validate APPROVED -> IN_PROGRESS transition when field WorkOrder starts."""
        cls.validate_transition(current, QuoteStatus.IN_PROGRESS)
        return cls.build_audit_diff(
            current,
            QuoteStatus.IN_PROGRESS,
            previous_extra={"version": current_version},
            new_extra={"version": current_version + 1},
        )

    @classmethod
    def transition_to_completed(
        cls,
        current: QuoteStatus,
        *,
        current_version: int = 1,
    ) -> QuoteStateTransitionDiff:
        """Validate IN_PROGRESS -> COMPLETED transition when field WorkOrder completes."""
        cls.validate_transition(current, QuoteStatus.COMPLETED)
        return cls.build_audit_diff(
            current,
            QuoteStatus.COMPLETED,
            previous_extra={"version": current_version},
            new_extra={"version": current_version + 1},
        )
