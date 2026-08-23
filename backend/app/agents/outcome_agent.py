from __future__ import annotations

class OutcomeAgent:
    def __init__(self, session): self.session = session
    def record(self, action, status, **kwargs):
        from app.main import Opportunity, Payment, audit
        from app.outcome_service import OutcomeService
        opportunity=self.session.get(Opportunity, action.opportunity_id); payment=self.session.get(Payment, opportunity.payment_id)
        audit(self.session, payment, 'OutcomeAgent', 'OUTCOME', 'outcome agent invoked', requested_status=status.value if hasattr(status,'value') else str(status))
        return OutcomeService(self.session).record(action, status, **kwargs)
