from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class DecisionResult:
    payment_id: str
    recovery_probability: float
    model_version: str
    prediction_source: str
    intervention_rankings: dict
    expected_recovery_value: float
    recommended_action: str
    decision_status: str
    priority: str
    guardrail_result: dict
    reasons: str
    timestamp: datetime

class DecisionAgent:
    def __init__(self, session): self.session = session
    def decide(self, payment) -> DecisionResult:
        from app.main import audit, decision_engine
        result = decision_engine(self.session, payment)
        output = DecisionResult(payment.external_id, result['probability'], result['model_version'], result['source'], result['rankings'], result['expected_value'], result['action'], result['guardrail']['decision_status'], result['priority'], result['guardrail'], result['reason'], datetime.now(timezone.utc))
        audit(self.session, payment, 'DecisionAgent', 'DECISION', output.reasons, probability=output.recovery_probability, model_version=output.model_version, prediction_source=output.prediction_source, recommended_action=output.recommended_action, decision_status=output.decision_status, expected_recovery_value=output.expected_recovery_value, guardrail=output.guardrail_result)
        return output
