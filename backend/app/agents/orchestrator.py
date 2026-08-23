from __future__ import annotations
from dataclasses import dataclass
from .detection_agent import DetectionAgent
from .diagnosis_agent import DiagnosisAgent
from .decision_agent import DecisionAgent
from .execution_agent import ExecutionAgent

@dataclass(frozen=True)
class OrchestrationResult:
    detection: object
    diagnosis: object | None
    decision: object | None
    action: object | None = None
    outcome: object | None = None

class RecoveryOrchestrator:
    def __init__(self, session): self.session=session
    def assess(self, payment, event_type='payment.failed'):
        detection=DetectionAgent(self.session).detect(payment,event_type)
        if not detection.detected: return OrchestrationResult(detection,None,None)
        diagnosis=DiagnosisAgent(self.session).diagnose(payment)
        decision=DecisionAgent(self.session).decide(payment)
        return OrchestrationResult(detection,diagnosis,decision)
    def execute_if_auto_approved(self, opportunity, actor_role: str):
        if opportunity.state != 'AUTO_APPROVED': return OrchestrationResult(None,None,None)
        action,outcome=ExecutionAgent(self.session,actor_role).execute(opportunity)
        return OrchestrationResult(None,None,None,action,outcome)
