import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.feature_builder import FEATURE_COLUMNS, MODEL_INPUT_FORBIDDEN, FeatureBuilder
from app.main import Base, Customer, Payment, SessionLocal, engine, prediction_service

Base.metadata.create_all(engine)


def payment_fixture(with_history=True):
    session = SessionLocal()
    marker = uuid.uuid4().hex
    customer = Customer(
        external_id='feature_customer_' + marker,
        name='feature-test',
        email=marker + '@example.test',
        lifetime_value=42000,
        success_rate=.8,
    )
    session.add(customer)
    session.flush()
    if with_history:
        session.add(Payment(external_id='feature_old_' + marker, customer_id=customer.id, amount=1000, status='captured'))
        session.add(Payment(external_id='feature_failed_' + marker, customer_id=customer.id, amount=1200, status='failed'))
        session.flush()
    current = Payment(
        external_id='feature_current_' + marker,
        customer_id=customer.id,
        amount=4999,
        status='failed',
        method='card',
        failure_reason='temporary_bank_error',
        retry_count=1,
    )
    session.add(current)
    session.flush()
    return session, current


def test_feature_builder_uses_real_history_and_order():
    session, payment = payment_fixture()
    try:
        features = FeatureBuilder(session).build(payment)
        assert list(features) == FEATURE_COLUMNS
        assert features['previous_payment_count'] == 2
        assert features['previous_success_count'] == 1
        assert features['previous_failure_count'] == 1
        assert features['customer_lifetime_value'] == 42000
        assert features['customer_success_rate'] == .5
    finally:
        session.rollback()
        session.close()


def test_feature_builder_missing_history_policy_is_deterministic():
    session, payment = payment_fixture(with_history=False)
    try:
        features = FeatureBuilder(session).build(payment)
        assert features['previous_payment_count'] == 0
        assert features['previous_success_count'] == 0
        assert features['previous_failure_count'] == 0
        assert features['average_transaction_amount'] == payment.amount
        assert features['subscription_status'] == 'none'
        assert features['merchant_category'] == 'unknown'
        assert features['customer_segment'] == 'unknown'
    finally:
        session.rollback()
        session.close()


def test_feature_builder_has_no_target_or_outcome_columns():
    session, payment = payment_fixture(with_history=False)
    try:
        features = FeatureBuilder(session).build(payment)
        assert not set(features).intersection(MODEL_INPUT_FORBIDDEN)
    finally:
        session.rollback()
        session.close()


def test_saved_model_inference_uses_feature_builder():
    session, payment = payment_fixture()
    try:
        probability, version, source = prediction_service(session, payment)
        assert 0 <= probability <= 1
        assert version.startswith('synthetic-v2')
        assert source == 'model'
    finally:
        session.rollback()
        session.close()
