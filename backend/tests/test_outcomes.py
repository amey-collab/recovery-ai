import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.main import Audit, Base, Customer, Opportunity, Outcome, Payment, RecoveryAction, SessionLocal, engine, pipeline
from app.outcome_service import OutcomeService, OutcomeStatus

Base.metadata.create_all(engine)


def action_fixture(simulated=False):
    session = SessionLocal()
    marker = uuid.uuid4().hex
    customer = Customer(external_id='outcome_customer_'+marker,name='outcome-test',email=marker+'@example.test',success_rate=.9,lifetime_value=20000)
    session.add(customer); session.flush()
    payment = Payment(external_id='outcome_payment_'+marker,customer_id=customer.id,amount=4999,status='failed',failure_reason='temporary_bank_error')
    session.add(payment); session.flush()
    opportunity = pipeline(session,payment); session.flush()
    action = RecoveryAction(opportunity_id=opportunity.id,action='retry',status='EXECUTING',simulated=simulated)
    session.add(action); session.flush()
    return session, payment, opportunity, action


def test_successful_outcome_persists_valid_amount():
    s,p,o,a=action_fixture()
    try:
        result=OutcomeService(s).record(a,OutcomeStatus.SUCCESS,recovered_amount=2500,execution_mode='RAZORPAY_TEST')
        s.flush(); assert result.status==OutcomeStatus.SUCCESS; assert result.outcome.success is True; assert result.outcome.amount==2500; assert o.state=='SUCCESS'; assert a.status=='SUCCESS'
    finally: s.rollback();s.close()


def test_failed_and_pending_outcomes_do_not_claim_revenue():
    for status in (OutcomeStatus.FAILED,OutcomeStatus.PENDING):
        s,p,o,a=action_fixture()
        try:
            result=OutcomeService(s).record(a,status,failure_reason='synthetic failure')
            s.flush(); assert result.outcome.success is False; assert result.outcome.amount==0; assert result.status==status
        finally: s.rollback();s.close()


def test_simulated_outcome_is_distinct_and_zero_revenue():
    s,p,o,a=action_fixture(simulated=True)
    try:
        result=OutcomeService(s).record(a,OutcomeStatus.SIMULATED,execution_mode='SIMULATED')
        s.flush(); assert result.status==OutcomeStatus.SIMULATED; assert a.status=='SIMULATED_TEST_RECOVERY'; assert result.outcome.success is False; assert result.outcome.amount==0
        assert s.scalar(select(func.coalesce(func.sum(Outcome.amount),0)).where(Outcome.success.is_(True))) == 0
    finally: s.rollback();s.close()


def test_invalid_recovered_amounts_are_rejected():
    s,p,o,a=action_fixture()
    try:
        with pytest.raises(ValueError): OutcomeService(s).record(a,OutcomeStatus.SUCCESS,recovered_amount=0)
        with pytest.raises(ValueError): OutcomeService(s).record(a,OutcomeStatus.SUCCESS,recovered_amount=6000)
        with pytest.raises(ValueError): OutcomeService(s).record(a,OutcomeStatus.FAILED,recovered_amount=1)
    finally: s.rollback();s.close()


def test_duplicate_outcome_is_idempotent_and_audited():
    s,p,o,a=action_fixture()
    try:
        service=OutcomeService(s); first=service.record(a,OutcomeStatus.SUCCESS,recovered_amount=1000);s.flush();second=service.record(a,OutcomeStatus.SUCCESS,recovered_amount=1000);s.flush()
        assert second.idempotent is True; assert s.scalar(select(func.count(Outcome.id)).where(Outcome.action_id==a.id))==1; assert s.scalar(select(func.count(Audit.id)).where(Audit.payment_id==p.external_id,Audit.action=='RECOVERY_SUCCEEDED'))==1
    finally: s.rollback();s.close()
