"""Train RecoverAI's persisted recovery-probability XGBoost pipeline."""
import json
from datetime import datetime,timezone
from pathlib import Path
import joblib,pandas as pd
from sklearn.metrics import average_precision_score,confusion_matrix,precision_recall_fscore_support,roc_auc_score,brier_score_loss
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from preprocessing import FEATURE_COLUMNS,TARGET_COLUMNS,OUTCOME_COLUMNS,build_preprocessor
def train(data='ml/data/synthetic_payments_100k.csv',seed=42):
 d=pd.read_csv(data);d=d[d.payment_status=='failed'].copy(); missing=set(FEATURE_COLUMNS+TARGET_COLUMNS)-set(d.columns)
 if missing:raise ValueError(f'Missing columns: {missing}')
 assert not set(FEATURE_COLUMNS)&set(OUTCOME_COLUMNS),'Outcome leakage in features'
 x=d[FEATURE_COLUMNS];y=d[TARGET_COLUMNS[0]].astype(int);xt,xhold,yt,yhold=train_test_split(x,y,test_size=.30,random_state=seed,stratify=y);xv,xte,yv,yte=train_test_split(xhold,yhold,test_size=.50,random_state=seed,stratify=yhold)
 pre=build_preprocessor();xtp=pre.fit_transform(xt);xtep=pre.transform(xte);model=XGBClassifier(n_estimators=220,max_depth=5,learning_rate=.055,subsample=.85,colsample_bytree=.85,eval_metric='logloss',random_state=seed,n_jobs=4);model.fit(xtp,yt);p=model.predict_proba(xtep)[:,1];pred=(p>=.5).astype(int);pr,re,f1,_=precision_recall_fscore_support(yte,pred,average='binary',zero_division=0);metrics={'roc_auc':float(roc_auc_score(yte,p)),'pr_auc':float(average_precision_score(yte,p)),'precision':float(pr),'recall':float(re),'f1':float(f1),'confusion_matrix':confusion_matrix(yte,pred).tolist(),'brier_score':float(brier_score_loss(yte,p)),'train_rows':len(xt),'validation_rows':len(xv),'test_rows':len(xte),'failed_payment_rows':len(d),'positive_rate':float(y.mean()),'training_timestamp':datetime.now(timezone.utc).isoformat(),'dataset_version':'synthetic-v2','feature_version':'v2','feature_columns':FEATURE_COLUMNS};out=Path('ml/models');out.mkdir(parents=True,exist_ok=True);joblib.dump({'preprocessor':pre,'model':model,'feature_columns':FEATURE_COLUMNS},out/'recovery_probability_model.joblib');joblib.dump(pre,out/'recovery_preprocessor.joblib');(out/'recovery_metrics.json').write_text(json.dumps(metrics,indent=2));return metrics
if __name__=='__main__':print(json.dumps(train(),indent=2))
