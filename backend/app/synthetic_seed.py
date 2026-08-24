"""Idempotent, explicitly synthetic demo-data seeding.

This module deliberately does not create schema objects.  Production schema
creation remains the responsibility of Alembic.  A seed *bundle* consists of
one customer, one failed payment, and the normal prediction/intervention/
opportunity/audit records produced by ``pipeline``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import Audit, Customer, Payment, pipeline

DEFAULT_NAMESPACE = "recoverai_synthetic_v1"
MAX_BUNDLES = 5


@dataclass
class SeedReport:
    requested: int
    created_bundles: int = 0
    skipped_bundles: int = 0
    created: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)


def seed_synthetic_data(
    session: Session,
    *,
    count: int = 4,
    namespace: str = DEFAULT_NAMESPACE,
) -> SeedReport:
    """Create missing synthetic bundles without changing existing rows.

    The caller owns commit/rollback.  Existing rows are only read; they are
    never updated or deleted.  ``count`` is intentionally capped so this
    utility cannot become a bulk production loader.
    """
    if not 1 <= count <= MAX_BUNDLES:
        raise ValueError(f"count must be between 1 and {MAX_BUNDLES}")
    if not namespace.startswith("recoverai_synthetic_") or any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in namespace
    ):
        raise ValueError("namespace must use the recoverai_synthetic_ prefix and contain safe characters")

    report = SeedReport(requested=count)
    for index in range(count):
        marker = f"{namespace}_{index}"
        payment_external_id = f"{marker}_payment"
        customer_external_id = f"{marker}_customer"

        existing_payment = session.scalar(select(Payment).where(Payment.external_id == payment_external_id))
        if existing_payment is not None:
            report.skipped_bundles += 1
            report.skipped["bundles"] = report.skipped.get("bundles", 0) + 1
            continue

        customer = session.scalar(select(Customer).where(Customer.external_id == customer_external_id))
        if customer is None:
            customer = Customer(
                external_id=customer_external_id,
                name=f"RecoverAI Synthetic Test Customer {index + 1}",
                email=f"{marker}@synthetic.recoverai.test",
                lifetime_value=2500 + index * 750,
                success_rate=0.72 + index * 0.04,
            )
            session.add(customer)
            session.flush()
            report.created["customers"] = report.created.get("customers", 0) + 1

        payment = Payment(
            external_id=payment_external_id,
            customer_id=customer.id,
            order_id=f"{marker}_order",
            amount=799 + index * 600,
            currency="INR",
            method=("card", "upi", "netbanking", "card", "upi")[index],
            status="failed",
            failure_reason=("temporary_bank_error", "insufficient_funds", "network_error", "expired_card", "payment_method_error")[index],
            retry_count=0,
        )
        session.add(payment)
        session.flush()
        report.created["payments"] = report.created.get("payments", 0) + 1

        opportunity = pipeline(session, payment)
        if opportunity is None:
            raise RuntimeError(f"pipeline did not produce an opportunity for synthetic bundle {index}")
        session.flush()
        report.created_bundles += 1
        for key in ("opportunities", "predictions", "intervention_scores"):
            report.created[key] = report.created.get(key, 0) + 1

        # The pipeline invokes Detection, Diagnosis, and Decision agents.
        report.created["audit_logs"] = report.created.get("audit_logs", 0) + session.query(Audit).filter(Audit.payment_id == payment.external_id).count()

    return report
