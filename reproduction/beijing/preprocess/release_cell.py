"""Validate method/router labels, independently of any downstream experiment."""


def parse_cell(value):
    parts = value.split('/')
    if parts in (['MTNet', 'Origin'], ['DPMM', 'Origin'], ['MTR-DFR', 'Origin']):
        return tuple(parts)
    if (len(parts) != 2 or parts[0] not in ('SPRT', 'PrivTrace', 'DPStd', 'DPTraj-PM')
            or parts[1] not in ('Origin', 'Nearest', 'FMM', 'STMatch', 'MM2-MDP')):
        raise ValueError('Expected a supported M/R pair')
    return tuple(parts)
