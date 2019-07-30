# -*- coding: utf-8 -*-
"""Non-graphical part of the Loop step in a SEAMM flowchart"""

import logging
import loop_step
import seamm
from seamm_util import ureg, Q_, units_class  # noqa: F401
import seamm_util.printing as printing
from seamm_util.printing import FormattedText as __

logger = logging.getLogger(__name__)
job = printing.getPrinter()
printer = printing.getPrinter('from_smiles')


class Loop(seamm.Node):
    def __init__(self,
                 flowchart=None,
                 extension=None):
        '''Setup the non-graphical part of the Loop step in a
        SEAMM flowchart.

        Keyword arguments:
        '''
        logger.debug('Creating Loop {}'.format(self))

        self.table_handle = None
        self.table = None
        self._loop_value = None
        self._loop_length = None

        super().__init__(
            flowchart=flowchart,
            title='Loop',
            extension=extension)

        # This needs to be after initializing subclasses...
        self.parameters = loop_step.LoopParameters()

    def description(self, P):
        """Prepare information about what this node will do
        """
        text = ''

        # Print the body of the loop
        indent = '    '
        for edge in self.flowchart.edges(self, direction='out'):
            if edge.edge_subtype == 'loop':
                logger.debug('Loop, first node of loop is: {}'
                             .format(edge.node2))
                next_node = edge.node2
                while next_node and not next_node.visited:
                    text += next_node.describe(indent)

        return text

    def describe(self, indent='', json_dict=None):
        """Write out information about what this node will do
        If json_dict is passed in, add information to that dictionary
        so that it can be written out by the controller as appropriate.
        """

        super().describe(indent, json_dict)

        P = self.parameters.values_to_dict()

        text = self.description(P)

        job.job(__(text, **P, indent=self.indent+'    '))

        return self.exit_node()

    def run(self):
        """Run a Loop step.
        """

        # Set up the directory, etc.
        super().run()

        P = self.parameters.current_values_to_dict(
            context=seamm.flowchart_variables._data
        )

        if P['type'] == 'For':
            if self._loop_value is None:
                logger.info(
                    'For {} from {} to {} by {}'.format(
                        P['variable'], P['start'], P['end'], P['step'])
                )

                logger.info('Initializing loop')
                self._loop_value = P['start']
                self.set_variable(P['variable'], self._loop_value)
                if self.variable_exists('_loop_indices'):
                    tmp = self.get_variable('_loop_indices')
                    self.set_variable(
                        '_loop_indices', (*tmp, self._loop_value)
                    )
                else:
                    self.set_variable('_loop_indices', (self._loop_value,))
                    self.set_variable('_loop_index', self._loop_value)
            else:
                self._loop_value += P['step']
                self.set_variable(P['variable'], self._loop_value)

                # Set up the index variables
                tmp = self.get_variable('_loop_indices')
                self.set_variable(
                    '_loop_indices', (*tmp[0:-1], self._loop_value,)
                )
                self.set_variable('_loop_index', self._loop_value)

                # See if we are at the end of loop
                if self._loop_value > P['end']:
                    self._loop_value = None

                    # Revert the loop index variables to the next outer loop
                    # if there is one, or remove them.
                    tmp = self.get_variable('_loop_indices')

                    if len(tmp) <= 1:
                        self.delete_variable('_loop_indices')
                        self.delete_variable('_loop_index')
                    else:
                        self.set_variable('_loop_indices', tmp[0:-1])
                        self.set_variable('_loop_index', tmp[-2])

                    logger.info(
                        ('The loop over {} from {} to {} by {}'
                         ' finished successfully').format(
                             P['variable'], P['start'], P['end'], P['step'])
                    )
                    return self.exit_node()

            logger.info('    Loop value = {}'.format(self._loop_value))
        elif P['type'] == 'Foreach':
            logger.info('Foreach {}'.format(P['variable']))
            if self._loop_value is None:
                self._loop_value = -1
                self._loop_length = len(P['values'])
                if self.variable_exists('_loop_indices'):
                    tmp = self.get_variable('_loop_indices')
                    self.set_variable('_loop_indices', (*tmp, None,))
                else:
                    self.set_variable('_loop_indices', (None,))

            self._loop_value += 1

            if self._loop_value >= self._loop_length:
                self._loop_value = None
                self._loop_length = None

                # Revert the loop index variables to the next outer loop
                # if there is one, or remove them.
                tmp = self.get_variable('_loop_indices')
                if len(tmp) <= 1:
                    self.delete_variable('_loop_indices')
                    self.delete_variable('_loop_index')
                else:
                    self.set_variable('_loop_indices', tmp[0:-1])
                    self.set_variable('_loop_index', tmp[-2])
                logger.info(
                    'The loop over value finished successfully'
                )

                # return the next node after the loop
                return self.exit_node()

            value = P['values'][self._loop_value]
            self.set_variable(P['variable'], value)

            # Set up the index variables
            tmp = self.get_variable('_loop_indices')
            self.set_variable(
                '_loop_indices', (*tmp[0:-1], self._loop_value,)
            )
            self.set_variable('_loop_index', self._loop_value)
            logger.info('    Loop value = {}'.format(value))
        elif P['type'] == 'For rows in table':
            if self._loop_value is None:
                self.table_handle = self.get_variable(P['table'])
                self.table = self.table_handle['table']
                self.table_handle['loop index'] = True

                logger.info(
                    'Initialize loop over {} rows in table {}'
                    .format(self.table.shape[0], P['table'])
                )
                self._loop_value = -1
                if self.variable_exists('_loop_indices'):
                    tmp = self.get_variable('_loop_indices')
                    self.set_variable('_loop_indices', (*tmp, None,))
                else:
                    self.set_variable('_loop_indices', (None,))
            self._loop_value += 1
            if self._loop_value >= self.table.shape[0]:
                self._loop_value = None

                self.delete_variable('_row')
                # Revert the loop index variables to the next outer loop
                # if there is one, or remove them.
                tmp = self.get_variable('_loop_indices')
                if len(tmp) <= 1:
                    self.delete_variable('_loop_indices')
                    self.delete_variable('_loop_index')
                else:
                    self.set_variable('_loop_indices', tmp[0:-1])
                    self.set_variable('_loop_index', tmp[-2])

                # and the other info in the table handle
                self.table_handle['loop index'] = False

                self.table = None
                self.table_handle = None

                logger.info(
                    'The loop over table ' + self.parameters['table'].value +
                    ' finished successfully'
                )

                # return the next node after the loop
                return self.exit_node()

            # Set up the index variables
            tmp = self.get_variable('_loop_indices')
            self.set_variable(
                '_loop_indices',
                (*tmp[0:-1], self.table.index[self._loop_value])
            )
            self.set_variable(
                '_loop_index', self.table.index[self._loop_value]
            )
            self.table_handle['current index'] = (
                self.table.index[self._loop_value]
            )

            row = self.table.iloc[self._loop_value]
            self.set_variable('_row', row)

        for edge in self.flowchart.edges(self, direction='out'):
            if edge.edge_subtype == 'loop':
                logger.info('Loop, first node of loop is: {}'
                            .format(edge.node2))
                # Add the iteration to the ids so the directory structure is
                # reasonable
                self.flowchart.reset_visited()
                self.set_subids(
                    (*self._id, 'iter_{}'.format(self._loop_value))
                )

                return edge.node2

        # No loop body? just go on?
        return self.exit_node()

    def default_edge_subtype(self):
        """Return the default subtype of the edge. Usually this is 'next'
        but for nodes with two or more edges leaving them, such as a loop, this
        method will return an appropriate default for the current edge. For
        example, by default the first edge emanating from a loop-node is the
        'loop' edge; the second, the 'exit' edge.

        A return value of 'too many' indicates that the node exceeds the number
        of allowed exit edges.
        """

        # how many outgoing edges are there?
        n_edges = len(self.flowchart.edges(self, direction='out'))

        logger.debug('loop.default_edge_subtype, n_edges = {}'.format(n_edges))

        if n_edges == 0:
            return "loop"
        elif n_edges == 1:
            return "exit"
        else:
            return "too many"

    def set_id(self, node_id=()):
        """Sequentially number the loop subnodes"""
        logger.debug('Setting ids for loop {}'.format(self))
        if self.visited:
            return None
        else:
            self.visited = True
            self._id = node_id
            self.set_subids(self._id)
            return self.exit_node()

    def set_subids(self, node_id=()):
        """Set the ids of the nodes in the loop"""
        for edge in self.flowchart.edges(self, direction='out'):
            if edge.edge_subtype == 'loop':
                logger.debug('Loop, first node of loop is: {}'
                             .format(edge.node2))
                next_node = edge.node2
                n = 0
                while next_node and next_node != self:
                    next_node = next_node.set_id((*node_id, str(n)))
                    n += 1

        logger.debug('end of loop')

    def exit_node(self):
        """The next node after the loop, if any"""

        for edge in self.flowchart.edges(self, direction='out'):
            if edge.edge_subtype == 'exit':
                logger.debug('Loop, node after loop is: {}'
                             .format(edge.node2))
                return edge.node2

        # loop is the last node in the flowchart
        logger.debug('There is no node after the loop')
        return None
