import sys, os, time
sys.path.insert(0, r'E:\study\大四下\Paper-Agent-main\Paper-Agent-main\MT_net\PUTS\PUTS-main')

# Fake DataProcess module
import types
fake = types.ModuleType('DataProcess')
fake2 = types.ModuleType('DataProcess.Data_Collection')
fake3 = types.ModuleType('DataProcess.Data_Collection.gps_reader')
class FakeTransform:
    def __init__(self, *args): pass
    def transform_func(self, *args): return args
fake3.GisTransform = FakeTransform
fake2.gps_reader = fake3
fake.Data_Collection = fake2
sys.modules['DataProcess'] = fake
sys.modules['DataProcess.Data_Collection'] = fake2
sys.modules['DataProcess.Data_Collection.gps_reader'] = fake3

import logging
logging.basicConfig(format='%(asctime)s %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
                    datefmt='%Y-%m-%d %H:%M', level=logging.INFO)

data_dir = r'E:\study\大四下\Paper-Agent-main\Paper-Agent-main\MT_net\PUTS\PUTS-main\Dataset\Beijing'
N_TRAJS = 15462

from GlobalDatabase import GlobalDatabase
from SrcDestRegionsSample import SrcDestRegionsSample
from RoadTransitionMatrix import RoadTransitionMatrix
from RoadSpeedSample import RoadSpeedSample
from TrajectorySynthesizer import RoadSequenceGenerator, TrajectoryPointGenerator
from utils import saveSynDB

start = time.time()

matched_gps = os.path.join(data_dir, f'pgeom.{N_TRAJS}')
cpath_data = os.path.join(data_dir, f'cpath.{N_TRAJS}')
opath_data = os.path.join(data_dir, f'opath.{N_TRAJS}')
road_geometry = os.path.join(data_dir, 'geometry.txt')
shortestLengthFile = os.path.join(data_dir, f'shortestLengthM_{N_TRAJS}.npy')

print('Building GlobalDatabase...')
globalDB = GlobalDatabase(
    matchedGPSFile=matched_gps, cpathDataFile=cpath_data, opathDataFile=opath_data,
    roadGeometryFile=road_geometry, regionCount=6, shortestLengthFile=shortestLengthFile)
print(f'  DB size: {globalDB.getMatchedGPSDatabase().getSize()}')

sdRoadSampler = SrcDestRegionsSample(globalDB, 0.33)
print('Trip Distribution done.')

noisyTransMatrix = RoadTransitionMatrix(globalDB, 0.34)
print('Transition Matrix done.')

minspeed, maxspeed = 0, 7*0.0003
if maxspeed is None: maxspeed = 7*0.0003
roadSpeedSampler = RoadSpeedSample(globalDB, 5, minspeed, maxspeed, 0.33)
print('Speed distribution done.')

# One DP-sanitized model is used to draw a public fixed-size release.  The
# candidate count is larger than the drawable target because PUTS can emit
# degenerate one-point GPS records on this scaled Beijing adapter.
DRAWABLE_TARGET = 17123
CANDIDATE_RELEASE_SIZE = 21300
import TrajectorySynthesizer as ts
original_desired = ts.RoadSequenceGenerator.__init__
def patched_init(self, sdRoadSampler, noisyTransMatrix, globalDB, safeValue=1.5, MulProcesses=False):
    self.desiredNumberOfTrajectories = CANDIDATE_RELEASE_SIZE
    self.usedRoad = globalDB.getCpathDatabase().getusedRoad()
    self.roadErrorCount = 0
    self.unAdjaceRoadTransitionMatrix = noisyTransMatrix.getunAdjaceRoadTransitionMatrix()
    self.maxSteps = globalDB.getCpathDatabase().getMaxRoadSequenceLength()
    self.transitionProbsMatrixs = self.precomputeMarkov(noisyTransMatrix.getnoisyRoadTransitionProbsMatrix(), self.maxSteps)
    self.srcDestLengthSampler = ts.SrcDestLengthSample(globalDB, self.transitionProbsMatrixs, safeValue)
    self.adjacRoadDic = globalDB.getRoadGeometry().getAdjacentRoad()
    print(f'Generating {self.desiredNumberOfTrajectories} road sequences...')
    self.syntheticRoadDB = self.generatedSyntheticRoadSequence(sdRoadSampler)
ts.RoadSequenceGenerator.__init__ = patched_init

roadSequenceGenerator = RoadSequenceGenerator(sdRoadSampler, noisyTransMatrix, globalDB, 10.0, False)  # safeValue=10
synRoads = roadSequenceGenerator.getsyntheticRoadDB()
print(f'Generated {len(synRoads)} road sequences')

trajectoryGenerator = TrajectoryPointGenerator(roadSpeedSampler, globalDB, synRoads, False)
synTrajDb = trajectoryGenerator.getsyntheticTrajectoryDB()
print(f'Generated {len(synTrajDb)} GPS trajectories')

out_dir = r'E:\study\大四下\Paper-Agent-main\Paper-Agent-main\MT_net\PUTS\PUTS-main\SyntheticDataset\Beijing\Test'
os.makedirs(out_dir, exist_ok=True)
filename = f'sf1.5-rc6-eps1.0-0.33-0.34-0.33.Beijing'
out_path = os.path.join(out_dir, filename)
saveSynDB(out_path, synTrajDb)
print(f'Done! {time.time()-start:.1f}s')
print(f'Output: {out_path}')
