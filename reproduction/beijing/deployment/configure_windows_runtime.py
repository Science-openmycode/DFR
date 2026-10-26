"""Bind bundled VC runtime to this isolated environment, without system changes."""
import hashlib
import json
from pathlib import Path
import sys
import sysconfig

def configure(root):
    if sys.platform != 'win32':
        return
    if sys.prefix == sys.base_prefix:
        raise RuntimeError('Refusing to change a non-isolated Python environment')
    root=Path(root).resolve()
    manifest=root/'resources/binding.json'
    if not manifest.is_file():
        manifest=root/'deployment_binding.json'
    files=json.loads(manifest.read_text(encoding='utf-8'))['files']
    runtime=root/'resources/runtime'
    required=('msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll','vcruntime140.dll','vcruntime140_1.dll')
    for name in required:
        rel='resources/runtime/'+name
        if rel not in files or hashlib.sha256((root/rel).read_bytes()).hexdigest()!=files[rel]:
            raise ValueError('Missing or changed bound runtime: '+rel)
    # Keep the handle alive for subsequent imports in every venv subprocess.
    line='import os; _beijing_runtime_handle = os.add_dll_directory('+repr(str(runtime))+')\n'
    target=Path(sysconfig.get_path('purelib'))/'beijing_runtime.pth'
    if target.exists() and target.read_text(encoding='utf-8')!=line:
        raise FileExistsError('Different runtime already configured: '+str(target))
    target.write_text(line,encoding='utf-8')
    print('BOUND_WINDOWS_RUNTIME',runtime)

if __name__=='__main__':
    configure(sys.argv[1])
