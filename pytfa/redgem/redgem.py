#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
.. module:: redgem
   :platform: Unix, Windows
   :synopsis: RedGEM Algorithm

.. moduleauthor:: pyTFA team

Model class
"""

import os
from pytfa.io import import_matlab_model

import networkx as nx
from cobra import Metabolite, Reaction, Model
from copy import deepcopy


class RedGEM:

    def __init__(self, gem, core_subsystems, carbon_uptake, cofactor_pairs, small_metabolites,
                 inorganics, d, extracellular_system, subsystem_names=(), n=0):
        """
        A class encapsulating the RedGEM algorithm

        :param gem: The studied GEM
        :param core_subsystems: List of core subsystems names
        :param carbon_uptake:
        :param cofactor_pairs: List of cofactor pairs id
        :param small_metabolites: List of small metabolites id
        :param inorganics: List of inorganics id
        :param d: Degree
        :param extracellular_system:
        :param subsystem_names:
        :param n: User parameter
        """
        self._gem = gem
        self._redgem = gem.copy()
        self._redgem.name = 'redgem'
        self._reduced_model = Model('graph')
        self._graph = nx.DiGraph()

        # Subsystems
        self._subsystem_names = subsystem_names
        self._subsystem_count = len(subsystem_names)
        self._core_subsystems = core_subsystems

        # Sets of core reactions and metabolites
        self._rcore = set()
        self._mcore = set()

        # Dicts to save extracted reactions and metabolites for each subsystem
        # TODO: Improve structure definition
        dict_of_lists_of_sets = {}
        for name in subsystem_names:
            dict_of_lists_of_sets[name] = [set() for _ in range(d+1)]
        dict_of_dicts_of_lists_of_sets = {}
        for name in subsystem_names:
            dict_of_dicts_of_lists_of_sets[name] = deepcopy(dict_of_lists_of_sets)
        dict_of_int = {}
        for name in subsystem_names:
            dict_of_int[name] = -1
        dict_of_dicts_of_int = {}
        for name in subsystem_names:
            dict_of_dicts_of_int[name] = deepcopy(dict_of_int)

        self._subsystem_reactions = {}
        self._subsystem_reactions_id = {}
        self._intermediate_reactions_id = deepcopy(dict_of_dicts_of_lists_of_sets)
        self._subsystem_metabolites = {}
        self._subsystem_metabolites_id = {}
        self._intermediate_metabolites_id = deepcopy(dict_of_dicts_of_lists_of_sets)
        self._intermediate_paths = deepcopy(dict_of_dicts_of_lists_of_sets)
        self._min_distance_sub_to_sub = deepcopy(dict_of_dicts_of_int)

        self._intermediate_extracellular_paths = deepcopy(dict_of_lists_of_sets)
        self._intermediate_extracellular_metabolites_id = deepcopy(dict_of_lists_of_sets)
        self._intermediate_extracellular_reactions_id = deepcopy(dict_of_lists_of_sets)

        self._path_dict = {}

        # Save others parameters
        self._carbon_uptake = carbon_uptake
        self._cofactor_pairs = cofactor_pairs
        self._small_metabolites = small_metabolites
        self._inorganics = inorganics
        self._d = d
        self._extracellular_system = extracellular_system
        self._n = n

    def extract_core_reactions(self):
        for rxn in self._gem.reactions:
            if rxn.subsystem in self._core_subsystems:
                self._rcore.add(rxn)

    def extract_core_metabolites(self):
        for rxn in self._rcore:
            for metabolite in rxn.metabolites:
                metabolite_id = metabolite.id
                if metabolite_id in self._cofactor_pairs \
                        or metabolite_id in self._small_metabolites \
                        or metabolite_id in self._inorganics:
                    continue
                self._mcore.add(metabolite)

    def extract_subsystem_reactions(self, subsystem):
        """
        Extracts all reactions of a subsystem and stores them and their id in the corresponding
        dictionary.

        :param subsystem: Name of the subsystem
        :return: Extracted reactions
        """
        rxns = set()
        rxns_id = set()
        for rxn in self._gem.reactions:
            if rxn.subsystem == subsystem:
                rxns.add(rxn)
                rxns_id.add(rxn.id)
        self._subsystem_reactions[subsystem] = rxns
        self._subsystem_reactions_id[subsystem] = rxns_id
        return rxns

    def extract_subsystem_metabolites(self, subsystem):
        """
        Extracts all metabolites of a subsystem and stores them and their id in the corresponding
        dictionary.

        :param subsystem: Name of the subsystem
        :return: Extracted metabolites
        """
        subsystem_rxns = self._subsystem_reactions[subsystem]
        metabolites = set()
        metabolites_id = set()
        for rxn in subsystem_rxns:
            for metabolite in rxn.metabolites:
                metabolite_id = metabolite.id
                if metabolite_id in self._cofactor_pairs \
                        or metabolite_id in self._small_metabolites \
                        or metabolite_id in self._inorganics:
                    continue
                metabolites.add(metabolite)
                metabolites_id.add(metabolite.id)
        self._subsystem_metabolites[subsystem] = metabolites
        self._subsystem_metabolites_id[subsystem] = metabolites_id
        return metabolites

    def create_new_stoichiometric_matrix(self):
        """
        Extracts the new graph without the small metabolites, inorganics and cofactor pairs.

        :return: Networkx graph of the new network
        """
        kept_rxns = []
        kept_metabolites = set()
        for rxn in self._gem.reactions:
            metabolites = {}
            for metabolite, coefficient in rxn.metabolites.items():
                metabolite_id = metabolite.id
                if metabolite_id in self._cofactor_pairs \
                        or metabolite_id in self._small_metabolites \
                        or metabolite_id in self._inorganics:
                    continue
                new_metabolite = Metabolite(metabolite_id,
                                            formula=metabolite.formula,
                                            name=metabolite.name,
                                            compartment=metabolite.compartment)
                metabolites[new_metabolite] = coefficient
                kept_metabolites.add(metabolite)
            new_rxn = Reaction(rxn.id,
                               name=rxn.name,
                               subsystem=rxn.subsystem,
                               lower_bound=rxn.lower_bound,
                               upper_bound=rxn.upper_bound)
            new_rxn.add_metabolites(metabolites)
            kept_rxns.append(new_rxn)
        self._reduced_model.add_reactions(kept_rxns)

        paths_struct = [{} for _ in range(self._d+1)]  # Comprehension list to create multiple dicts
        to_struct = [""] * (self._d+1)
        for metabolite in kept_metabolites:
            self._graph.add_node(metabolite.id, paths=paths_struct, to=to_struct)
        for rxn in kept_rxns:
            for reactant in rxn.reactants:
                for product in rxn.products:
                    self._graph.add_edge(reactant.id, product.id, rxn_id=rxn.id, weight=1)
        return self._graph

    def breadth_search_subsystems_paths_length_d(self, subsystem_i, subsystem_j, d):
        for metabolite_id in self._subsystem_metabolites_id[subsystem_i]:
            # Find metabolites at a distance d from metabolite_id
            ancestors = {}
            frontier = {metabolite_id}
            explored = {metabolite_id}
            for i in range(d):
                new_nodes = set()
                for current_node in frontier:
                    for new_node in set(self._graph.adj[current_node]):
                        if self.is_node_allowed(new_node, i, explored, subsystem_i, subsystem_j, d):
                            new_nodes.add(new_node)
                            # new_node can already be in ancestors if there are 2 paths of same
                            # length to it
                            if new_node in ancestors:
                                ancestors[new_node].append(current_node)
                            else:
                                ancestors[new_node] = [current_node]
                explored = explored.union(new_nodes)
                frontier = new_nodes
            # Handle d = 0 case, since it didn't go through the loop
            if d == 0 and metabolite_id not in self._subsystem_metabolites_id[subsystem_j]:
                frontier = {}
            """
            self._graph.nodes[metabolite_id]['paths'][d] = ancestors
            self._graph.nodes[metabolite_id]['to'][d] = frontier
            for node in frontier:
                if 'from_'+subsystem_i in self._graph.nodes[node]:
                    self._graph.nodes[node]['from_'+subsystem_i].append(metabolite_id)
                else:
                    self._graph.nodes[node]['from_'+subsystem_i] = [metabolite_id]
            """
            # Retrieve and save metabolites, reactions and paths
            for node in frontier:
                paths = self.retrieve_all_paths(node, metabolite_id, ancestors)
                self._intermediate_paths[subsystem_i][subsystem_j][d] = \
                    self._intermediate_paths[subsystem_i][subsystem_j][d].union(set(paths))
                self.retrieve_intermediate_metabolites_and_reactions(paths, subsystem_i,
                                                                     subsystem_j, d)

    def is_node_allowed(self, node, i, explored, subsystem_i, subsystem_j, d):
        # The new node is added if it is not already explored, if it is not in the source subsystem,
        # and if it is not in the destination subsystem, except if it is the last round
        # of exploration
        if node in explored:
            return False
        if subsystem_i != subsystem_j and node in self._subsystem_metabolites_id[subsystem_i]:
            return False
        if i < d-1 and node in self._subsystem_metabolites_id[subsystem_j]:
            return False
        if i == d-1 and node not in self._subsystem_metabolites_id[subsystem_j]:
            return False
        return True

    def retrieve_all_paths(self, dest_node, src_node, ancestors, init_dict=True):
        if init_dict:
            self._path_dict = {}
        if dest_node == src_node:
            self._path_dict[dest_node] = [(src_node,)]
        if dest_node not in self._path_dict:
            new_paths = []
            for previous_node in ancestors[dest_node]:
                for path in self.retrieve_all_paths(previous_node, src_node, ancestors, False):
                    new_paths.append(path + (dest_node,))
            self._path_dict[dest_node] = new_paths
        return self._path_dict[dest_node]

    def retrieve_intermediate_metabolites_and_reactions(self, paths, subsystem_i, subsystem_j, d):
        for path in paths:
            for i in range(len(path)-1):
                reaction = self._graph[path[i]][path[i+1]]['rxn_id']
                self._intermediate_reactions_id[subsystem_i][subsystem_j][d].add(reaction)
                if i > 0:
                    self._intermediate_metabolites_id[subsystem_i][subsystem_j][d].add(path[i])

    def find_min_distance_between_subsystems(self):
        for i in self._subsystem_names:
            for j in self._subsystem_names:
                for k in range(self._d+1):
                    # If there path of length d
                    if self._intermediate_paths[i][j][k]:
                        self._min_distance_sub_to_sub[i][j] = k
                        break
                # If min distance os not found, then
                if self._min_distance_sub_to_sub[i][j] == -1:
                    pass
        return self._min_distance_sub_to_sub

    def breadth_search_extracellular_system_paths(self, subsystem, n):
        for metabolite_id in self._extracellular_system:
            # Find metabolites at a distance n from metabolite_id
            ancestors = {}
            frontier = {metabolite_id}
            explored = {metabolite_id}
            for i in range(n):
                new_nodes = set()
                for current_node in frontier:
                    for new_node in set(self._graph.adj[current_node]):
                        if self.is_node_allowed_extracellular(new_node, i, explored, subsystem, n):
                            new_nodes.add(new_node)
                            # new_node can already be in ancestors if there are 2 paths of same
                            # length to it
                            if new_node in ancestors:
                                ancestors[new_node].append(current_node)
                            else:
                                ancestors[new_node] = [current_node]
                explored = explored.union(new_nodes)
                frontier = new_nodes
            # Handle n = 0 case, since it didn't go through the loop
            if n == 0 and metabolite_id not in self._subsystem_metabolites_id[subsystem]:
                frontier = {}
            # Retrieve and save metabolites, reactions and paths
            for node in frontier:
                paths = self.retrieve_all_paths(node, metabolite_id, ancestors)
                self._intermediate_extracellular_paths[subsystem][n] = \
                    self._intermediate_extracellular_paths[subsystem][n].union(set(paths))
                self.retrieve_intermediate_extracellular_metabolites_and_reactions(paths, subsystem,
                                                                                   n)

    def is_node_allowed_extracellular(self, node, i, explored, subsystem, n):
        # The new node is added if it is not already explored, if it is not in the source subsystem,
        # and if it is not in the destination subsystem, except if it is the last round
        # of exploration
        if node in explored:
            return False
        if node in self._extracellular_system:
            return False
        if i < n-1 and node in self._subsystem_metabolites_id[subsystem]:
            return False
        if i == n-1 and node not in self._subsystem_metabolites_id[subsystem]:
            return False
        return True

    def retrieve_intermediate_extracellular_metabolites_and_reactions(self, paths, subsystem, n):
        for path in paths:
            for i in range(len(path) - 1):
                reaction = self._graph[path[i]][path[i + 1]]['rxn_id']
                self._intermediate_extracellular_reactions_id[subsystem][n].add(reaction)
                if i > 0:
                    self._intermediate_extracellular_metabolites_id[subsystem][n].add(path[i])

    def run_between_all_subsystems(self):
        for subsystem in self._subsystem_names:
            self.extract_subsystem_reactions(subsystem)
            self.extract_subsystem_metabolites(subsystem)

        for subsystem_i in self._subsystem_names:
            for subsystem_j in self._subsystem_names:
                for k in range(self._d+1):
                    self.breadth_search_subsystems_paths_length_d(subsystem_i, subsystem_j, k)

    def run_extracellular_system(self):
        for subsystem in self._subsystem_names:
            for k in range(self._n + 1):
                self.breadth_search_extracellular_system_paths(subsystem, k)

    def extract_sub_network(self):
        def extract_id(x):
            return x.id
        to_remove_metabolites = set(map(extract_id, self._gem.metabolites))
        to_remove_reactions = set(map(extract_id, self._gem.reactions))

        # Keep subsystems reactions and metabolites
        for name in self._subsystem_names:
            to_remove_reactions = to_remove_reactions - self._subsystem_reactions_id[name]
            to_remove_metabolites = to_remove_metabolites - self._subsystem_metabolites_id[name]

        # Keep intermediate reactions and metabolites
        for i in self._subsystem_names:
            for j in self._subsystem_names:
                for k in range(self._d+1):
                    to_remove_reactions = to_remove_reactions \
                                          - self._intermediate_reactions_id[i][j][k]
                    to_remove_metabolites = to_remove_metabolites \
                                            - self._intermediate_metabolites_id[i][j][k]

        # Keep extracellular metabolites
        to_remove_metabolites = to_remove_metabolites - set(self._extracellular_system)

        # Keep intermediate extracellular reactions and metabolites
        for i in self._subsystem_names:
            for k in range(self._d+1):
                to_remove_reactions = to_remove_reactions \
                                      - self._intermediate_extracellular_reactions_id[i][k]
                to_remove_metabolites = to_remove_metabolites \
                                        - self._intermediate_extracellular_metabolites_id[i][k]

        print(to_remove_metabolites, to_remove_reactions)
        self._redgem.remove_reactions(to_remove_reactions, True)
        # self._redgem.remove_metabolites(to_remove_metabolites)

    """
    def create_sub_network(self):
        to_add_metabolites_id = set()
        to_add_reactions_id = set()

        for name in self._subsystem_names:
            to_add_reactions_id = to_add_reactions_id.union(self._subsystem_reactions_id[name])
            to_add_metabolites_id = to_add_metabolites_id.union(self._subsystem_metabolites_id[name])

        for i in self._subsystem_names:
            for j in self._subsystem_names:
                for k in range(self._d+1):
                    to_add_reactions_id = to_add_reactions_id.union(self._intermediate_reactions_id[i][j][k])
                    to_add_metabolites_id = to_add_metabolites_id.union(self._intermediate_metabolites_id[i][j][k])

        to_add_reactions = []
        to_add_metabolites = []
        for reaction_id in to_add_reactions_id:
            to_add_reactions.append(self._gem.reactions.get_by_id(reaction_id))
        for metabolite_id in to_add_metabolites_id:
            to_add_metabolites.append(self._gem.metabolites.get_by_id(metabolite_id))

        self._redgem.add_reactions(to_add_reactions)
    """

    def run(self):
        self.create_new_stoichiometric_matrix()
        self.run_between_all_subsystems()
        self.run_extracellular_system()
        self.extract_sub_network()
