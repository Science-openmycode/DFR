import numpy as np
import argparse
import config.folder_and_file_names as fname


def parse_epsilon_partition(value):
    if isinstance(value, np.ndarray):
        return value.astype(float)
    if isinstance(value, (list, tuple)):
        return np.asarray(value, dtype=float)
    parts = [float(part.strip()) for part in str(value).replace(";", ",").split(",") if part.strip()]
    arr = np.asarray(parts, dtype=float)
    if arr.shape != (3,):
        raise argparse.ArgumentTypeError("epsilon_partition must contain three comma-separated values")
    total = float(arr.sum())
    if total <= 0:
        raise argparse.ArgumentTypeError("epsilon_partition must have positive sum")
    return arr / total


class ParSetter:

    def __init__(self):
        pass

    def set_up_args(self, dataset_file_name=None, epsilon=False, epsilon_partition=False, level1_parameter=False, level2_parameter=False):
        parser = argparse.ArgumentParser()
        parser.add_argument('--dataset_file_name', type=str, default=fname.dataset_file_name)
        parser.add_argument('--subdividing_inner_parameter', type=float, default=200)
        parser.add_argument('--level1_parameter', type=float, default=600)
        parser.add_argument('--total_epsilon', type=float, default=2.0)
        # regularly, partition solution is suggested to be np.array([0.2, 0.52, 0.28]))
        parser.add_argument('--epsilon_partition', type=parse_epsilon_partition, default=np.array([0.2, 0.4, 0.4]))
        # this parameter indicates how many trajectories to generate
        parser.add_argument('--trajectory_number_to_generate', type=int, default=-1)
        args = vars(parser.parse_args())
        if epsilon is not False:
            args['total_epsilon'] = epsilon
        if epsilon_partition is not False:
            args['epsilon_partition'] = epsilon_partition
        if level1_parameter is not False:
            args['level1_parameter'] = level1_parameter
        if level2_parameter is not False:
            args['subdividing_inner_parameter'] = level2_parameter
        if dataset_file_name is not None:
            args['dataset_file_name'] = dataset_file_name
        return args




