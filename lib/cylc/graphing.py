#!/usr/bin/env python

#C: THIS FILE IS PART OF THE CYLC SUITE ENGINE.
#C: Copyright (C) 2008-2014 Hilary Oliver, NIWA
#C:
#C: This program is free software: you can redistribute it and/or modify
#C: it under the terms of the GNU General Public License as published by
#C: the Free Software Foundation, either version 3 of the License, or
#C: (at your option) any later version.
#C:
#C: This program is distributed in the hope that it will be useful,
#C: but WITHOUT ANY WARRANTY; without even the implied warranty of
#C: MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#C: GNU General Public License for more details.
#C:
#C: You should have received a copy of the GNU General Public License
#C: along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Cylc suite graphing module. Modules relying on this should test for
ImportError due to pygraphviz/graphviz not being installed."""

import re
import pygraphviz
import TaskID
from cycling.loader import get_point, get_point_relative, get_interval
from graphnode import graphnode

# TODO: Do we still need autoURL below?

class CGraphPlain( pygraphviz.AGraph ):
    """Directed Acyclic Graph class for cylc dependency graphs."""

    def __init__( self, title, suite_polling_tasks={} ):
        self.title = title
        pygraphviz.AGraph.__init__( self, directed=True )
        # graph attributes
        # - label (suite name)
        self.graph_attr['label'] = title
        self.suite_polling_tasks = suite_polling_tasks

    def node_attr_by_taskname( self, node_string ):
        name, point_string = TaskID.split( node_string )
        if name in self.task_attr:
            return self.task_attr[name]
        else:
            return []

    def style_edge( self, left, right ):
        pass

    def style_node( self, node_string, autoURL, base=False ):
        node = self.get_node( node_string )
        name, point_string = TaskID.split( node_string )
        label = name
        if name in self.suite_polling_tasks:
            label += "\\n" + self.suite_polling_tasks[name][3]
        label += "\\n" + point_string
        node.attr[ 'label' ] = label
        if autoURL:
            if base:
                # TODO - This is only called from cylc_add_edge in this
                # base class ... should it also be called from add_node?
                node.attr[ 'URL' ] = 'base:' + node_string
            else:
                node.attr['URL'] = node_string

    def cylc_add_node( self, node_string, autoURL, **attr ):
        pygraphviz.AGraph.add_node( self, node_string, **attr )
        self.style_node( node_string, autoURL )

    def cylc_add_edge( self, left, right, autoURL, **attr ):
        if left == None and right == None:
            pass
        elif left == None:
            self.cylc_add_node( right, autoURL )
        elif right == None:
            self.cylc_add_node( left, autoURL )
        elif left == right:
            # pygraphviz 1.1 adds a node instead of a self-edge
            # which results in a KeyError in get_edge() below.
            self.cylc_add_node( left, autoURL )
        else:
            pygraphviz.AGraph.add_edge( self, left, right, **attr )
            self.style_node( left, autoURL, base=True )
            self.style_node( right, autoURL, base=True )
            self.style_edge( left, right )

    def add_edges( self, edges, ignore_suicide=False ):
        edges.sort() # TODO: does sorting help layout stability?
        for edge in edges:
            left, right, dashed, suicide, conditional = edge
            if suicide and ignore_suicide:
                continue
            if conditional:
                if suicide:
                    style='dashed'
                    arrowhead='odot'
                else:
                    style='solid'
                    arrowhead='onormal'
            else:
                if suicide:
                    style='dashed'
                    arrowhead='dot'
                else:
                    style='solid'
                    arrowhead='normal'
            if dashed:
                # override
                style='dashed'

            penwidth = 2

            self.cylc_add_edge(
                left, right, True, style=style, arrowhead=arrowhead,
                penwidth=penwidth
            )

    def add_cycle_point_subgraphs( self, edges ):
        """Draw nodes within cycle point groups (subgraphs)."""
        point_string_id_map = {}
        for edge_entry in edges:
            for id_ in edge_entry[:2]:
                if id_ is None:
                    continue
                point_string = TaskID.split(id_)[1]
                point_string_id_map.setdefault(point_string, [])
                point_string_id_map[point_string].append(id_)
        for point_string, ids in point_string_id_map.items():
            self.add_subgraph(
                nbunch=ids, name="cluster_" + point_string,
                label=point_string, fontsize=28, rank="max", style="dashed"
            )

    def add_subgraph(self, nbunch=None, name=None, **attr):
        """Return subgraph induced by nodes in nbunch.

        Overrides (but does the same thing as) pygraphviz's
        AGraph.add_subgraph method.

        """

        name = name.encode(self.encoding)

        handle = pygraphviz.graphviz.agsubg(
            self.handle, name, 1)

        subgraph = pygraphviz.AGraph(
            handle=handle, name=name,
            strict=self.strict, directed=self.directed,
            **attr
        )

        nodes = self.prepare_nbunch(nbunch)
        subgraph.add_nodes_from(nodes)

        for left, right in self.edges():
            if left in subgraph and right in subgraph: 
                subgraph.add_edge(left, right)

        return subgraph


class CGraph( CGraphPlain ):
    """Directed Acyclic Graph class for cylc dependency graphs.
    This class automatically adds node and edge attributes
    according to the suite.rc file visualization config."""

    def __init__( self, title, suite_polling_tasks={}, vizconfig={} ):

        # suite.rc visualization config section
        self.vizconfig = vizconfig
        CGraphPlain.__init__( self, title, suite_polling_tasks )

        # graph attributes
        # - default node attributes
        for item in vizconfig['default node attributes']:
            attr, value = re.split( '\s*=\s*', item )
            self.node_attr[ attr ] = value
        # - default edge attributes
        for item in vizconfig['default edge attributes']:
            attr, value = re.split( '\s*=\s*', item )
            self.edge_attr[ attr ] = value

        # non-default node attributes by task name
        # TODO - ERROR CHECKING FOR INVALID TASK NAME
        self.task_attr = {}

        for item in self.vizconfig['node attributes']:
            if item in self.vizconfig['node groups']:
                # item is a group of tasks
                for task in self.vizconfig['node groups'][item]:
                    # for each task in the group
                    for attr in self.vizconfig['node attributes'][item]:
                        if task not in self.task_attr:
                            self.task_attr[task] = []
                        self.task_attr[task].append( attr )
            else:
                # item must be a task name
                for attr in self.vizconfig['node attributes'][item]:
                    if item not in self.task_attr:
                        self.task_attr[item] = []
                    self.task_attr[item].append( attr )

    def style_node( self, node_string, autoURL, base=False ):
        super( self.__class__, self ).style_node(
            node_string, autoURL, False)
        node = self.get_node(node_string)
        for item in self.node_attr_by_taskname( node_string ):
            attr, value = re.split( '\s*=\s*', item )
            node.attr[ attr ] = value
        if self.vizconfig['use node color for labels']:
            node.attr['fontcolor'] = node.attr['color']

    def style_edge( self, left, right ):
        super( self.__class__, self ).style_edge( left, right )
        left_node = self.get_node(left)
        edge = self.get_edge(left, right)
        if self.vizconfig['use node color for edges']:
            if left_node.attr['style'] == 'filled':
                edge.attr['color'] = left_node.attr['fillcolor']
            else:
                edge.attr['color'] = left_node.attr['color']


class edge( object):
    def __init__( self, left, right, sequence, sasl=False, suicide=False,
                  conditional=False ):
        """contains qualified node names, e.g. 'foo[T-6]:out1'"""
        self.left = left
        self.right = right
        self.sequence = sequence
        self.sasl = sasl
        self.suicide = suicide
        self.conditional = conditional

    def get_right( self, inpoint, start_point, not_first_cycle, raw,
                   startup_only ):
        inpoint_string = str(inpoint)
        if self.right == None:
            return None
        first_cycle = not not_first_cycle
        if self.right in startup_only:
            if not first_cycle or raw:
                return None

        # strip off special outputs
        self.right = re.sub( ':\w+', '', self.right )

        return TaskID.get( self.right, inpoint_string )

    def get_left( self, inpoint, start_point, not_first_cycle, raw,
                  startup_only, base_interval ):

        first_cycle = not not_first_cycle

        # strip off special outputs
        left = re.sub( ':[\w-]+', '', self.left )

        if left in startup_only:
            if not first_cycle or raw:
                return None

        left_graphnode = graphnode(left, base_interval=base_interval)
        if left_graphnode.offset_is_from_ict:
            point = get_point_relative(left_graphnode.offset_string,
                                       start_point)
        elif left_graphnode.offset_string:
            point = get_point_relative(left_graphnode.offset_string, inpoint)
        else:
            point = inpoint
        name = left_graphnode.name

        return TaskID.get( name, str(point) )
