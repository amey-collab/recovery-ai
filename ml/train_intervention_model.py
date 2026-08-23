"""Observed synthetic intervention effectiveness, used by the deterministic value ranking layer."""
import json
from pathlib import Path
import pandas as pd
def train(data='ml/data/synthetic_payments_100k.csv'):
 d=pd.read_csv(data);d=d[(d.payment_status=='failed')&(d.recovery_action!='no_action')];r=d.groupby('recovery_action').agg(effectiveness=('recovered','mean'),mean_amount=('amount','mean'),attempts=('recovered','size'),recovered_value=('recovered_amount','sum')).sort_values('effectiveness',ascending=False).to_dict('index');out=Path('ml/models');out.mkdir(parents=True,exist_ok=True);(out/'intervention_effectiveness.json').write_text(json.dumps(r,indent=2));return r
if __name__=='__main__':print(json.dumps(train(),indent=2))
