"""Seeds only clearly labelled synthetic/demo records."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'backend'))
from app.main import Base,engine,SessionLocal,Customer,Payment,pipeline
Base.metadata.create_all(engine);s=SessionLocal()
for i in range(60):
 c=Customer(external_id=f'demo_customer_{i}',name=f'Demo customer {i}',email=f'demo{i}@example.test',lifetime_value=5000+i*400,success_rate=.45+(i%5)*.1);s.add(c);s.flush();p=Payment(external_id=f'demo_pay_{i}',customer_id=c.id,order_id=f'demo_order_{i}',amount=500+(i*431)%14500,method=['card','upi','netbanking'][i%3],status='failed',failure_reason=['temporary_bank_failure','insufficient_funds','expired_card'][i%3],retry_count=i%3);s.add(p);s.flush();pipeline(s,p)
s.commit();print('Seeded 60 synthetic demo failures')
