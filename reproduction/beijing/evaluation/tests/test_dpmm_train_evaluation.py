import json
import pickle
import numpy as np
import pytest

from preprocess.dataset_contract import sha
from prepare_remote_tstr import parse_cell
from tools.prepare_dpmm_train_evaluation import prepare


def write(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.mark.parametrize('bad', [None, 'full', 'partial', 'input', 'hash', 'exit',
                               'missing-receipt', 'command', 'validation', 'split', 'indices'])
def test_train_evaluation_requires_finished_bound_train_release(tmp_path, bad):
    d = tmp_path / 'native'
    d.mkdir()
    train, test = tmp_path / 'train.pkl', tmp_path / 'test.pkl'
    train.write_bytes(b'train input'); test.write_bytes(b'held out input')
    split = tmp_path / 'split.json'
    write(split, dict(schema='verified_disjoint_split_v1', status='passed',
        all_source_indices_used_once=bad != 'split', train_sha256=sha(train),
        test_sha256=sha(test), train_count=2, test_count=1))
    config = tmp_path / 'config.json'
    write(config, dict(paths=dict(train=str(train), test=str(test), split_audit=str(split)),
        frozen_dataset_id='frozen', train_slots=2, test_slots=1, epsilon=1.4))
    with (d / 'dpmm.pkl').open('wb') as handle:
        pickle.dump([np.array([[1., 2.], [3., 4.]])], handle)
    write(d / 'dpmm.json', dict(input_count=2, output_count=1, failed_count=1,
        released_input_indices=[2 if bad == 'indices' else 1]))
    validation = tmp_path / 'validation.json'
    write(validation, dict(complete=bad != 'validation', passed=True, population='train',
        protocol='accelerated-only-process-validation-v1', tested_records=60, target_records=60,
        slow_reference_executed=False, sixty_record_validation=dict(results=[dict(index=i) for i in range(60)]),
        input_count=2, dataset_id='frozen', public_osm_sha256='graph', recommended_workers=3,
        input_sha256=sha(train), adapter_sha256='code', optimization_sha256='fast',
        public_parameters=dict(epsilon=1.4)))
    outputs = {f: sha(d / f) for f in ('dpmm.pkl', 'dpmm.json')}
    write(d / 'new_dataset_execution.json', dict(status='RUNNING' if bad == 'partial' else 'DONE',
        population='full' if bad == 'full' else 'train', input_count=2, dataset_id='frozen',
        input_sha256='wrong' if bad == 'input' else sha(train), rematched=False,
        validation_sha256=sha(validation), adapter_sha256='code', optimizer_sha256='fast',
        osm_sha256='graph', workers=3,
        outputs=outputs, privacy_scope='per-input link-level; not central trajectory DP'))
    document = tmp_path / 'document.md'
    command = 'python synthesize_dpmm.py --split train --workers 3'
    document.write_text('original sentence\n```powershell\n' + command + '\n```\n', encoding='utf-8')
    row = dict(phase='verified', actual_outer_command=command + (' ' if bad == 'command' else ''),
        document_sha256=sha(document), line=3, output='unique/native',
        exit_code=1 if bad == 'exit' else 0, seconds=1,
        execution_sha256=sha(d / 'new_dataset_execution.json'), outputs_sha256=outputs)
    ledger = tmp_path / 'ledger.jsonl'
    rows = [dict(row, phase='start'), dict(row, phase='finish')]
    if bad != 'missing-receipt': rows.append(row)
    ledger.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
    if bad == 'hash': (d / 'dpmm.pkl').write_bytes(b'changed')
    out = tmp_path / 'view'
    if bad:
        with pytest.raises(ValueError):
            prepare(d, config, ledger, document, validation, out)
        assert not (out / 'lineage.json').exists()
    else:
        result = prepare(d, config, ledger, document, validation, out)
        assert result['outputs']['coordinates.pkl'] == sha(out / 'coordinates.pkl')
        assert result['train_sha256'] == sha(train)
        assert result['returncode'] == 0
        with (out / 'coordinates.pkl').open('rb') as handle: slots = pickle.load(handle)
        assert len(slots) == 2 and slots[0].shape == (0, 2)
        np.testing.assert_array_equal(slots[1], [[1., 2.], [3., 4.]])
        with pytest.raises(FileExistsError):
            prepare(d, config, ledger, document, validation, out)


def test_dpmm_native_origin_only():
    assert parse_cell('DPMM/Origin') == ('DPMM', 'Origin')
    with pytest.raises(ValueError): parse_cell('DPMM/FMM')
