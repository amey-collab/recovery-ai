import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.agents.decision_agent import DecisionAgent
from app.agents.diagnosis_agent import DiagnosisAgent
from app.agents.detection_agent import DetectionAgent
from app.agents.execution_agent import ExecutionAgent
from app.agents.orchestrator import RecoveryOrchestrator
from app.main import Audit, Base, Customer, Payment, RecoveryAction, SessionLocal, engine, pipeline

Base.metadata.create_all(engine)


def fixture():
    s=SessionLocal(); marker=uuid.uuid4().hex
    c=Customer(external_id='agent_customer_'+marker,name='agent-test',email=marker+'@example.test',success_rate=.9,lifetime_value=1000);s.add(c);s.flush()
    p=Payment(external_id='agent_payment_'+marker,customer_id=c.id,amount=4999,status='failed',failure_reason='temporary_bank_error',retry_count=0);s.add(p);s.flush();return s,p


def test_detection_and_diagnosis_are_structured():
    s,p=fixture()
    try:
        detection=DetectionAgent(s).detect(p); diagnosis=DiagnosisAgent(s).diagnose(p)
        assert detection.detected and detection.payment_id==p.external_id
        assert diagnosis.category=='temporary_bank_error'; assert diagnosis.contributing_factors['failure_reason']==p.failure_reason
    finally:s.rollback();s.close()


def test_decision_agent_uses_existing_deterministic_pipeline():
    s,p=fixture()
    try:
        result=DecisionAgent(s).decide(p); assert 0<=result.recovery_probability<=1; assert result.prediction_source=='model'; assert result.recommended_action in result.intervention_rankings
    finally:s.rollback();s.close()


def test_orchestrator_stops_non_failed_payment():
    s,p=fixture();p.status='captured'
    try:
        result=RecoveryOrchestrator(s).assess(p); assert result.detection.detected is False; assert result.decision is None
    finally:s.rollback();s.close()


def test_execution_requires_authorization_and_auto_approval():
    s,p=fixture();o=pipeline(s,p);s.flush()
    try:
        with pytest.raises(PermissionError): ExecutionAgent(s,'VIEWER').execute(o)
        o.state='HUMAN_REVIEW'
        with pytest.raises(ValueError): ExecutionAgent(s,'OPERATOR').execute(o)
    finally:s.rollback();s.close()


def test_blocked_guardrail_cannot_be_bypassed():
    s,p=fixture();o=pipeline(s,p);s.flush();o.state='AUTO_APPROVED';o.recommended_action='RETRY';p.retry_count=2
    try:
        with pytest.raises(ValueError,match='guardrail rejected'): ExecutionAgent(s,'OPERATOR').execute(o)
    finally:s.rollback();s.close()


def test_execution_agent_duplicate_protection_and_audit_timeline():
    s,p=fixture();o=pipeline(s,p);s.flush()
    try:
        assert o.state=='AUTO_APPROVED'; action,result=ExecutionAgent(s,'OPERATOR').execute(o);s.flush();assert result.status.value=='SIMULATED';
        with pytest.raises(ValueError,match='duplicate'): ExecutionAgent(s,'OPERATOR').execute(o)
        events={x.action for x in s.scalars(select(Audit).where(Audit.payment_id==p.external_id)).all()};assert {'DETECTION','DIAGNOSIS','DECISION','OUTCOME'}.issubset(events);assert action.status=='SIMULATED_TEST_RECOVERY'
    finally:s.rollback();s.close()
