import sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from app.main import Base,engine,Customer,Payment,GuardrailEngine,SessionLocal,pipeline,Prediction,InterventionScore
Base.metadata.create_all(engine)
def make(amount=4999,retries=0,success=.9,reason='temporary_bank_error'):
 s=SessionLocal();z=uuid.uuid4().hex;c=Customer(external_id='c'+z,name='T',email=z+'@example.test',success_rate=success,lifetime_value=30000);s.add(c);s.flush();p=Payment(external_id='p'+z,customer_id=c.id,amount=amount,status='failed',failure_reason=reason,retry_count=retries);s.add(p);s.flush();return s,p
def test_high_probability_low_amount_auto_approved():
 s,p=make();o=pipeline(s,p);s.flush();assert o.state=='AUTO_APPROVED';assert s.scalar(__import__('sqlalchemy').select(Prediction).where(Prediction.payment_id==p.id));assert s.scalar(__import__('sqlalchemy').select(InterventionScore).where(InterventionScore.payment_id==p.id));s.rollback();s.close()
def test_high_value_requires_human_review():
 s,p=make(amount=20000);o=pipeline(s,p);assert o.state=='HUMAN_REVIEW';s.rollback();s.close()
def test_retries_are_blocked():
 s,p=make(retries=2);o=pipeline(s,p);assert o.state=='BLOCKED';s.rollback();s.close()
def test_low_probability_no_action():
 s,p=make(success=.05,retries=1,reason='customer_cancelled');assert GuardrailEngine().check(s,p,.1,'RETRY')['decision_status']=='NO_ACTION';s.rollback();s.close()
def test_duplicate_pipeline_is_idempotent():
 s,p=make();a=pipeline(s,p);s.flush();b=pipeline(s,p);assert a.id==b.id;s.rollback();s.close()
