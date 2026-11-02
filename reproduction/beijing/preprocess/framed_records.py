"""Bounded iterator over the freezer's explicitly framed protocol-3 list."""
import gzip
import pickle
import queue
import threading
from pathlib import Path


class Consumer(pickle._Unpickler):
    dispatch=pickle._Unpickler.dispatch.copy()
    def __init__(self,stream,callback):
        super().__init__(stream);self.root=None;self.callback=callback
    def load_empty_list(self):
        super().load_empty_list()
        if self.root is None:self.root=self.stack[-1]
    dispatch[pickle.EMPTY_LIST[0]]=load_empty_list
    def load_append(self):
        if len(self.stack)>=2 and self.stack[-2] is self.root:self.callback(self.stack.pop())
        else:super().load_append()
    dispatch[pickle.APPEND[0]]=load_append


def records(path,expected_count):
    path=Path(path);opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rb') as f:framed=f.read(3)==b'\x80\x03]'
    if not framed:
        if expected_count>100000:raise ValueError('Large input requires bounded-memory framed list')
        with opener(path,'rb') as f:values=pickle.load(f)
        if len(values)!=expected_count:raise ValueError('Record count mismatch')
        yield from values
        return
    messages=queue.Queue(maxsize=2);stop=threading.Event()
    class Cancelled(Exception):pass
    def put(kind,value):
        while not stop.is_set():
            try:messages.put((kind,value),timeout=.1);return
            except queue.Full:pass
        raise Cancelled()
    def worker():
        try:
            with opener(path,'rb') as f:
                result=Consumer(f,lambda value:put('record',value)).load()
                if result!=[] or f.read(1):raise ValueError('Invalid framed list or trailing bytes')
            put('done',None)
        except Cancelled:pass
        except BaseException as error:
            try:put('error',error)
            except Cancelled:pass
    thread=threading.Thread(target=worker,daemon=True);thread.start();count=0
    try:
        while True:
            kind,value=messages.get()
            if kind=='error':raise value
            if kind=='done':break
            count+=1;yield value
        if count!=expected_count:raise ValueError('Framed record count mismatch')
    finally:
        stop.set();thread.join(timeout=1)
