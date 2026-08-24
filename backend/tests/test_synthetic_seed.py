import uuid

from sqlalchemy import select

from app.main import Customer, Payment, SessionLocal
from app.synthetic_seed import seed_synthetic_data


def test_synthetic_seed_is_idempotent_and_creates_pipeline_records():
    session = SessionLocal()
    namespace = "recoverai_synthetic_test_seed_" + uuid.uuid4().hex
    try:
        first = seed_synthetic_data(session, count=3, namespace=namespace)
        session.flush()
        second = seed_synthetic_data(session, count=3, namespace=namespace)
        assert first.created_bundles == 3
        assert second.created_bundles == 0
        assert second.skipped_bundles == 3
        assert first.created["payments"] == 3
        assert first.created["opportunities"] == 3
        assert first.created["predictions"] == 3
        assert first.created["intervention_scores"] == 3
        assert first.created["audit_logs"] == 9
    finally:
        session.rollback()
        session.close()


def test_synthetic_seed_does_not_modify_existing_payment():
    session = SessionLocal()
    namespace = "recoverai_synthetic_test_existing_" + uuid.uuid4().hex
    external_id = f"{namespace}_0_payment"
    customer = Customer(external_id=f"{namespace}_0_customer", name="existing", email=f"{namespace}@example.test")
    session.add(customer)
    session.flush()
    payment = Payment(external_id=external_id, customer_id=customer.id, amount=1234, status="captured", retry_count=7)
    session.add(payment)
    session.flush()
    try:
        report = seed_synthetic_data(session, count=1, namespace=namespace)
        session.flush()
        unchanged = session.scalar(select(Payment).where(Payment.external_id == external_id))
        assert report.created_bundles == 0 and report.skipped_bundles == 1
        assert unchanged.amount == 1234 and unchanged.status == "captured" and unchanged.retry_count == 7
    finally:
        session.rollback()
        session.close()
