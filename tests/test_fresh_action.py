import numpy as np
from scripts import fresh_action as f


def test_roundoff_feature_is_removed_and_predictions_stable():
    rows=[dict(task='packing26',x=[i,1e-17*i],terminal=[dict(score=v) for v in [i,-i,0]]) for i in range(16)]
    model=f.fit(rows)
    assert model['active']==[True,False]
    np.testing.assert_array_equal(f.predictions(model,[3,0]),f.predictions(model,[3,1e-15]))
    assert np.argmax(f.predictions(model,[15,0]))==0
