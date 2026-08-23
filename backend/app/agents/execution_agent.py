from __future__ import annotations

class ExecutionAgent:
    def __init__(self, session, actor_role: str):
        self.session = session; self.actor_role = actor_role
    def execute(self, opportunity):
        from sqlalchemy import select
        from app.main import Payment, RecoveryAction, State, audit, guardrails
        from app.outcome_service import OutcomeStatus
        from app.agents.outcome_agent import OutcomeAgent
        if self.actor_role not in {'ADMIN','OPERATOR'}: raise PermissionError('execution role is not permitted')
        if self.session.scalar(select(RecoveryAction).where(RecoveryAction.opportunity_id==opportunity.id)):
            raise ValueError('duplicate recovery execution blocked')
        if opportunity.state != State.AUTO_APPROVED.value: raise ValueError('only AUTO_APPROVED opportunities can execute')
        payment = self.session.get(Payment, opportunity.payment_id)
        prediction = self.session.scalar(select(__import__('app.main', fromlist=['Prediction']).Prediction).where(__import__('app.main', fromlist=['Prediction']).Prediction.payment_id==payment.id).order_by(__import__('app.main', fromlist=['Prediction']).Prediction.created_at.desc()))
        if not prediction: raise ValueError('execution requires a persisted prediction')
        check = guardrails.check(self.session, payment, prediction.probability, opportunity.recommended_action)
        if check['decision_status'] != State.AUTO_APPROVED.value: raise ValueError(f'guardrail rejected execution: {check["decision_status"]}')
        action = RecoveryAction(opportunity_id=opportunity.id, action=opportunity.recommended_action, status='SIMULATED_TEST_RECOVERY', simulated=True)
        self.session.add(action); self.session.flush(); opportunity.state=State.EXECUTING.value
        audit(self.session, payment, 'ExecutionAgent', 'EXECUTION', 'approved recovery action execution started', execution_mode='SIMULATED', intervention_action=action.action)
        result=OutcomeAgent(self.session).record(action, OutcomeStatus.SIMULATED, execution_mode='SIMULATED')
        return action, result
