import hashlib,hmac,json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from fastapi.testclient import TestClient
from sqlalchemy import delete,select
from app.main import app,settings,SessionLocal,Event,Payment,Customer,Opportunity,Prediction,InterventionScore,Audit
TEST_SECRET='synthetic-local-webhook-secret'
settings.razorpay_webhook_secret=TEST_SECRET

def signed(payload,secret=None):
 raw=json.dumps(payload,separators=(',',':')).encode(); key=(secret or TEST_SECRET).encode(); return raw,hmac.new(key,raw,hashlib.sha256).hexdigest()
def event(marker,kind='payment.failed'):
 return {'event':kind,'payload':{'payment':{'entity':{'id':'pay_web_'+marker,'order_id':'ord_web_'+marker,'amount':499900,'currency':'INR','method':'card','email':marker+'@example.test','error_description':'synthetic test bank error'}}}}
def payment_link_event(marker):
 return {'event':'payment_link.paid','payload':{'payment_link':{'entity':{'id':'plink_'+marker,'order_id':'order_link_'+marker,'amount':125000,'currency':'INR','customer_details':{'name':'Payment Link Test','email':marker+'@example.test'}}},'order':{'entity':{'id':'order_link_'+marker,'amount':125000,'currency':'INR'}},'payment':{'entity':{'id':'pay_link_'+marker,'order_id':'order_link_'+marker,'amount':125000,'currency':'INR','method':'card','email':marker+'@example.test'}}}}
def cleanup(marker):
 s=SessionLocal();p=s.scalar(select(Payment).where(Payment.external_id=='pay_web_'+marker));
 if p:
  o=s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id));
  if o:
   s.execute(delete(Audit).where(Audit.payment_id==p.external_id));s.execute(delete(InterventionScore).where(InterventionScore.payment_id==p.id));s.execute(delete(Prediction).where(Prediction.payment_id==p.id));s.execute(delete(Opportunity).where(Opportunity.id==o.id))
  s.execute(delete(Payment).where(Payment.id==p.id));s.execute(delete(Customer).where(Customer.id==p.customer_id))
 for e in s.scalars(select(Event).where(Event.payload['event'].as_string()=='payment.failed')).all():
  if marker in json.dumps(e.payload):s.delete(e)
 s.commit();s.close()
def test_webhook_valid_duplicate_and_pipeline():
 marker=uuid.uuid4().hex;cleanup(marker);raw,sig=signed(event(marker));
 try:
  with TestClient(app) as c:
   first=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig});second=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig})
  assert first.status_code==200 and first.json()['status']=='processed';assert second.status_code==200 and second.json()['status']=='duplicate'
  s=SessionLocal();p=s.scalar(select(Payment).where(Payment.external_id=='pay_web_'+marker));assert p and s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id));assert s.scalar(select(Prediction).where(Prediction.payment_id==p.id));assert s.scalar(select(InterventionScore).where(InterventionScore.payment_id==p.id));assert s.scalar(select(Audit).where(Audit.payment_id==p.external_id));s.close()
 finally: cleanup(marker)
def test_webhook_invalid_signature():
 marker=uuid.uuid4().hex;raw,_=signed(event(marker));
 with TestClient(app) as c:r=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':'bad'})
 assert r.status_code==400;cleanup(marker)
def test_webhook_malformed_and_missing_fields():
 with TestClient(app) as c:
  raw=b'{not-json}';sig=hmac.new(TEST_SECRET.encode(),raw,hashlib.sha256).hexdigest();assert c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig}).status_code==400
  raw,sig=signed({'event':'payment.failed','payload':{'payment':{'entity':{}}}});assert c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig}).status_code==400
def test_webhook_unknown_event_is_ignored():
 marker=uuid.uuid4().hex;raw,sig=signed({'event':'subscription.paused','payload':{'subscription':{'entity':{'id':'sub_'+marker}}}})
 with TestClient(app) as c:r=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig})
 assert r.status_code==200 and r.json()['status']=='ignored'
def test_supported_non_failure_events_are_recognized():
 marker=uuid.uuid4().hex
 with TestClient(app) as c:
  for kind,body in [('payment.authorized',{'payment':{'entity':{'id':'pay_unknown_authorized_'+marker,'amount':100,'currency':'INR'}}}),('payment.captured',{'payment':{'entity':{'id':'pay_unknown_captured_'+marker,'amount':100,'currency':'INR'}}}),('order.paid',{'order':{'entity':{'id':'order_local_supported_'+marker}}})]:
   raw,sig=signed({'event':kind,'payload':body});r=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig});assert r.status_code==200 and r.json()['status']=='processed'

def test_payment_link_paid_creates_captured_payment_and_is_idempotent():
 marker=uuid.uuid4().hex;payload=payment_link_event(marker);raw,sig=signed(payload)
 try:
  with TestClient(app) as c:
   first=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig});second=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig})
  assert first.status_code==200 and first.json()['status']=='processed';assert second.status_code==200 and second.json()['status']=='duplicate'
  s=SessionLocal();p=s.scalar(select(Payment).where(Payment.external_id=='pay_link_'+marker));assert p and p.status=='captured' and p.amount==1250
  assert s.scalar(select(Customer).where(Customer.external_id==marker+'@example.test'));assert not s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id));assert s.scalar(select(Event).where(Event.event_type=='payment_link.paid',Event.payload['event'].as_string()=='payment_link.paid'));assert s.query(Payment).filter(Payment.external_id=='pay_link_'+marker).count()==1
  s.close()
 finally:
  s=SessionLocal();p=s.scalar(select(Payment).where(Payment.external_id=='pay_link_'+marker));
  if p:
   s.execute(delete(Payment).where(Payment.id==p.id));s.execute(delete(Customer).where(Customer.external_id==marker+'@example.test'))
  for e in s.scalars(select(Event).where(Event.event_type=='payment_link.paid')).all():
   if marker in json.dumps(e.payload):s.delete(e)
  s.commit();s.close()
