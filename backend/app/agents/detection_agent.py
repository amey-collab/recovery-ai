from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class DetectionResult:
    detected: bool
    payment_id: str
    opportunity_type: str
    reason: str
    timestamp: datetime

class DetectionAgent:
    def __init__(self, session): self.session = session
    def detect(self, payment, event_type: str = 'payment.failed') -> DetectionResult:
        from app.main import audit
        detected = payment.status == 'failed' and event_type == 'payment.failed'
        reason = 'failed payment is eligible for recovery analysis' if detected else 'payment/event is not an eligible failed payment'
        result = DetectionResult(detected, payment.external_id, 'PAYMENT_RECOVERY' if detected else 'NONE', reason, datetime.now(timezone.utc))
        audit(self.session, payment, 'DetectionAgent', 'DETECTION', reason, detected=detected, opportunity_type=result.opportunity_type, event_type=event_type)
        return result
