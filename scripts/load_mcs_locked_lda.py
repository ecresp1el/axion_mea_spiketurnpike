"""Load the locked 215 raw unit metrics and apply the saved descriptive LDA."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

CONFIG=Path(__file__).resolve().parents[1]/'metadata/mcs_active_lda_configuration.json'

def load_units(config_path=CONFIG,verify=True):
    config=json.loads(Path(config_path).read_text())
    path=Path(config['frozen_raw_metrics_csv'])
    if verify:
        assert hashlib.sha256(path.read_bytes()).hexdigest()==config['frozen_raw_metrics_sha256']
    frame=pd.read_csv(path,dtype={'unit_id':str})
    names=config['original_features']+config['new_burst_features']
    values=frame[names].astype(float)
    metadata=frame.drop(columns=names)
    assert values.shape[1]==215 and not metadata.duplicated(['recording_id','unit_id']).any()
    return metadata,values

def project_units(values,config_path=CONFIG):
    """Use frozen full-data transforms; returns LD1/LD2 and fitted class labels."""
    config=json.loads(Path(config_path).read_text())
    path=Path(config['frozen_model_npz'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==config['frozen_model_sha256']
    model=np.load(path,allow_pickle=False)
    names=model['feature_names'].tolist()
    raw=values[names].to_numpy(dtype=float)
    x=np.sign(raw)*np.log1p(np.abs(raw))
    x=np.where(np.isnan(x),model['impute_median'],x)
    z=(x-model['scale_mean'])/model['scale_std']
    assert np.isfinite(z).all()
    coordinates=z@model['lda_projection']
    labels=model['class_labels'][np.argmax(z@model['lda_coef'].T+model['lda_intercept'],axis=1)]
    return coordinates,labels

if __name__=='__main__':
    metadata,values=load_units()
    coordinates,labels=project_units(values)
    print(f'{len(values)} units; {values.shape[1]} raw metrics; LD coordinates {coordinates.shape}')
