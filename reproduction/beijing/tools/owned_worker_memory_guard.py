"""Observe this invocation's descendants only; fail safely before memory exhaustion."""
import json
from pathlib import Path
import threading
import time


class OwnedWorkerMemoryGuard:
    def __init__(self,reserve_gib,out):
        self.reserve_gib=reserve_gib
        self.out=Path(out)
        self.stopped=threading.Event()
        self.exceeded=threading.Event()
        self.stats={'reserve_gib':reserve_gib,'minimum_available_gib':None,
                    'peak_descendant_private_gib':0.,'terminated_owned_pids':[],
                    'scope':'Only descendants of this generation process; no unrelated processes'}
        self.thread=threading.Thread(target=self.watch,daemon=True)

    def start(self):
        self.thread.start()

    def watch(self):
        import psutil
        parent=psutil.Process()
        while not self.stopped.is_set():
            free=psutil.virtual_memory().available/2**30
            previous=self.stats['minimum_available_gib']
            self.stats['minimum_available_gib']=free if previous is None else min(previous,free)
            children=parent.children(recursive=True)
            memory=0.
            for child in children:
                try:
                    info=child.memory_info();memory+=getattr(info,'private',info.rss)/2**30
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            self.stats['peak_descendant_private_gib']=max(self.stats['peak_descendant_private_gib'],memory)
            if free<self.reserve_gib:
                self.exceeded.set()
                for child in children:
                    try:
                        child.terminate();self.stats['terminated_owned_pids'].append(child.pid)
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            self.stats['sample_epoch_seconds']=time.time()
            temporary=self.out.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.stats,indent=2),encoding='utf-8')
            temporary.replace(self.out)
            if self.exceeded.is_set():break
            self.stopped.wait(.5)

    def stop(self):
        self.stopped.set();self.thread.join(timeout=2)
