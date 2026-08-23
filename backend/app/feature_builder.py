"""Decision-time feature construction for the persisted RecoverAI model.

Only information available on the current payment, its customer, and prior
database records is used. Fields not represented by the current schema use
documented deterministic defaults; no synthetic history is created here.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
ML_PATH = ROOT / "ml"
if str(ML_PATH) not in sys.path:
    sys.path.insert(0, str(ML_PATH))
from preprocessing import (  # noqa: E402
    FEATURE_COLUMNS,
    OUTCOME_COLUMNS,
    TARGET_COLUMNS,
)

MODEL_INPUT_FORBIDDEN = set(OUTCOME_COLUMNS) | set(TARGET_COLUMNS)


class FeatureBuilder:
    """Build exactly the persisted model's feature columns in fixed order."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _days_between(later: datetime, earlier: datetime) -> int:
        if later.tzinfo is None:
            later = later.replace(tzinfo=timezone.utc)
        if earlier.tzinfo is None:
            earlier = earlier.replace(tzinfo=timezone.utc)
        return max(0, (later - earlier).days)

    def build(self, payment) -> dict:
        # Imported lazily to avoid a model ↔ feature-builder import cycle.
        from app.main import Audit, Customer, Opportunity, Outcome, Payment, RecoveryAction

        history = list(
            self.session.scalars(
            select(Payment)
                .where(
                    Payment.customer_id == payment.customer_id,
                    Payment.id != payment.id,
                    Payment.created_at <= payment.created_at,
                )
                .order_by(Payment.created_at.asc())
            ).all()
        )
        prior_count = len(history)
        prior_success = sum(1 for item in history if item.status in {"captured", "authorized", "success", "paid"})
        prior_failure = sum(1 for item in history if item.status == "failed")
        customer = payment.customer
        customer_rate = (
            prior_success / prior_count
            if prior_count
            else (float(customer.success_rate) if customer and customer.success_rate is not None else 0.5)
        )
        previous_amounts = [float(item.amount) for item in history if item.amount is not None]
        average_amount = sum(previous_amounts) / len(previous_amounts) if previous_amounts else float(payment.amount)
        # The PostgreSQL column is timezone-naive in the current schema even
        # though application values may be timezone-aware. The SQL predicate
        # already limits rows to prior records, so no second Python comparison
        # is needed here.
        prior_dates = [item.created_at for item in history if item.created_at]
        days_since_last = self._days_between(payment.created_at, max(prior_dates)) if prior_dates else 0

        successful_outcomes = int(
            self.session.scalar(
                select(func.count(Outcome.id))
                .join(RecoveryAction, Outcome.action_id == RecoveryAction.id)
                .join(Opportunity, RecoveryAction.opportunity_id == Opportunity.id)
                .join(Payment, Opportunity.payment_id == Payment.id)
                .where(Payment.customer_id == payment.customer_id, Outcome.success.is_(True))
            )
            or 0
        )
        historical_recovery_rate = successful_outcomes / prior_failure if prior_failure else 0.0
        latest_action = self.session.scalar(
            select(RecoveryAction.action)
            .join(Opportunity, RecoveryAction.opportunity_id == Opportunity.id)
            .join(Payment, Opportunity.payment_id == Payment.id)
            .where(Payment.customer_id == payment.customer_id)
            .order_by(RecoveryAction.created_at.desc())
            .limit(1)
        ) or "no_action"

        created_at = payment.created_at or datetime.now(timezone.utc)
        # These values are explicitly schema-missing defaults: the current
        # database has no subscription, merchant, or customer-created-at fields.
        features = {
            "amount": float(payment.amount),
            "payment_method": payment.method or "unknown",
            "failure_reason": payment.failure_reason or "unknown",
            "failure_source": "unknown",
            "failure_step": "unknown",
            "customer_age_days": 0,
            "previous_payment_count": prior_count,
            "previous_success_count": prior_success,
            "previous_failure_count": prior_failure,
            "customer_success_rate": round(max(0.0, min(1.0, customer_rate)), 6),
            "average_transaction_amount": round(average_amount, 2),
            "customer_lifetime_value": float(customer.lifetime_value) if customer and customer.lifetime_value is not None else 0.0,
            "days_since_last_payment": days_since_last,
            "retry_count": int(payment.retry_count or 0),
            "previous_recovery_count": successful_outcomes,
            "historical_recovery_rate": round(max(0.0, min(1.0, historical_recovery_rate)), 6),
            "previous_intervention": latest_action,
            "subscription_status": "none",
            "subscription_age_days": 0,
            "time_of_day": int(created_at.hour),
            "day_of_week": int(created_at.weekday()),
            "merchant_category": "unknown",
            "customer_segment": "unknown",
        }
        if set(features) & MODEL_INPUT_FORBIDDEN:
            raise ValueError("Target/outcome leakage detected in FeatureBuilder output")
        if list(features) != FEATURE_COLUMNS:
            raise ValueError("FeatureBuilder output order does not match FEATURE_COLUMNS")
        return features

    def dataframe(self, payment) -> pd.DataFrame:
        return pd.DataFrame([self.build(payment)], columns=FEATURE_COLUMNS)
