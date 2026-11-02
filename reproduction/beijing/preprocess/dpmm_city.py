"""Public UTM parameters, preserving historical Beijing defaults."""
def projection(config):
    if config.get('dataset', 'beijing') == 'beijing':
        if config.get('routing_crs', {}).get('network_srs', 'EPSG:32650')!='EPSG:32650':
            raise ValueError('Beijing projection mismatch')
        return 50, 'S'
    crs=config.get('routing_crs', {}).get('network_srs', '')
    if not crs.startswith('EPSG:326'): raise ValueError('Explicit northern UTM CRS required')
    zone=int(crs[8:])
    south,north,west,east=config['bbox']
    if not (1<=zone<=60 and 0<=south<=north<84 and -180<=west<=east<=180):
        raise ValueError('Invalid public UTM bounds')
    bands='CDEFGHJKLMNPQRSTUVWXX'
    letters={bands[int((lat+80)//8)] for lat in (south,north)}
    if len(letters)!=1: raise ValueError('Bounds cross UTM latitude bands')
    return zone, letters.pop()
