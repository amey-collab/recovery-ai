from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'ml'))
from train_recovery_model import train
from train_intervention_model import train as interventions
if __name__=='__main__': print(train());print(interventions())
