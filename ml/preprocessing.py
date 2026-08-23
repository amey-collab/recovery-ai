"""One source of truth; outcome fields are excluded from inference features."""
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
FEATURE_COLUMNS=['amount','payment_method','failure_reason','failure_source','failure_step','customer_age_days','previous_payment_count','previous_success_count','previous_failure_count','customer_success_rate','average_transaction_amount','customer_lifetime_value','days_since_last_payment','retry_count','previous_recovery_count','historical_recovery_rate','previous_intervention','subscription_status','subscription_age_days','time_of_day','day_of_week','merchant_category','customer_segment']
TARGET_COLUMNS=['recovered'];OUTCOME_COLUMNS=['recovered','recovered_amount']
CATEGORICAL_COLUMNS=['payment_method','failure_reason','failure_source','failure_step','previous_intervention','subscription_status','merchant_category','customer_segment'];NUMERIC_COLUMNS=[x for x in FEATURE_COLUMNS if x not in CATEGORICAL_COLUMNS]
def build_preprocessor():return ColumnTransformer([('num',Pipeline([('impute',SimpleImputer(strategy='median'))]),NUMERIC_COLUMNS),('cat',Pipeline([('impute',SimpleImputer(strategy='most_frequent')),('onehot',OneHotEncoder(handle_unknown='ignore'))]),CATEGORICAL_COLUMNS)])
