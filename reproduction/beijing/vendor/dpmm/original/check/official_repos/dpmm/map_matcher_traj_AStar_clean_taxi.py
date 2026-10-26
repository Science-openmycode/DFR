import os
import random
import numpy as np
import multiprocessing as mp
from itertools import groupby, count
from heapq import heappush, heappop


import geopandas as gpd
import osmnx as ox
import networkx as nx
import shapely as shp
import utm
from rdp import rdp

from Differential import Differential

import warnings
_visible_deprecation = getattr(np, "VisibleDeprecationWarning", None)
if _visible_deprecation is not None:
    warnings.filterwarnings("ignore", category=_visible_deprecation)

def select_region(place):#, graph):
     
        
    cities_latlon=ox.project_gdf(gpd.read_file('bay_area_cities.geojson'), to_latlong = True)
    p_gdf=cities_latlon.loc[cities_latlon.city=='SAN FRANCISCO']
    west, south, east, north = p_gdf.unary_union.bounds

    subgraph = ox.graph_from_bbox(north, south, east, west, network_type='drive')
    nodes, edges= ox.graph_to_gdfs(subgraph)
    
    edges_projected = ox.project_gdf(edges, to_crs = 32610)
    
    
    cities=ox.project_gdf(gpd.read_file('bay_area_cities.geojson'))
    gdf=cities.loc[cities.city=='SAN FRANCISCO']
    west, south, east, north = gdf.unary_union.bounds
    roi = shp.geometry.box(*(west, south, east, north))
    
    return edges_projected, nodes, subgraph, roi
    
class MapMatching:
    def __init__(self, zone, place, edges, nodes, graph, unproc_dir, clean_dir,
                 utm_zone_number=10, utm_zone_letter='U'):
        self.zone = zone
        self.graph = graph
        self.bb_margin = 5 #number of links margin
        self.bb_margin_fc = 5 #number of same ff links margin 
        self.edges, self.nodes= edges, nodes
        self.unproc_dir, self.clean_dir = unproc_dir, clean_dir
        # Geographic adapter: the released example hard-codes San Francisco
        # UTM zone 10U.  These defaults preserve that example; external-city
        # adapters provide their public UTM zone without altering DPMM's noise
        # sampler, candidate construction, or path-selection logic.
        self.utm_zone_number = utm_zone_number
        self.utm_zone_letter = utm_zone_letter
        
        self.edges.insert(0,'u', [idx[0] for idx in self.edges.index])
        self.edges.insert(1,'v', [idx[1] for idx in self.edges.index])
        # self.edges = edges
        # self.edges, self.graph = self.select_region(place)

    def folder_init(self, eps, find_dir):
        """
        Initialize the MapMAching object with epsilon valu and directory for DPMM link trajectories,
        """
        self.eps = eps
        self.find_dir = find_dir

    def heuristic(self, a, b):     
        """
        Helper function NetworkX A* Shortest Path algorithm.
        """
        a_point =self.nodes.loc[a].geometry
        b_point =self.nodes.loc[b].geometry
        return a_point.distance(b_point)

    def gen_path_list(self, source_nodes, target_nodes):
        """
        Helper function to generate list of links for paths between source and target links.
        """
        path_list=[]
        distance_list=[]
        for source in source_nodes:
            for target in target_nodes:
                if source!=target:
                    try:
                    # path_list.append(self.find_A_star_path(source, target))
                        path_list.append(nx.astar_path(self.graph, source=source, target=target, heuristic=self.heuristic, weight="length"))
                        distance_list.append(nx.astar_path_length(self.graph, source=source, target=target, heuristic=self.heuristic, weight="length"))
                    except:
                        pass
        # path_list = [x for x in path_list if x]
        paths = [p for p in path_list if p]
        distances = [p for p in distance_list if p]
        
        return paths, distances
    
    def path_to_df(self, path):
        """
        Helper function to convert from NetworkX Shortest Path (list-like) to subset of GeoDataFrame.
        """
        df_edges=self.edges.copy()
        
        links_u=[idx[0] for idx in df_edges.index]
        links_v=[idx[1] for idx in df_edges.index]
        df_edges.index = list(zip(links_u,links_v))
        
        index_list = []
        for i in range(len(path)-1):
            index = (path[i],path[i+1])
            if index not in index_list:
                index_list.append(index)
                
        return df_edges.loc[index_list].reset_index(drop=True)
    
    def load_trajectory(self, file_name):
        """
        Reads and projects trajectory file. Removes duplicate geometries, just in case.
        """
        utm_trajectory = ox.project_gdf(gpd.read_file(self.unproc_dir+file_name))
        utm_trajectory = utm_trajectory.drop_duplicates(subset='geometry').reset_index(drop=True)
    
        return utm_trajectory


    def NormalizeData(self, data):
        """
        Normalizes the input data between minimum and maximum values for exponential differential privacy mechanism.
        """       
        if len(data)>1:
            return (data - np.min(data)) / (np.max(data) - np.min(data))
        else:
            return np.array([1])

    def exponential(self, paths, distances, sensitivity=1):
        """
        Applies exponential differential privacy to the path selections given the epsilon value with respec to distance values of candidate paths.
        """
     
        # Calculate the score for each element of R
        # scores = [u(x, r) for r in R]
        scores= 1-self.NormalizeData(distances)
        
        # num_len=len(str(int(max(distances))))-2
        # t_dist=1/(norm.cdf(distances, np.mean(distances), max(distances)/min(distances)))
        # scores = [np.log(t) for t in t_dist]
        
        # scores=np.exp(-0.5 * (distances / np.mean(distances))**2)
        # link_ids = R.link_id.values
        
        # Calculate the probability for each element, based on its score
        probabilities = [np.exp(self.eps * score / (2 * sensitivity)) for score in scores]
        
        # Normalize the probabilties so they sum to 1
        probabilities = probabilities / np.linalg.norm(probabilities, ord=1)
    
        # Choose an element from R based on the probabilities
        return random.choices(paths, probabilities)[0]

     

    def matched_links_traj_clean(self, waypoints):

        """
        Main map-matching function for generating baseline link trajectories from GPS sequences
        """
        final_path=[]
        for indx in range(len(waypoints)):
            if indx==0: #first linestring of utm_trajectory
                #origin
                b_zone=self.zone
                bbox_links=[]
                while len(bbox_links)<=self.bb_margin:
                    box=waypoints.iloc[indx].geometry.buffer(b_zone)
                    bbox_links = self.edges.loc[self.edges.intersects(box)]
                    b_zone=b_zone+10                 
                
                
                nearby_link=[bbox_links.iloc[[i]] for i in range(len(bbox_links))]
                    
                n_u= [idx[0] for link in nearby_link for idx in link.index ]
                n_v= [idx[1] for link in nearby_link for idx in link.index ]
                nodes_o=list(set(list(set(n_u))+list(set(n_v)))) #selects endpoints (u and v)   

            elif indx==len(waypoints)-1: # final linestring of utm_trajectory

                #destination
                b_zone=self.zone
                bbox_links=[]
                while len(bbox_links)<=self.bb_margin:
                    box=waypoints.iloc[indx].geometry.buffer(b_zone)
                    bbox_links = self.edges.loc[self.edges.intersects(box)]
                    b_zone=b_zone+10 
                
                
                nearby_link=[bbox_links.iloc[[i]] for i in range(len(bbox_links))]
                    
                n_u= [idx[0] for link in nearby_link for idx in link.index ]
                n_v= [idx[1] for link in nearby_link for idx in link.index ]
                nodes_d=list(set(list(set(n_u))+list(set(n_v)))) #selects endpoints (u and v)    

                paths, distances = self.gen_path_list(nodes_o, nodes_d)
                if len(paths)>0:
                    selected_path=paths[np.argmin(distances)]
                    # selected_path = self.exponential(paths, distances)
                    final_path.append(selected_path)
                
            else:
                #middle point
                b_zone=self.zone
                bbox_links=[]
                while len(bbox_links)<=self.bb_margin: # we used fc margin for non origin and destination points
                    box=waypoints.iloc[indx].geometry.buffer(b_zone)
                    bbox_links = self.edges.loc[self.edges.intersects(box)]
                    b_zone=b_zone+10   

                nearby_link=[bbox_links.iloc[[i]] for i in range(len(bbox_links))]
                # n_u= [idx[0] for link in nearby_link for idx in link.index ]
                n_v= [idx[1] for link in nearby_link for idx in link.index ]
                nodes_d=list(set(n_v))#selects endpoints (ony v)   
                
                paths, distances = self.gen_path_list(nodes_o, nodes_d)
                if len(paths)>0:
                    selected_path=paths[np.argmin(distances)]
                    # selected_path = self.exponential(paths, distances)
                    nodes_o = [selected_path[-1]]
                    final_path.append(selected_path)
                
        return final_path


    def matched_links_traj_noisy(self, waypoints):
          
        """
        Main map-matching function for generating DPMM link trajectories from GPS sequences with respect to baselien link trajectories
        """
     
        final_path=[]
        for indx in range(len(waypoints)):
            if indx==0: #first linestring of utm_trajectory
                #origin
                b_zone=self.zone
                bbox_links=[]
                # bbox_links_fc=[]
                while len(bbox_links)<=self.bb_margin:# or len(bbox_links_fc)<=self.bb_margin_fc:
                    box=waypoints[indx].buffer(b_zone)
                    bbox_links = self.edges.loc[self.edges.intersects(box)]
                    # bbox_links_fc = bbox_links.loc[bbox_links.func_class==self.links.func_class.iloc[0]] #select the FC of origin or first link in the list
                    b_zone=b_zone+10  
                                    

                link_id=self.links.osmid.iloc[[0]].iloc[0]
                differ = Differential(int(str(link_id)[2:]))
                
                lat_long_o=utm.to_latlon(waypoints[indx].x, waypoints[indx].y, self.utm_zone_number, self.utm_zone_letter)        
                
                noisy_dp=differ.addPolarNoiseCartesian_UCD(self.eps, lat_long_o, b_zone/2)                
                utm_point=utm.from_latlon(noisy_dp[0], noisy_dp[1])
                n_point=shp.geometry.Point((utm_point[0], utm_point[1]))
                
                # bbox_links_fc=[]
                b_zone=self.zone
                while len(bbox_links)<=self.bb_margin:
                    box=n_point.buffer(b_zone)
                    bbox_links = self.edges.loc[self.edges.intersects(box)]
                    # bbox_links_fc = bbox_links.loc[bbox_links.func_class==self.links.func_class.iloc[0]] #select the FC of origin or first link in the list
                    b_zone=b_zone+10                 
                
                
                nearby_link=[bbox_links.iloc[[i]] for i in range(len(bbox_links))]
                # nearby_link = [bbox_links.loc[bbox_links.func_class==self.links.func_class.iloc[0]]] #select the FC of origin or first link in the list
                    
                n_u= [idx[0] for link in nearby_link for idx in link.index ]
                n_v= [idx[1] for link in nearby_link for idx in link.index ]
                nodes_o=list(set(list(set(n_u))+list(set(n_v)))) #selects endpoints (u and v)   

            elif indx==len(waypoints)-1: # final linestring of utm_trajectory

                #destination
                b_zone=self.zone
                bbox_links=[]
                # bbox_links_fc=[]
                while len(bbox_links)<=self.bb_margin:# or len(bbox_links_fc)<=self.bb_margin_fc:
                    box=waypoints[indx].buffer(b_zone)
                    bbox_links = self.edges.loc[self.edges.intersects(box)]
                    # bbox_links_fc = bbox_links.loc[bbox_links.func_class==self.links.func_class.iloc[-1]] #select the FC of origin or first link in the list
                    b_zone=b_zone+10

                # nearby_link=[bbox_links.iloc[[i]] for i in range(len(bbox_links))]
                                    
                link_id=self.links.osmid.iloc[[-1]].iloc[0]
                differ = Differential(int(str(link_id)[2:]))
                
                lat_long_d=utm.to_latlon(waypoints[indx].x, waypoints[indx].y, self.utm_zone_number, self.utm_zone_letter)        
                
                noisy_dp=differ.addPolarNoiseCartesian_UCD(self.eps, lat_long_d, b_zone/2)                
                u_point=utm.from_latlon(noisy_dp[0], noisy_dp[1])
                n_point=shp.geometry.Point((u_point[0], u_point[1]))

                
                # bbox_links_fc=[]
                b_zone=self.zone
                while len(bbox_links)<=self.bb_margin:
                    box=n_point.buffer(b_zone)
                    bbox_links = self.edges.loc[self.edges.intersects(box)]
                    # bbox_links_fc = bbox_links.loc[bbox_links.func_class==self.links.func_class.iloc[-1]] #select the FC of origin or first link in the list
                    b_zone=b_zone+10 
                
                
                nearby_link = [bbox_links.iloc[[i]] for i in range(len(bbox_links))]
                # nearby_link = [bbox_links.loc[bbox_links.func_class==self.links.func_class.iloc[-1]]] #select the FC of origin or first link in the list
                    
                n_u= [idx[0] for link in nearby_link for idx in link.index ]
                n_v= [idx[1] for link in nearby_link for idx in link.index ]
                nodes_d=list(set(list(set(n_u))+list(set(n_v)))) #selects endpoints (u and v)    

                paths, distances = self.gen_path_list(nodes_o, nodes_d)
                if len(paths)>0:
                    # selected_path=paths[np.argmin(distances)]
                    selected_path = self.exponential(paths, distances)
                    final_path.append(selected_path)
                
            else:
                #middle point
                b_zone=self.zone
                bbox_links=[]
                while len(bbox_links)<=self.bb_margin: # we used fc margin for non origin and destination points
                    box=waypoints[indx].buffer(b_zone)
                    bbox_links = self.edges.loc[self.edges.intersects(box)]
                    b_zone=b_zone+10   

                nearby_link=[bbox_links.iloc[[i]] for i in range(len(bbox_links))]
                # n_u= [idx[0] for link in nearby_link for idx in link.index ]
                n_v= [idx[1] for link in nearby_link for idx in link.index ]
                nodes_d=list(set(n_v))#selects endpoints (ony v)   
                
                paths, distances = self.gen_path_list(nodes_o, nodes_d)
                if len(paths)>0:
                    # selected_path=paths[np.argmin(distances)]
                    selected_path = self.exponential(paths, distances)
                    nodes_o = [selected_path[-1]]
                    final_path.append(selected_path)

        return final_path
    
    def final_edge_path(self, paths):
        """
        Helper function connects the sequence of paths to have a final single path from origin to destination.
        """
        full_path=[]
        for f in paths:
            full_path+=f
        final = [i[0] for i in groupby(full_path)]
        return final
    
        
    def trajectory_points(self, utm_trajectory):
        """
        Helper function extracts the GPS points from the utm_trajectory file for doing map-matching on baseline link trajectories. 
        """
     
        points = utm_trajectory.geometry.apply(lambda x: shp.geometry.Point(x.coords[0]))
        points=points.to_frame()

        return points               
    
    def remove_edges(self, path):
        """
        Helper function as a postprocessing for DPMM trajectories that removes the loops from the final path. 
        """     
     
        removed_path = []
        
        for i in range(len(path)):
            if path[i] not in removed_path:
                removed_path.append(path[i])
            else:
                while removed_path[-1]!=path[i]:
                    removed_path.pop()
                    
        return removed_path

    def sample_waypoints(self, utm_trajectory):
        """
        Helper function samples the waypoints for DPMM.
        """             

        lat_lng_trj=ox.project_gdf(utm_trajectory,to_latlong=True)
        points=lat_lng_trj['geometry'].to_list()

        
        lat=[p.y for p in points]
        lng=[p.x for p in points]
        np_trj=np.array([lat, lng]).transpose()

        waypoints_list=rdp(np_trj, epsilon=0.001)

        #convert lat long points to utm coordinates
        u_points_list=[utm.from_latlon(wp[0], wp[1]) for wp in waypoints_list]
        waypoints = [shp.geometry.Point((up[0], up[1])) for up in u_points_list]
                
        return waypoints
    
    def map_matcher_clean(self, file_name):
        """
        Applies whole map-mathcing pipeline to GPS trajectories for clean link trajectories.
        """     
        
        try:
        
            utm_trajectory_1 = self.load_trajectory(file_name)
            utm_trajectory = utm_trajectory_1.loc[utm_trajectory_1.intersects(ROI)].reset_index(drop=True)
            # df=utm_trajectory['time'].astype('datetime64[ns]')
        
            if len(utm_trajectory)>1: 

                points = self.trajectory_points(utm_trajectory)
                path_list = self.matched_links_traj_clean(points)

                final_path = self.final_edge_path(path_list)
                
                final_path_edges = self.path_to_df(final_path)
                final_path_edges['name'] = file_name                
                final_path_edges = ox.project_gdf(final_path_edges,to_latlong=True)    
                final_path_edges.to_file(os.path.join(self.clean_dir,file_name),driver='GeoJSON')                

        except Exception as e:
            print("Clean map-matching for {} resulted in error: {}".format(file_name,e))

    def map_matcher_noisy(self, file_name):
        """
        Applies whole DPMM pipeline to GPS trajectories for privacy-preserved link trajectories.
        """        
        
        try:
        
            utm_trajectory_1 = self.load_trajectory(file_name)
            utm_trajectory = utm_trajectory_1.loc[utm_trajectory_1.intersects(ROI)].reset_index(drop=True)
        
            if len(utm_trajectory)>1: 
                self.links = ox.project_gdf(gpd.read_file(self.clean_dir+file_name))

                sample_points=self.sample_waypoints(utm_trajectory)                
                path_list = self.matched_links_traj_noisy(sample_points)

                node_sequence = self.final_edge_path(path_list)
                final_path = self.remove_edges(node_sequence)
                
                final_path_edges = self.path_to_df(final_path)
                final_path_edges['name'] = file_name                
                final_path_edges = ox.project_gdf(final_path_edges,to_latlong=True)    
                final_path_edges.to_file(os.path.join(self.find_dir,file_name),driver='GeoJSON')

        except Exception as e:
            print("Noisy map matching for {} resulted in error: {}".format(file_name,e))
        

if __name__ == "__main__":
    # Official San Francisco example entry point.  The import guard is the only
    # local change to this file: it lets the Beijing adapter instantiate the
    # unmodified MapMatching class and its original RDP/noise/path routines.
    place='San Francisco'
    edges, nodes, subgraph, ROI = select_region(place)

    zone=25
    unproc_dir=os.getcwd()+'/SF_taxi_dataset/unprocessed_trajectories/'
    clean_dir=os.getcwd()+'/SF_taxi_dataset/A_star_clean/'

    mm=MapMatching(zone, place, edges, nodes, subgraph, unproc_dir, clean_dir)
    if not os.path.exists(clean_dir):
        os.makedirs(clean_dir)    
    for file_name in os.listdir(unproc_dir):
        mm.map_matcher_clean(file_name)

    #pool = mp.Pool(8)    
    #pool.map(mm.map_matcher_clean, [file_name for file_name in os.listdir(unproc_dir)])        
    #pool.close()

    eps_all=[0.05,0.1,1,1.5,2,5,10,15,20]
    eps_2_all=['005','01','1','1_5','2','5','10','15','20']

    # eps_all=[1]
    # eps_2_all=['1']

    for eps, eps_2 in zip(eps_all, eps_2_all):

        find_dir=os.getcwd()+'/SF_taxi_dataset/A_star_NoiseOD_waypoint_RLoop_ACSAC/A*_noisy_trajs_'+eps_2+'/'
        
        mm.folder_init(eps, find_dir)
        if not os.path.exists(find_dir):
            os.makedirs(find_dir)    
        for file_name in os.listdir(unproc_dir):
            mm.map_matcher_noisy(file_name)
        
        # pool = mp.Pool(mp.cpu_count())    
        # pool = mp.Pool(8)    
        # pool.map(mm.map_matcher_noisy, [file_name for file_name in os.listdir(unproc_dir)])        
        # pool.close()
