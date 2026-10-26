import os
import numpy as np

if not hasattr(np,'int'):np.int=int
if not hasattr(np,'float'):np.float=float
if 'PRIVTRACE_NUMPY_SEED' in os.environ:
    np.random.seed(int(os.environ['PRIVTRACE_NUMPY_SEED']))
