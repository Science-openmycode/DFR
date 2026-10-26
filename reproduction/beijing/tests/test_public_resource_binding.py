import importlib.util
from pathlib import Path

def test_dataset_alias_is_bound_to_the_existing_pipeline_key():
    file=Path(__file__).resolve().parents[1]/'prepare_public_resources.py'
    spec=importlib.util.spec_from_file_location('prepare_public_resources',file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.legacy_dataset_key('beijing')=='geolife'
    assert module.legacy_dataset_key('san_francisco')=='sf_taxi'
    assert module.legacy_dataset_key('porto')=='porto'
    labels=module.physical_node_labels({9:(2,3),10:(3,4)},{9:(100,101),10:(101,102)})
    assert labels=={100:2,101:3,102:4}
