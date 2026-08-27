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
def payment_link_failed_event(marker,email='reuse@example.test'):
 return {'event':'payment.failed','payload':{'payment':{'entity':{'id':'pay_plinkfail_'+marker,'order_id':'order_plink_'+marker,'amount':250000,'currency':'INR','status':'failed','method':'card','email':email,'error_description':'Payment failed','error_reason':'payment_failed','notes':[]}},'payment_link':{'entity':{'id':'plink_'+marker,'order_id':'order_plink_'+marker,'amount':250000,'currency':'INR','customer_details':{'name':'Link Customer','email':email}}}}}
def cleanup_ext(ext,email=None):
 s=SessionLocal();p=s.scalar(select(Payment).where(Payment.external_id==ext))
 if p:
  o=s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id))
  if o:
   s.execute(delete(Audit).where(Audit.payment_id==p.external_id));s.execute(delete(InterventionScore).where(InterventionScore.payment_id==p.id));s.execute(delete(Prediction).where(Prediction.payment_id==p.id));s.execute(delete(Opportunity).where(Opportunity.id==o.id))
  cid=p.customer_id;s.execute(delete(Payment).where(Payment.id==p.id))
  if cid and not s.scalar(select(Payment).where(Payment.customer_id==cid)): s.execute(delete(Customer).where(Customer.id==cid))
 elif email:
  c=s.scalar(select(Customer).where(Customer.external_id==email))
  if c and not s.scalar(select(Payment).where(Payment.customer_id==c.id)): s.execute(delete(Customer).where(Customer.id==c.id))
 for e in s.scalars(select(Event)).all():
  if ext in json.dumps(e.payload): s.delete(e)
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

def test_webhook_missing_signature_is_400():
 marker=uuid.uuid4().hex;raw,_=signed(event(marker))
 with TestClient(app) as c:r=c.post('/api/webhooks/razorpay',content=raw)
 assert r.status_code==400

def test_payment_link_failed_creates_opportunity():
 marker=uuid.uuid4().hex;email=marker+'@example.test';raw,sig=signed(payment_link_failed_event(marker,email))
 try:
  with TestClient(app) as c:
   r=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig})
  assert r.status_code==200 and r.json()['status']=='processed'
  s=SessionLocal();p=s.scalar(select(Payment).where(Payment.external_id=='pay_plinkfail_'+marker))
  assert p and p.status=='failed' and p.amount==2500 and p.failure_reason=='Payment failed'
  assert s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id));assert s.scalar(select(Customer).where(Customer.external_id==email));s.close()
 finally: cleanup_ext('pay_plinkfail_'+marker,email)

def test_repeated_failed_payment_links_reuse_customer():
 email='shared-link@example.test'; m1,m2=uuid.uuid4().hex,uuid.uuid4().hex
 try:
  with TestClient(app) as c:
   for marker in (m1,m2):
    raw,sig=signed(payment_link_failed_event(marker,email));r=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig})
    assert r.status_code==200 and r.json()['status']=='processed'
  s=SessionLocal();p1=s.scalar(select(Payment).where(Payment.external_id=='pay_plinkfail_'+m1));p2=s.scalar(select(Payment).where(Payment.external_id=='pay_plinkfail_'+m2))
  assert p1 and p2 and p1.customer_id==p2.customer_id
  assert s.scalar(select(Opportunity).where(Opportunity.payment_id==p1.id));assert s.scalar(select(Opportunity).where(Opportunity.payment_id==p2.id));s.close()
 finally:
  cleanup_ext('pay_plinkfail_'+m1,email);cleanup_ext('pay_plinkfail_'+m2,email)

def test_payment_failed_null_email_and_notes_list():
 marker=uuid.uuid4().hex;payload=event(marker);payload['payload']['payment']['entity']['email']=None;payload['payload']['payment']['entity']['notes']=[]
 raw,sig=signed(payload)
 try:
  with TestClient(app) as c:r=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig})
  assert r.status_code==200 and r.json()['status']=='processed'
  s=SessionLocal();p=s.scalar(select(Payment).where(Payment.external_id=='pay_web_'+marker));assert p and p.status=='failed' and s.scalar(select(Opportunity).where(Opportunity.payment_id==p.id));s.close()
 finally: cleanup(marker)

def test_payment_failed_amount_fallback_from_payment_link():
 marker=uuid.uuid4().hex;email=marker+'@example.test'
 payload={'event':'payment.failed','payload':{'payment':{'entity':{'id':'pay_plinkfail_'+marker,'currency':'INR','status':'failed','method':'upi','email':email,'error_reason':'payment_failed'}},'payment_link':{'entity':{'id':'plink_'+marker,'amount':9900,'currency':'INR','customer_details':{'email':email}}}}}
 raw,sig=signed(payload)
 try:
  with TestClient(app) as c:r=c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig})
  assert r.status_code==200 and r.json()['status']=='processed'
  s=SessionLocal();p=s.scalar(select(Payment).where(Payment.external_id=='pay_plinkfail_'+marker));assert p and p.amount==99 and p.status=='failed';s.close()
 finally: cleanup_ext('pay_plinkfail_'+marker,email)

def test_payments_and_sync_include_new_failed_payment():
 from datetime import datetime,timedelta,timezone
 from jose import jwt
 from app.main import Role,User,pwd
 marker=uuid.uuid4().hex;email=f'sync-{marker}@example.test';raw,sig=signed(event(marker))
 session=SessionLocal();user=User(email=email,password_hash=pwd.hash('Sync-test-password-2026!'),role=Role.VIEWER.value);session.add(user);session.commit()
 token=jwt.encode({'sub':email,'exp':datetime.now(timezone.utc)+timedelta(minutes=5)},settings.secret_key,algorithm='HS256')
 try:
  with TestClient(app) as c:
   assert c.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig}).status_code==200
   headers={'Authorization':f'Bearer {token}'}
   payments=c.get('/api/payments',headers=headers).json();sync=c.get('/api/sync',headers=headers).json()
  match=next(x for x in payments if x['payment_id']=='pay_web_'+marker)
  assert match['status']=='failed' and match['created_at'] and match['method']=='card'
  assert sync['failed_count']>=1 and sync['last_event_at']
 finally:
  session.delete(user);session.commit();session.close();cleanup(marker)

