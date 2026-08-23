"""Independent artifact-load inference smoke test."""
import argparse,json
from pathlib import Path
import joblib,pandas as pd
from preprocessing import FEATURE_COLUMNS
def run(data='ml/data/synthetic_payments_100k.csv',n=10):
 d=pd.read_csv(data);d=d[d.payment_status=='failed'].head(n);artifact=joblib.load('ml/models/recovery_probability_model.joblib');p=artifact['model'].predict_proba(artifact['preprocessor'].transform(d[FEATURE_COLUMNS]))[:,1];rank=json.loads(Path('ml/models/intervention_effectiveness.json').read_text());recommended=max(rank,key=lambda a:rank[a]['effectiveness']);out=[{'payment_id':x.payment_id,'actual_outcome':int(x.recovered),'predicted_probability':round(float(prob),4),'recommended_intervention':recommended} for (_,x),prob in zip(d.iterrows(),p)];print(json.dumps(out,indent=2));return out
if __name__=='__main__':p=argparse.ArgumentParser();p.add_argument('--rows',type=int,default=10);a=p.parse_args();run(n=a.rows)
