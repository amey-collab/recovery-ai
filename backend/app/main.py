from __future__ import annotations
import hashlib, hmac, json, os, uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=Path(__file__).resolve().parents[2]/'.env', extra='ignore')
    app_env:str='development'; database_url:str='sqlite:///./recoverai.db'; secret_key:str=''; cors_origins:str='http://localhost:5173'; razorpay_mode:str='test'
    razorpay_key_id:str=''; razorpay_key_secret:str=''; razorpay_webhook_secret:str=''; openai_api_key:str=''; openai_model:str='gpt-4.1-mini'
    @model_validator(mode='after')
    def validate_security_settings(self):
        if self.app_env.lower() in {'production','staging'} and (len(self.secret_key) < 32 or self.secret_key in {'development-change-me','change-me-before-production'}):
            raise ValueError('A strong SECRET_KEY of at least 32 characters is required outside development')
        if '*' in [x.strip() for x in self.cors_origins.split(',')] and self.app_env.lower() in {'production','staging'}:
            raise ValueError('Wildcard CORS origins are not allowed outside development')
        return self
settings=Settings()
engine=create_engine(settings.database_url, connect_args={'check_same_thread':False} if settings.database_url.startswith('sqlite') else {})
SessionLocal=sessionmaker(bind=engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class Role(str,Enum): ADMIN='ADMIN'; ANALYST='ANALYST'; OPERATOR='OPERATOR'; VIEWER='VIEWER'
class State(str,Enum): DETECTED='DETECTED'; ANALYZING='ANALYZING'; PREDICTED='PREDICTED'; RECOMMENDED='RECOMMENDED'; GUARDRAIL_CHECK='GUARDRAIL_CHECK'; AUTO_APPROVED='AUTO_APPROVED'; HUMAN_REVIEW='HUMAN_REVIEW'; EXECUTING='EXECUTING'; SUCCESS='SUCCESS'; FAILED='FAILED'; STOPPED='STOPPED'; EXPIRED='EXPIRED'
class User(Base):
    __tablename__='users'; id:Mapped[int]=mapped_column(primary_key=True); email:Mapped[str]=mapped_column(String(255),unique=True,index=True); password_hash:Mapped[str]; role:Mapped[str]=mapped_column(default=Role.ADMIN.value); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Customer(Base):
    __tablename__='customers'; id:Mapped[int]=mapped_column(primary_key=True); external_id:Mapped[str]=mapped_column(unique=True,index=True); name:Mapped[str]; email:Mapped[str]; lifetime_value:Mapped[float]=mapped_column(default=0); success_rate:Mapped[float]=mapped_column(default=.5)
class Payment(Base):
    __tablename__='payments'; id:Mapped[int]=mapped_column(primary_key=True); external_id:Mapped[str]=mapped_column(unique=True,index=True); customer_id:Mapped[int|None]=mapped_column(ForeignKey('customers.id')); order_id:Mapped[str|None]=mapped_column(index=True); amount:Mapped[float]; currency:Mapped[str]=mapped_column(default='INR'); method:Mapped[str]=mapped_column(default='card'); status:Mapped[str]=mapped_column(index=True); failure_reason:Mapped[str|None]=None; retry_count:Mapped[int]=mapped_column(default=0); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc),index=True); customer:Mapped[Customer|None]=relationship()
class Event(Base):
    __tablename__='payment_events'; id:Mapped[int]=mapped_column(primary_key=True); event_hash:Mapped[str]=mapped_column(unique=True,index=True); event_type:Mapped[str]=mapped_column(index=True); payload:Mapped[dict]=mapped_column(JSON); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Opportunity(Base):
    __tablename__='recovery_opportunities'; id:Mapped[int]=mapped_column(primary_key=True); payment_id:Mapped[int]=mapped_column(ForeignKey('payments.id'),unique=True); state:Mapped[str]=mapped_column(default=State.DETECTED.value,index=True); priority:Mapped[str]=mapped_column(default='LOW'); expected_value:Mapped[float]=mapped_column(default=0); recommended_action:Mapped[str|None]=None; guardrail_result:Mapped[dict]=mapped_column(JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc)); payment:Mapped[Payment]=relationship()
class Prediction(Base):
    __tablename__='ml_predictions'; id:Mapped[int]=mapped_column(primary_key=True); payment_id:Mapped[int]=mapped_column(ForeignKey('payments.id'),index=True); probability:Mapped[float]; model_version:Mapped[str]; factors:Mapped[dict]=mapped_column(JSON); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class RecoveryAction(Base):
    __tablename__='recovery_actions'; id:Mapped[int]=mapped_column(primary_key=True); opportunity_id:Mapped[int]=mapped_column(ForeignKey('recovery_opportunities.id'),index=True); action:Mapped[str]; status:Mapped[str]; simulated:Mapped[bool]=mapped_column(default=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Outcome(Base):
    __tablename__='recovery_outcomes'; id:Mapped[int]=mapped_column(primary_key=True); action_id:Mapped[int]=mapped_column(ForeignKey('recovery_actions.id')); success:Mapped[bool]; amount:Mapped[float]; occurred_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Audit(Base):
    __tablename__='audit_logs'; id:Mapped[int]=mapped_column(primary_key=True); actor:Mapped[str]; agent:Mapped[str]; payment_id:Mapped[str]; action:Mapped[str]; reason:Mapped[str]; details:Mapped[dict]=mapped_column(JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc),index=True)
class ModelVersion(Base):
    __tablename__='model_versions'; id:Mapped[int]=mapped_column(primary_key=True); version:Mapped[str]=mapped_column(unique=True); training_timestamp:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc)); dataset_version:Mapped[str]; feature_version:Mapped[str]; metrics:Mapped[dict]=mapped_column(JSON)
class InterventionScore(Base):
    __tablename__='intervention_scores'; id:Mapped[int]=mapped_column(primary_key=True); payment_id:Mapped[int]=mapped_column(ForeignKey('payments.id'),index=True); scores:Mapped[dict]=mapped_column(JSON); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
def db():
    s=SessionLocal()
    try: yield s
    finally:s.close()
pwd=CryptContext(schemes=['bcrypt'],deprecated='auto'); oauth=OAuth2PasswordBearer(tokenUrl='/api/auth/login')
def audit(s:Session,p:Payment,agent:str,action:str,reason:str,**details): s.add(Audit(actor='system',agent=agent,payment_id=p.external_id,action=action,reason=reason,details=details))
def current(token:str=Depends(oauth),s:Session=Depends(db)):
    try: email=jwt.decode(token,settings.secret_key,algorithms=['HS256'])['sub']
    except JWTError: raise HTTPException(401,'Invalid authentication token')
    u=s.scalar(select(User).where(User.email==email))
    if not u: raise HTTPException(401,'User not found')
    return u
def authorize(*roles):
    def dep(u:User=Depends(current)):
        if u.role not in roles: raise HTTPException(403,'Insufficient role')
        return u
    return dep
def validate_password_bytes(value:str)->str:
    if len(value.encode('utf-8'))>72:
        raise ValueError('password must be 72 UTF-8 bytes or fewer')
    return value
class Register(BaseModel):
    email:EmailStr
    password:str=Field(min_length=8)
    _password_limit=field_validator('password')(validate_password_bytes)
class Login(BaseModel):
    email:EmailStr
    password:str
    _password_limit=field_validator('password')(validate_password_bytes)
class PaymentIn(BaseModel): amount:float=Field(gt=0); currency:str='INR'; receipt:str|None=None; customer_name:str='Test customer'; customer_email:EmailStr
class RazorpayService:
    def client(self):
        if settings.razorpay_mode.lower() != 'test' or settings.razorpay_key_id.startswith('rzp_live_'): raise HTTPException(503,'Only Razorpay Test Mode is permitted')
        if not(settings.razorpay_key_id and settings.razorpay_key_secret): raise HTTPException(503,'Razorpay Test Mode credentials are not configured')
        import razorpay; return razorpay.Client(auth=(settings.razorpay_key_id,settings.razorpay_key_secret))
    def create_order(self,amount,currency,receipt): return self.client().order.create({'amount':round(amount*100),'currency':currency,'receipt':receipt[:40]})
    def fetch_payment(self,payment_id): return self.client().payment.fetch(payment_id)
razorpay_service=RazorpayService()
class GuardrailEngine:
    MAX_AUTO=10000; MAX_RETRIES=2; MIN_PROB=.35; COOLDOWN_MINUTES=60
    def check(self,s:Session,p:Payment,prob:float,action:str):
        reasons=[]
        if p.retry_count>=self.MAX_RETRIES and action=='RETRY': return {'pass':False,'decision_status':'BLOCKED','reasons':['maximum retry count reached']}
        if prob<self.MIN_PROB: return {'pass':False,'decision_status':'NO_ACTION','reasons':['below confidence threshold']}
        recent=s.scalar(select(RecoveryAction).join(Opportunity,RecoveryAction.opportunity_id==Opportunity.id).where(Opportunity.payment_id==p.id,RecoveryAction.created_at>=datetime.now(timezone.utc)-timedelta(minutes=self.COOLDOWN_MINUTES)))
        if recent:return {'pass':False,'decision_status':'BLOCKED','reasons':['recovery cooldown active']}
        if p.amount>self.MAX_AUTO:return {'pass':False,'decision_status':'HUMAN_REVIEW','reasons':['amount exceeds automatic recovery limit']}
        if action=='NO_ACTION':return {'pass':False,'decision_status':'NO_ACTION','reasons':['no positive intervention value']}
        return {'pass':True,'decision_status':'AUTO_APPROVED','reasons':['amount within limit','retry limit not reached','confidence threshold passed','cooldown clear']}
guardrails=GuardrailEngine()
def prediction_service(s:Session,p:Payment):
    """Loads a persisted model only; never trains in a request path."""
    artifact_path=Path(__file__).resolve().parents[2]/'ml'/'models'/'recovery_probability_model.joblib'
    if not artifact_path.exists(): return None,'artifact unavailable','fallback'
    try:
        import joblib
        artifact=joblib.load(artifact_path)
        metadata=json.loads((artifact_path.parent/'recovery_metrics.json').read_text())
    except Exception as exc:
        return None,f'artifact error: {type(exc).__name__}','fallback'
    from app.feature_builder import FeatureBuilder
    features=FeatureBuilder(s).dataframe(p)
    probability=float(artifact['model'].predict_proba(artifact['preprocessor'].transform(features[artifact['feature_columns']]))[0,1])
    return probability,f"{metadata.get('dataset_version','unknown')}-{metadata.get('feature_version','unknown')}",'model'
def model_probability(s:Session,p:Payment): return prediction_service(s,p)[0]
def intervention_ranking(p:Payment,prob:float):
    path=Path(__file__).resolve().parents[2]/'ml'/'models'/'intervention_effectiveness.json'; raw=json.loads(path.read_text()) if path.exists() else {}
    names={'RETRY':'retry','REMINDER':'reminder','ALTERNATIVE_PAYMENT_METHOD':'alternative_payment_method','CUSTOMER_NOTIFICATION':'customer_notification','HUMAN_ESCALATION':'human_escalation','NO_ACTION':'no_action'}; temporary=any(x in (p.failure_reason or '').lower() for x in ['bank','network','temporary'])
    costs={'RETRY':5,'REMINDER':2,'ALTERNATIVE_PAYMENT_METHOD':3,'CUSTOMER_NOTIFICATION':1,'HUMAN_ESCALATION':100,'NO_ACTION':0}; out={}
    for action,key in names.items():
        effectiveness=float(raw.get(key,{}).get('effectiveness',0.0)); context=1.0
        if action=='RETRY' and temporary: context*=1.12
        if action=='ALTERNATIVE_PAYMENT_METHOD' and 'expired' in (p.failure_reason or '').lower(): context*=1.12
        if action=='HUMAN_ESCALATION' and p.amount>guardrails.MAX_AUTO: context*=1.08
        out[action]={'effectiveness':round(effectiveness*context,4),'expected_recovery_value':round(prob*p.amount*effectiveness*context-costs[action],2),'cost':costs[action]}
    return out
def decision_engine(s:Session,p:Payment):
    c=p.customer; temporary=any(x in (p.failure_reason or '').lower() for x in ['bank','network','timeout','temporary'])
    prob,version,source=prediction_service(s,p); fallback=.28+.34*(c.success_rate if c else .5)+(.18 if temporary else 0)-.12*p.retry_count
    prob=max(.03,min(.97,fallback)) if prob is None else prob; rankings=intervention_ranking(p,prob);action=max(rankings,key=lambda a:rankings[a]['expected_recovery_value']);g=guardrails.check(s,p,prob,action);expected=rankings[action]['expected_recovery_value']; priority='HIGH' if expected>=5000 or (prob>=.7 and p.amount>=5000) else 'MEDIUM' if expected>=1000 else 'LOW'; reasons=['Factors influencing the prediction: customer payment history, retry count, failure category, transaction amount, and customer value.',f'Recommended action maximizes Expected Recovery Value ({expected:.2f}).']+g['reasons'];return {'probability':prob,'model_version':version,'source':source,'action':action,'rankings':rankings,'guardrail':g,'expected_value':expected,'priority':priority,'reason':' '.join(reasons)}
class LLMService:
    """Optional explanation provider. It is deliberately absent from financial decisions."""
    def explain(self, payment:Payment, probability:float, action:str)->str:
        return f"Factors influencing the prediction include payment history, retry count, failure reason, and customer value. Recommended action: {action}; predicted recoverability: {probability:.0%}."
llm=LLMService()
def pipeline(s:Session,p:Payment):
    opp=s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id))
    if opp:return opp
    from app.agents.orchestrator import RecoveryOrchestrator
    orchestration=RecoveryOrchestrator(s).assess(p)
    if not orchestration.detection.detected or not orchestration.decision: return None
    d=orchestration.decision; factors={'customer_success_rate':p.customer.success_rate if p.customer else .5,'retry_count':p.retry_count,'failure_reason':p.failure_reason or 'unknown','decision_reason':d.reasons,'prediction_source':d.prediction_source};s.add(Prediction(payment_id=p.id,probability=d.recovery_probability,model_version=d.model_version,factors=factors));s.add(InterventionScore(payment_id=p.id,scores=d.intervention_rankings));opp=Opportunity(payment_id=p.id,state=d.decision_status,priority=d.priority,expected_value=d.expected_recovery_value,recommended_action=d.recommended_action,guardrail_result=d.guardrail_result);s.add(opp);return opp
app=FastAPI(title='RecoverAI',version='1.0.0'); app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins.split(','),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@app.on_event('startup')
def startup():
    # Production schema changes are applied by Alembic, never implicitly here.
    if settings.app_env.lower() in {'development','test'}:
        Base.metadata.create_all(engine)
@app.get('/health')
def health(): return {'status':'ok','mode':settings.database_url.split(':')[0],'razorpay_configured':bool(settings.razorpay_key_id)}
@app.post('/api/auth/register')
def register(x:Register,s:Session=Depends(db)):
    if s.scalar(select(User).where(User.email==x.email)): raise HTTPException(409,'Email already registered')
    role=Role.ADMIN.value if not s.scalar(select(User.id)) else Role.VIEWER.value
    u=User(email=x.email,password_hash=pwd.hash(x.password),role=role);s.add(u);s.commit();return {'id':u.id,'email':u.email,'role':u.role}
@app.post('/api/auth/login')
def login(x:Login,s:Session=Depends(db)):
    u=s.scalar(select(User).where(User.email==x.email))
    if not u or not pwd.verify(x.password,u.password_hash): raise HTTPException(401,'Invalid credentials')
    return {'access_token':jwt.encode({'sub':u.email,'exp':datetime.now(timezone.utc)+timedelta(hours=8)},settings.secret_key,algorithm='HS256'),'token_type':'bearer'}
@app.get('/api/auth/me')
def me(u:User=Depends(current)): return {'id':u.id,'email':u.email,'role':u.role}
@app.get('/api/payments')
def payments(s:Session=Depends(db),u:User=Depends(current)): return [{'payment_id':p.external_id,'amount':p.amount,'status':p.status,'method':p.method,'failure_reason':p.failure_reason} for p in s.scalars(select(Payment).order_by(Payment.created_at.desc())).all()]
@app.get('/api/payments/failed')
def failed(s:Session=Depends(db),u:User=Depends(current)): return [p.external_id for p in s.scalars(select(Payment).where(Payment.status=='failed')).all()]
@app.get('/api/payments/{payment_id}')
def payment_detail(payment_id:str,s:Session=Depends(db),u:User=Depends(current)):
    p=s.scalar(select(Payment).where(Payment.external_id==payment_id))
    if not p: raise HTTPException(404,'Payment not found')
    pred=s.scalar(select(Prediction).where(Prediction.payment_id==p.id).order_by(Prediction.created_at.desc()))
    opp=s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id))
    scores=s.scalar(select(InterventionScore).where(InterventionScore.payment_id==p.id).order_by(InterventionScore.created_at.desc()));return {'payment_id':p.external_id,'amount':p.amount,'currency':p.currency,'status':p.status,'failure_reason':p.failure_reason,'customer':{'id':p.customer.external_id if p.customer else None,'success_rate':p.customer.success_rate if p.customer else None},'prediction':{'probability':pred.probability,'factors':pred.factors,'model_version':pred.model_version} if pred else None,'intervention_scores':scores.scores if scores else {},'opportunity':{'id':opp.id,'state':opp.state,'action':opp.recommended_action,'expected_recovery_value':opp.expected_value,'priority':opp.priority,'guardrail':opp.guardrail_result} if opp else None}
@app.get('/api/recovery/opportunities')
def opportunities(s:Session=Depends(db),u:User=Depends(current)): return [{'id':o.id,'payment_id':o.payment.external_id,'customer_id':o.payment.customer.external_id if o.payment.customer else None,'amount':o.payment.amount,'failure_reason':o.payment.failure_reason,'state':o.state,'priority':o.priority,'recommended_action':o.recommended_action,'expected_recovery_value':o.expected_value,'guardrail':o.guardrail_result,'probability':s.scalar(select(Prediction.probability).where(Prediction.payment_id==o.payment_id).order_by(Prediction.created_at.desc()))} for o in s.scalars(select(Opportunity).order_by(Opportunity.expected_value.desc())).all()]
@app.get('/api/recovery/opportunities/{oid}')
def opportunity_detail(oid:int,s:Session=Depends(db),u:User=Depends(current)):
    o=s.get(Opportunity,oid)
    if not o:raise HTTPException(404,'Opportunity not found')
    pred=s.scalar(select(Prediction).where(Prediction.payment_id==o.payment_id).order_by(Prediction.created_at.desc()));scores=s.scalar(select(InterventionScore).where(InterventionScore.payment_id==o.payment_id).order_by(InterventionScore.created_at.desc()))
    return {'id':o.id,'payment_id':o.payment.external_id,'state':o.state,'priority':o.priority,'recommended_action':o.recommended_action,'expected_recovery_value':o.expected_value,'guardrail':o.guardrail_result,'prediction':{'probability':pred.probability,'model_version':pred.model_version,'factors':pred.factors} if pred else None,'intervention_scores':scores.scores if scores else {}}
@app.post('/api/recovery/{oid}/approve')
def approve(oid:int,s:Session=Depends(db),u:User=Depends(authorize(Role.ADMIN.value,Role.OPERATOR.value))):
    o=s.get(Opportunity,oid)
    if not o:raise HTTPException(404,'Opportunity not found')
    if o.state!=State.HUMAN_REVIEW.value: raise HTTPException(409,'Only HUMAN_REVIEW opportunities can be approved')
    o.state=State.AUTO_APPROVED.value;audit(s,o.payment,'Human','APPROVED','human approval');s.commit();return {'state':o.state}
@app.post('/api/recovery/{oid}/reject')
def reject(oid:int,s:Session=Depends(db),u:User=Depends(authorize(Role.ADMIN.value,Role.OPERATOR.value))):
    o=s.get(Opportunity,oid)
    if not o:raise HTTPException(404,'Opportunity not found')
    o.state=State.STOPPED.value;audit(s,o.payment,'Human','REJECTED','human rejected recommendation');s.commit();return {'state':o.state}
@app.post('/api/recovery/{oid}/execute')
def execute(oid:int,s:Session=Depends(db),u:User=Depends(authorize(Role.ADMIN.value,Role.OPERATOR.value))):
    o=s.get(Opportunity,oid)
    if not o:raise HTTPException(404,'Opportunity not found')
    if o.state!=State.AUTO_APPROVED.value:raise HTTPException(409,'Approval required before execution')
    try:
        from app.agents.execution_agent import ExecutionAgent
        a,result=ExecutionAgent(s,u.role).execute(o);s.commit();return {'action_id':a.id,'status':a.status,'outcome_status':result.status.value,'simulation':True,'recovered_amount':result.recovered_amount}
    except (PermissionError,ValueError) as exc: raise HTTPException(409,str(exc))
@app.get('/api/predictions/{pid}')
def prediction(pid:str,s:Session=Depends(db),u:User=Depends(current)):
    p=s.scalar(select(Payment).where(Payment.external_id==pid)); x=s.scalar(select(Prediction).where(Prediction.payment_id==p.id).order_by(Prediction.created_at.desc())) if p else None
    if not x:raise HTTPException(404,'Prediction not found')
    scores=s.scalar(select(InterventionScore).where(InterventionScore.payment_id==p.id).order_by(InterventionScore.created_at.desc()));return {'probability':x.probability,'model_version':x.model_version,'factors':x.factors,'interventions':scores.scores if scores else {}}
@app.post('/api/predictions/{pid}/run')
def run_prediction(pid:str,s:Session=Depends(db),u:User=Depends(authorize(Role.ADMIN.value,Role.OPERATOR.value))):
    p=s.scalar(select(Payment).where(Payment.external_id==pid))
    if not p:raise HTTPException(404,'Payment not found')
    if p.status!='failed':raise HTTPException(409,'Only failed payments are eligible for recovery prediction')
    existing=s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id))
    if existing: return opportunity_detail(existing.id,s,u)
    pipeline(s,p);s.commit();return opportunity_detail(s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id)).id,s,u)
@app.get('/api/analytics/overview')
def overview(s:Session=Depends(db),u:User=Depends(current)):
    risk=s.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.status=='failed')); expected=s.scalar(select(func.coalesce(func.sum(Opportunity.expected_value),0))); recovered=s.scalar(select(func.coalesce(func.sum(Outcome.amount),0)).where(Outcome.success==True)); actions=s.scalar(select(func.count(RecoveryAction.id))); successes=s.scalar(select(func.count(Outcome.id)).where(Outcome.success==True))
    return {'synthetic_demo':True,'revenue_at_risk':risk,'recovery_opportunity':expected,'recovered_revenue':recovered,'recovery_rate':round(recovered/risk,4) if risk else 0,'intervention_success_rate':round(successes/actions,4) if actions else 0,'active_actions':actions}
@app.get('/api/analytics/recovery')
def recovery_analytics(s:Session=Depends(db),u:User=Depends(current)): return overview(s,u)
@app.get('/api/analytics/revenue-at-risk')
def revenue_at_risk(s:Session=Depends(db),u:User=Depends(current)): return {'amount':s.scalar(select(func.coalesce(func.sum(Payment.amount),0)).where(Payment.status=='failed'))}
@app.get('/api/analytics/interventions')
def interventions(s:Session=Depends(db),u:User=Depends(current)):
    rows=s.execute(select(RecoveryAction.action,func.count(RecoveryAction.id),func.coalesce(func.sum(Outcome.amount),0)).outerjoin(Outcome,Outcome.action_id==RecoveryAction.id).group_by(RecoveryAction.action)).all();return [{'action':a,'attempts':n,'recovered_revenue':v} for a,n,v in rows]
@app.get('/api/agents/activity')
def agent_activity(s:Session=Depends(db),u:User=Depends(current)): return logs(s,u)
@app.get('/api/agents/decisions')
def agent_decisions(s:Session=Depends(db),u:User=Depends(current)): return [x for x in logs(s,u) if x['agent']=='DecisionAgent']
@app.get('/api/audit-logs')
def logs(s:Session=Depends(db),u:User=Depends(current)): return [{'timestamp':x.created_at,'agent':x.agent,'payment_id':x.payment_id,'action':x.action,'reason':x.reason,'details':x.details} for x in s.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200)).all()]
@app.post('/api/razorpay/orders')
def create_order(x:PaymentIn,u:User=Depends(authorize(Role.ADMIN.value,Role.OPERATOR.value))): return razorpay_service.create_order(x.amount,x.currency,x.receipt or f'rai_{uuid.uuid4().hex[:20]}')
@app.post('/api/webhooks/razorpay',status_code=200)
async def webhook(request:Request,s:Session=Depends(db)):
    raw=await request.body(); signature=request.headers.get('X-Razorpay-Signature','')
    if not settings.razorpay_webhook_secret: raise HTTPException(503,'Webhook secret is not configured')
    expected=hmac.new(settings.razorpay_webhook_secret.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature): raise HTTPException(400,'Invalid webhook signature')
    try: payload=json.loads(raw)
    except (json.JSONDecodeError,UnicodeDecodeError): raise HTTPException(400,'Malformed JSON webhook payload')
    if not isinstance(payload,dict): raise HTTPException(400,'Webhook payload must be a JSON object')
    event_type=payload.get('event',''); event_hash=hashlib.sha256(raw).hexdigest()
    supported={'payment.failed','payment.authorized','payment.captured','order.paid'}
    if not event_type: raise HTTPException(400,'Missing webhook event type')
    if s.scalar(select(Event).where(Event.event_hash==event_hash)): return {'status':'duplicate'}
    s.add(Event(event_hash=event_hash,event_type=event_type,payload=payload)); container=payload.get('payload') or {}; entity=(container.get('payment') or {}).get('entity') or {}; order_entity=(container.get('order') or {}).get('entity') or {}
    if event_type not in supported:
        s.commit(); return {'status':'ignored','event':event_type}
    if event_type.startswith('payment.'):
        if not entity.get('id'): raise HTTPException(400,'Missing payment entity id')
        if event_type in {'payment.failed','payment.authorized','payment.captured'} and entity.get('amount') is None: raise HTTPException(400,'Missing payment amount')
    if event_type=='payment.failed':
        ext=entity.get('id'); p=s.scalar(select(Payment).where(Payment.external_id==ext))
        if not p:
            c=Customer(external_id=entity.get('email') or f'anon-{ext}',name=entity.get('email','Unknown'),email=entity.get('email','unknown@example.invalid'));s.add(c);s.flush();p=Payment(external_id=ext,customer_id=c.id,order_id=entity.get('order_id'),amount=entity.get('amount',0)/100,currency=entity.get('currency','INR'),method=entity.get('method','unknown'),status='failed',failure_reason=entity.get('error_description'));s.add(p);s.flush()
        else:
            p.status='failed';p.failure_reason=entity.get('error_description') or p.failure_reason;p.retry_count=p.retry_count or 0
        pipeline(s,p)
    elif event_type in {'payment.authorized','payment.captured'}:
        p=s.scalar(select(Payment).where(Payment.external_id==entity['id']))
        if p:
            p.status='authorized' if event_type.endswith('authorized') else 'captured'
            if event_type=='payment.captured':
                from app.outcome_service import OutcomeService, OutcomeStatus
                opportunity=s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id)); action=s.scalar(select(RecoveryAction).where(RecoveryAction.opportunity_id==opportunity.id).order_by(RecoveryAction.created_at.desc())) if opportunity else None
                if action and not action.simulated and not s.scalar(select(Outcome).where(Outcome.action_id==action.id)):
                    OutcomeService(s).record(action,OutcomeStatus.SUCCESS,recovered_amount=min(float(entity['amount'])/100,float(p.amount)),execution_mode='RAZORPAY_TEST')
    elif event_type=='order.paid' and not order_entity.get('id'):
        raise HTTPException(400,'Missing order entity id')
    s.commit();return {'status':'processed','event':event_type}
