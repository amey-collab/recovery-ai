"""Deterministic execution-to-outcome workflow using the existing schema."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session


class OutcomeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"
    SIMULATED = "SIMULATED"


@dataclass(frozen=True)
class OutcomeResult:
    outcome: object
    status: OutcomeStatus
    execution_mode: str
    recovered_amount: float
    attempted_amount: float
    idempotent: bool = False


class OutcomeService:
    """Persist one outcome per recovery action and audit each transition."""

    def __init__(self, session: Session):
        self.session = session

    def _context(self, action):
        from app.main import Opportunity, Payment

        opportunity = self.session.get(Opportunity, action.opportunity_id)
        payment = self.session.get(Payment, opportunity.payment_id) if opportunity else None
        if not opportunity or not payment:
            raise ValueError("Recovery action has no valid opportunity/payment")
        return opportunity, payment

    @staticmethod
    def status_for(action, outcome) -> OutcomeStatus:
        if action.simulated or action.status == "SIMULATED_TEST_RECOVERY":
            return OutcomeStatus.SIMULATED
        if action.status == OutcomeStatus.PENDING.value:
            return OutcomeStatus.PENDING
        return OutcomeStatus.SUCCESS if outcome.success else OutcomeStatus.FAILED

    def record(
        self,
        action,
        status: OutcomeStatus,
        *,
        recovered_amount: float = 0.0,
        failure_reason: str | None = None,
        execution_mode: str = "TEST",
        metadata: dict | None = None,
    ) -> OutcomeResult:
        from app.main import Audit, Outcome, State, audit

        opportunity, payment = self._context(action)
        attempted_amount = float(payment.amount)
        existing = self.session.scalar(select(Outcome).where(Outcome.action_id == action.id))
        if existing:
            return OutcomeResult(
                existing,
                self.status_for(action, existing),
                "SIMULATED" if action.simulated else execution_mode,
                float(existing.amount),
                attempted_amount,
                True,
            )
        if status == OutcomeStatus.SUCCESS:
            if action.simulated:
                raise ValueError("Simulated actions cannot record a real SUCCESS outcome")
            if recovered_amount <= 0 or recovered_amount > attempted_amount:
                raise ValueError("Successful recovered amount must be > 0 and <= payment amount")
            success = True
            amount = float(recovered_amount)
            action.status = OutcomeStatus.SUCCESS.value
            opportunity.state = State.SUCCESS.value
            event = "RECOVERY_SUCCEEDED"
            reason = "verified recovery outcome"
        elif status == OutcomeStatus.FAILED:
            if recovered_amount != 0:
                raise ValueError("Failed outcomes cannot claim recovered revenue")
            success = False
            amount = 0.0
            action.status = OutcomeStatus.FAILED.value
            opportunity.state = State.FAILED.value
            event = "RECOVERY_FAILED"
            reason = failure_reason or "recovery execution failed"
        elif status == OutcomeStatus.PENDING:
            if recovered_amount != 0:
                raise ValueError("Pending outcomes cannot claim recovered revenue")
            success = False
            amount = 0.0
            action.status = OutcomeStatus.PENDING.value
            event = "RECOVERY_PENDING"
            reason = "recovery execution is awaiting verification"
        elif status == OutcomeStatus.SIMULATED:
            if recovered_amount != 0:
                raise ValueError("Simulated outcomes cannot claim recovered revenue")
            success = False
            amount = 0.0
            action.simulated = True
            action.status = "SIMULATED_TEST_RECOVERY"
            event = "RECOVERY_SIMULATED"
            reason = "SIMULATED_TEST_RECOVERY; no real revenue claimed"
        else:
            raise ValueError(f"Unsupported outcome status: {status}")
        outcome = Outcome(action_id=action.id, success=success, amount=amount)
        self.session.add(outcome)
        audit(
            self.session,
            payment,
            "OutcomeAgent",
            event,
            reason,
            outcome_status=status.value,
            execution_mode="SIMULATED" if action.simulated else execution_mode,
            attempted_amount=attempted_amount,
            recovered_amount=amount,
            failure_reason=failure_reason,
            metadata=metadata or {},
        )
        return OutcomeResult(outcome, status, "SIMULATED" if action.simulated else execution_mode, amount, attempted_amount)

