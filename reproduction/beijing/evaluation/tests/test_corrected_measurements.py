import importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def module():
    spec=importlib.util.spec_from_file_location('corrected', ROOT/'algorithms/measurements/frozen_adapter.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mapping_matches_actual_frozen_versions():
    assert module().IDENTITIES == {'SPRT':'PaperSPRTModel','PrivTrace':'official_privtrace/main.py','DPStd':'PaperDPStdModel'}
    module().verify_sources()


def test_dpstd_center_decoder_preserves_original_no_jitter():
    adapter=module()
    real=[np.array([[39.9,116.3],[39.91,116.31],[39.92,116.32]]) for _ in range(50)]
    model=adapter.dpstd_model(1.4,42,(39.4,40.8,115.8,117.4))
    model.fit(real)
    syn=model.generate(7)
    assert len(syn)==7
    assert model.coord_sigma==0
    assert model.point_mode=='center'
    assert model.generator_variant=='markov-init'


def test_official_privtrace_runs_with_adapter_io(tmp_path):
    adapter=module()
    rng=np.random.default_rng(123)
    # Official level1=12500 needs >=50,000 observations for a 2x2 grid.
    real=[np.cumsum(rng.normal(0,.0005,(10,2)),axis=0)+[39.9,116.3] for _ in range(6000)]
    syn,params=adapter.official_privtrace(real,5,1.4,42,tmp_path)
    assert len(syn)==5
    assert all(a.ndim==2 and a.shape[1]==2 for a in syn)
    assert params['max_points']==30
