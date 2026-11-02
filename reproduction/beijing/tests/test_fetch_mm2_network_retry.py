"""Network failures retain evidence without poisoning later MM2 fetch attempts."""
import hashlib
import importlib.util
import io
import sys
from pathlib import Path


def test_retry_ignores_stale_partial_and_keeps_failed_attempt(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root/'preprocess'))
    spec=importlib.util.spec_from_file_location('mm2_retry_test',root/'preprocess/fetch_mm2.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    archive=tmp_path/'mm2.zip';stale=archive.with_suffix('.part');stale.write_bytes(b'old attempt')
    out=tmp_path/'extracted';exe=tmp_path/'installed.exe';payload=b'archive test bytes';binary=b'executable test bytes'
    monkeypatch.setattr(module,'ARCHIVE_SHA',hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(module,'EXE_SHA',hashlib.sha256(binary).hexdigest())
    monkeypatch.setattr(sys,'argv',['fetch_mm2.py','--archive',str(archive),'--extract-to',str(out),'--install-to',str(exe)])
    def fail(*args,**kwargs):raise TimeoutError('test network timeout')
    monkeypatch.setattr(module.urllib.request,'urlopen',fail)
    import pytest
    with pytest.raises(TimeoutError):module.main()
    failed=list(tmp_path.glob('mm2.zip.*.part'));assert len(failed)==1
    monkeypatch.setattr(module.urllib.request,'urlopen',lambda *args,**kwargs:io.BytesIO(payload))
    def extract(src,dest):
        (dest/'bin').mkdir(parents=True);(dest/'bin/map_matching_2.exe').write_bytes(binary)
    monkeypatch.setattr(module,'extract',extract)
    module.main()
    assert archive.read_bytes()==payload and exe.read_bytes()==binary
    assert stale.read_bytes()==b'old attempt' and failed[0].exists()
