from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class DiagnosisResult:
    payment_id: str
    category: str
    diagnosis: str
    contributing_factors: dict
    confidence: str
    timestamp: datetime

class DiagnosisAgent:
    CATEGORIES = {
        'temporary_bank_error':'temporary_bank_error', 'network_error':'network_error', 'bank_unavailable':'bank_unavailable',
        'insufficient_funds':'insufficient_funds', 'expired_card':'payment_method_error', 'payment_method_error':'payment_method_error',
        'authentication_failure':'authentication_failure', 'card_declined':'card_declined', 'customer_cancelled':'customer_cancelled',
    }
    def __init__(self, session): self.session = session
    def diagnose(self, payment) -> DiagnosisResult:
        from app.main import audit
        raw = payment.failure_reason or 'unknown'
        category = self.CATEGORIES.get(raw, 'unknown')
        diagnosis = f'failure category: {category}' if category != 'unknown' else 'failure category unavailable from stored payment data'
        factors = {'failure_reason': raw, 'payment_method': payment.method or 'unknown', 'retry_count': int(payment.retry_count or 0)}
        result = DiagnosisResult(payment.external_id, category, diagnosis, factors, 'AVAILABLE' if category != 'unknown' else 'UNAVAILABLE', datetime.now(timezone.utc))
        audit(self.session, payment, 'DiagnosisAgent', 'DIAGNOSIS', diagnosis, category=category, factors=factors, confidence=result.confidence)
        return result
