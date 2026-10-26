import torch

CITY = 'demo'
PARAM_BASE = './util/params/'
DATA_BASE = './data/'

RES_FILE = 'res.csv'

BATCH_SIZE = 8192
EPOCHS = 3
TRAJ_FIX_LEN = 21

THRESHOLD = 100

LAMBDA = 0.1

LSTMS_NUM = 2
L2_NUM = 1

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')  # + str(torch.cuda.device_count() - 1)

USE_PER = 1
SPLIT_PER = 0.8

USE_TGRAPH = True
TRANGE_BASE = 1800  # half an hour
T_ONEDAY = 3600 * 24
T_LOOP = T_ONEDAY if not USE_TGRAPH else T_ONEDAY * 7  # consider one day loop or one week

TCOST_MAX = 6000

FIX_LEN = True
TRIM_STOP = True  # true if extra 0 along traj line

EPSILON = 1e-3

ROAD_TYPES = 7
HEADING_DIM = 2
ROAD_LEN_DIM = 1
PROPERTY_DIM = ROAD_TYPES + HEADING_DIM + ROAD_LEN_DIM

ADJ_MASK = -1
STOP_EDGE = 0

PIDX = {'id': 0, 'len': 1, 'road_type': 2, 'heading': 3, 'WKT': 4}

# print('Current device: ', device, flush=True)
