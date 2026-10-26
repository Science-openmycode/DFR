__author__ = 'ubriela'

import numpy as np
import math

# # Basic parameters
class Params(object):
    DATASET = "gowallacn"

    maxHeight = 5  # maximum tree height, for kdtrees and quadtrees

    VARYING_GRID_SIZE = False
    p_sigma = 0.5
    gamma = 0.5
    theta = 10
    ONE_KM = 0.0089982311916  # convert km to degree
    base = np.e
    MIN_SENSITIVITY = 1e-4*5
    MAX_C_SS = 100 # used for precompute SS

    MAX_N = 1e+6
    MAX_C = 1e+4 # maximum number of visits of a user to a location (used for generate syn data)
    MAX_M = 1e+3 # maximum of maximum number of locations of a user (used for generate syn data)
    DELTA = 1e-8
    PRECISION = 1e-15
    DEFAULT_ENTROPY = DEFAULT_DIVERSITY = DEFAULT_FREQUENCY = 0.0
    TOP_K = 100
    MAX_ENTROPY = MAX_DIVERSITY = math.log(MAX_N, base)
    GEOI_GRID_SIZE = 5000

    EARTH_RADIUS = 6378137 # const, in meters
    def __init__(self, seed):
        self.dataset = ""
        self.resdir = ""
        self.locs = None
        self.maxC = None
        self.totalC = None
        self.users = None
        self.locDict = None
        self.cellDict = None

        self.radius = 500.0  # default unit is meters
        self.C = 2
        self.M = 5
        self.K = 50 # only publish locations with at least K users
        self.k_min = 10 # only consider locations with at least k_min users

        self.m = 100 # granularity of equal-size grid cell
        self.eps = 1.0  # epsilon
        self.seed = seed # used in generating noisy counts

        self.Percent = 0.3  # budget allocated for split
        self.geoBudget = 'optimal'  # geometric exponent i/3
        self.splitScheme = 'expo'  # exponential mechanism

    def select_dataset(self):
        if Params.DATASET == "sparse":
            self.dataset = "../dataset/sparse.txt"
            self.resdir = "../output/"

        if Params.DATASET == "medium":
            self.dataset = "../dataset/medium.txt"
            self.resdir = "../output/"

        if Params.DATASET == "dense":
            self.dataset = "../dataset/dense.txt"
            self.resdir = "../output/"

        if Params.DATASET == "yelppx":
            self.dataset = "../dataset/yelp_PX.txt"
            self.resdir = "../output/"
            self.x_min = 32.8768481
            self.y_min = -112.875481
            self.x_max = 33.806805
            self.y_max = -111.671219

        if Params.DATASET == "gowallacb":
            self.dataset = "../dataset/gowalla_CN.txt"
            self.resdir = "../output/"
            self.x_min = 39.1232147
            self.y_min = 115.3879166
            self.x_max = 40.7225952
            self.y_max = 117.3795395

        if Params.DATASET == "gowallany":
            self.dataset = "../dataset/gowalla_NY.txt"
            self.resdir = "../output/"
            self.x_min = 40.6991117951
            self.y_min = -74.0270912647
            self.x_max = 40.7965600333
            self.y_max = -73.9228093667

        if Params.DATASET == "gowallaau":
            self.dataset = "../dataset/gowalla_AU.txt"
            self.resdir = "../output/"
            self.x_min = 30.087879
            self.y_min = -98.010254
            self.x_max = 30.682575
            self.y_max = -97.451330

        if Params.DATASET == "gowallaca":
            self.dataset = "../dataset/gowalla_CA.txt"
            self.resdir = "../output/"
            self.x_min = 32.1713906
            self.y_min = -124.3041035
            self.x_max = 41.998434033
            self.y_max = -114.004346433

        if Params.DATASET == "gowallasf":
            self.dataset = "../dataset/gowalla_sf.dat"
            self.resdir = "../output/"
            self.x_min = 37.71127146
            self.y_min = -122.51350164
            self.x_max = 37.83266118
            self.y_max = -122.3627126

        if Params.DATASET == "syn10k":
            self.dataset = "../dataset/syn_10K.txt"
            self.resdir = "../output/"
            self.x_min = 0
            self.y_min = 0
            self.x_max = 100
            self.y_max = 100

        if Params.DATASET == "syn10kuni":
            self.dataset = "../dataset/syn_10K_uni.txt"
            self.resdir = "../output/"
            self.x_min = 0
            self.y_min = 0
            self.x_max = 100
            self.y_max = 100

        if Params.DATASET == "syn100k1m":
            self.dataset = "../dataset/syn_100K_1M.txt"
            self.resdir = "../output/"
            self.x_min = 0
            self.y_min = 0
            self.x_max = 100
            self.y_max = 100

#    def debug(self):
#        print 'number of locs', len(self.locs.keys())
#        print 'number of users', len(self.users)
#        print 'average number of users per location', np.average([len(self.locs[lid]) for lid in self.locs.keys()])
#        print 'average number of locations per user', np.average([len(self.users[uid]) for uid in self.users.keys()])
#        print 'maximum number of locations per user', np.max([len(self.users[uid]) for uid in self.users.keys()])
#        print 'Maximum number of visits of a user contributes to a location', self.maxC
#        print 'Average number of visits of a user to a location', (self.totalC + 0.0) / len(self.locs)