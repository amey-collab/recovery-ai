"""Send one synthetic, locally signed payment.failed event to the running API."""
import hashlib,hmac,json,os,sys,uuid
from pathlib import Path
import httpx
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]; env=dotenv_values(root/'.env'); secret=env.get('RAZORPAY_WEBHOOK_SECRET')
if not secret: raise SystemExit('RAZORPAY_WEBHOOK_SECRET is not configured in local .env')
marker=uuid.uuid4().hex; payload={'event':'payment.failed','payload':{'payment':{'entity':{'id':'pay_local_'+marker,'order_id':'ord_local_'+marker,'amount':499900,'currency':'INR','method':'card','email':'synthetic@example.test','error_description':'synthetic local webhook test'}}}}
raw=json.dumps(payload,separators=(',',':')).encode(); signature=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
r=httpx.post(os.getenv('RECOVERAI_API_URL','http://localhost:8000')+'/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':signature},timeout=15)
print('synthetic_event=payment.failed');print('event_marker='+marker);print('http_status='+str(r.status_code));print('response='+r.text[:500])
