# -*- coding: utf-8 -*-
"""Non-graphical part of the Loop step in a MolSSI workflow"""

import logging
import molssi_workflow
from molssi_workflow import units, Q_, data  # nopep8
from molssi_util import variable_names

logger = logging.getLogger(__name__)


class Loop(molssi_workflow.Node):
    def __init__(self,
                 workflow=None,
                 extension=None):
        '''Setup the non-graphical part of the Loop step in a
        MolSSI workflow.

        Keyword arguments:
        '''
        logger.debug('Creating Loop {}'.format(self))

        self.loop_type = 'For'
        self.variable = 'i'
        self.values = []
        self.first_value = 1
        self.last_value = 10
        self.increment = 1
        self.units = ''
        self.tablename = 'table1'
        self.table = None
        self.column_to_variable = None
        self.variable_to_column = None

        self._loop_value = None

        super().__init__(
            workflow=workflow,
            title='Loop',
            extension=extension)

    def run(self):
        """Run a Loop step.
        """

        if self.loop_type == 'For':
            if self._loop_value is None:
                print('For {} from {} to {} by {}'.format(
                    self.variable, self.first_value,
                    self.last_value, self.increment))
                logger.info('For {} from {} to {} by {}'.format(
                    self.variable, self.first_value,
                    self.last_value, self.increment))
                logger.info('Initializing loop')
                self._loop_value = self.first_value
                molssi_workflow.workflow_variables[self.variable] = \
                    self._loop_value
            else:
                self._loop_value += self.increment
                molssi_workflow.workflow_variables[self.variable] = \
                    self._loop_value
                if self._loop_value > self.last_value:
                    self._loop_value = None
                    logger.info('The loop over {} from {} to {} by {}'.format(
                        self.variable, self.first_value,
                        self.last_value, self.increment) +
                          ' finished successfully'
                    )
                    logger.info('Exiting loop')
                    # return the next node after the loop
                    for edge in self.workflow.edges(self, direction='out'):
                        if edge['label'] == 'exit':
                            logger.debug('Loop, next node is: {}'
                                         .format(edge.node2))
                            return edge.node2
                    # loop is the last node in the workflow
                    logger.debug('Reached the end of the workflow')
                    return None
            logger.info('    Loop value = {}'.format(self._loop_value))
        elif self.loop_type == 'Foreach':
            print('Foreach {}'.format(self.variable))
            logger.info('Foreach {}'.format(self.variable))
        elif self.loop_type == 'For rows in table':
            if self._loop_value is None:
                self.table = \
                    molssi_workflow.workflow_variables[self.tablename]['table']
                logger.info(
                    'Initialize loop over {} rows in table {}'
                    .format(self.table.shape[0], self.tablename)
                )
                self._loop_value = -1
                self.variable_to_column = {}
                self.column_to_variable = {}
                for column in self.table.columns:
                    # make a nice Python variable by removing e.g. blanks
                    column_variable = variable_names.clean(column)
                    logger.debug('  column {} --> {}'
                                 .format(column, column_variable))
                    self.column_to_variable[column] = column_variable
                    self.variable_to_column[column_variable] = column
            self._loop_value += 1
            if self._loop_value >= self.table.shape[0]:
                self._loop_value = None
                logger.info('The loop over table ' +
                            self.tablename +
                            ' finished successfully'
                )
                logger.info('Exiting loop')
                # return the next node after the loop
                for edge in self.workflow.edges(self, direction='out'):
                    if edge['label'] == 'exit':
                        logger.debug('Loop, next node is: {}'
                                     .format(edge.node2))
                        return edge.node2
                    # loop is the last node in the workflow
                logger.debug('Reached the end of the workflow')
                return None
                
            row = self.table.iloc[self._loop_value]
            for column in self.table.columns:
                value = row[column]
                variable = self.column_to_variable[column]
                molssi_workflow.workflow_variables[variable] = value
                logger.debug('  {} = {}'.format(variable, value))
            
        for edge in self.workflow.edges(self, direction='out'):
            if edge['label'] == 'loop':
                logger.debug('Loop, first node of loop is: {}'
                             .format(edge.node2))
                # Add the iteration to the ids so the directory structure is
                # reasonable
                self.workflow.reset_visited()
                self.set_subids(
                    (*self._id, 'iter_{}'.format(self._loop_value))
                )

                return edge.node2

        # No loop body? just go on?
        return super().run()

    def default_edge_label(self):
        """Return the default label of the edge. Usually this is ''
        but for nodes with two or more edges leaving them, such as a loop, this
        method will return an appropriate default for the current edge. For
        example, by default the first edge emanating from a loop-node is the
        'loop' edge; the second, the 'exit' edge.

        A return value of 'too many' indicates that the node exceeds the number
        of allowed exit edges.
        """

        logger.debug("seeing what super node says!")
        n_edges = super().default_edge_label()
        logger.debug('super.default_edge_label, n_edges = {}'.format(n_edges))

        # how many outgoing edges are there?
        n_edges = len(self.workflow.edges(self, direction='out'))

        print('printing all edges')
        self.workflow.print_edges()

        logger.debug('loop.default_edge_label, n_edges = {}'.format(n_edges))

        if n_edges == 0:
            return "loop"
        elif n_edges == 1:
            return "exit"
        else:
            return "too many"

    def describe(self, indent='', json_dict=None):
        """Write out information about what this node will do
        If json_dict is passed in, add information to that dictionary
        so that it can be written out by the controller as appropriate.
        """

        self.visited = True
        self.job_output('Step ' + '.'.join(str(e) for e in self._id) +
                        ': ' + self.title)

        # Print the body of the loop
        indent = indent + '    '
        for edge in self.workflow.edges(self, direction='out'):
            if edge['label'] == 'loop':
                logger.debug('Loop, first node of loop is: {}'
                             .format(edge.node2))
                next_node = edge.node2
                while next_node and not next_node.visited:
                    next_node = next_node.describe(indent)

        next_node = self.next()
        if not next_node or next_node.visited:
            return None
        else:
            return next_node

    def set_id(self, node_id=()):
        """Sequentially number the loop subnodes"""
        logger.debug('Setting ids for loop {}'.format(self))
        if self.visited:
            return None
        else:
            self.visited = True
            self._id = node_id
            self.set_subids(self._id)

    def set_subids(self, node_id=()):
        """Set the ids of the nodes in the loop"""
        for edge in self.workflow.edges(self, direction='out'):
            if edge['label'] == 'loop':
                logger.debug('Loop, first node of loop is: {}'
                             .format(edge.node2))
                next_node = edge.node2
                n = 0
                while next_node and next_node != self:
                    next_node = next_node.set_id((*node_id, str(n)))
                    n += 1
        logger.debug('end of loop')
        return self.next()

