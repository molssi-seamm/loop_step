# -*- coding: utf-8 -*-

"""Non-graphical part of the Loop step in a SEAMM flowchart"""

import logging
import os.path
import traceback

import loop_step
import seamm
import seamm_util.printing as printing
from seamm_util.printing import FormattedText as __

logger = logging.getLogger(__name__)
job = printing.getPrinter()
printer = printing.getPrinter('loop')


class Loop(seamm.Node):

    def __init__(self, flowchart=None, extension=None):
        '''Setup the non-graphical part of the Loop step in a
        SEAMM flowchart.

        Keyword arguments:
        '''
        logger.debug('Creating Loop {}'.format(self))

        self.table_handle = None
        self.table = None
        self._loop_value = None
        self._loop_length = None
        self._file_handler = None

        super().__init__(
            flowchart=flowchart,
            title='Loop',
            extension=extension,
            logger=logger
        )

        # This needs to be after initializing subclasses...
        self.parameters = loop_step.LoopParameters()

    @property
    def version(self):
        """The semantic version of this module.
        """
        return loop_step.__version__

    @property
    def git_revision(self):
        """The git version of this module.
        """
        return loop_step.__git_revision__

    def description_text(self, P=None):
        """Return a short description of this step.

        Return a nicely formatted string describing what this step will
        do.

        Keyword arguments:
            P: a dictionary of parameter values, which may be variables
                or final values. If None, then the parameters values will
                be used as is.
        """

        if not P:
            P = self.parameters.values_to_dict()

        text = ''

        if P['type'] == 'For':
            subtext = 'For {variable} from {start} to {end} by {step}'
        elif P['type'] == 'Foreach':
            subtext = 'Foreach {variable} in {values}'
        elif P['type'] == 'For rows in table':
            subtext = 'For rows in table {table}'
        else:
            subtext = 'Loop type defined by {type}'

        text += self.header + '\n' + __(subtext, **P, indent=4 * ' ').__str__()
        text += '\n\n'

        # Print the body of the loop
        for edge in self.flowchart.edges(self, direction='out'):
            if edge.edge_subtype == 'loop':
                self.logger.debug(
                    'Loop, first node of loop is: {}'.format(edge.node2)
                )
                next_node = edge.node2
                while next_node and not next_node.visited:
                    next_node.visited = True
                    text += __(next_node.description_text(),
                               indent=4 * ' ').__str__()
                    text += '\n'
                    next_node = next_node.next()

        return text

    def describe(self):
        """Write out information about what this node will do
        """

        self.visited = True

        # The description
        job.job(__(self.description_text(), indent=self.indent))

        return self.exit_node()

    def run(self):
        """Run a Loop step.
        """

        # Set up the directory, etc.
        super().run()

        P = self.parameters.current_values_to_dict(
            context=seamm.flowchart_variables._data
        )

        # Remove any redirection of printing.
        if self._file_handler is not None:
            job.removeHandler(self._file_handler)
            self._file_handler = None
        job.handlers[0].setLevel(printing.NORMAL)

        if P['type'] == 'For':
            if self._loop_value is None:
                self.logger.info(
                    'For {} from {} to {} by {}'.format(
                        P['variable'], P['start'], P['end'], P['step']
                    )
                )

                self.logger.info('Initializing loop')
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
                self.write_final_structure()

                self._loop_value += P['step']
                self.set_variable(P['variable'], self._loop_value)

                # Set up the index variables
                tmp = self.get_variable('_loop_indices')
                self.set_variable(
                    '_loop_indices', (
                        *tmp[0:-1],
                        self._loop_value,
                    )
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

                    self.logger.info(
                        (
                            'The loop over {} from {} to {} by {}'
                            ' finished successfully'
                        ).format(
                            P['variable'], P['start'], P['end'], P['step']
                        )
                    )
                    return self.exit_node()

            self.logger.info('    Loop value = {}'.format(self._loop_value))
        elif P['type'] == 'Foreach':
            self.logger.info(f"Foreach {P['variable']} in {P['values']}")
            if self._loop_value is None:
                self._loop_value = -1
                self._loop_length = len(P['values'])
                if self.variable_exists('_loop_indices'):
                    tmp = self.get_variable('_loop_indices')
                    self.set_variable('_loop_indices', (
                        *tmp,
                        None,
                    ))
                else:
                    self.set_variable('_loop_indices', (None,))

            if self._loop_value >= 0:
                self.write_final_structure()

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
                self.logger.info('The loop over value finished successfully')

                # return the next node after the loop
                return self.exit_node()

            value = P['values'][self._loop_value]
            self.set_variable(P['variable'], value)

            # Set up the index variables
            tmp = self.get_variable('_loop_indices')
            self.set_variable(
                '_loop_indices', (
                    *tmp[0:-1],
                    self._loop_value,
                )
            )
            self.set_variable('_loop_index', self._loop_value)
            self.logger.info('    Loop value = {}'.format(value))
        elif P['type'] == 'For rows in table':
            if self._loop_value is None:
                self.table_handle = self.get_variable(P['table'])
                self.table = self.table_handle['table']
                self.table_handle['loop index'] = True

                self.logger.info(
                    'Initialize loop over {} rows in table {}'.format(
                        self.table.shape[0], P['table']
                    )
                )
                self._loop_value = -1
                if self.variable_exists('_loop_indices'):
                    tmp = self.get_variable('_loop_indices')
                    self.set_variable('_loop_indices', (
                        *tmp,
                        None,
                    ))
                else:
                    self.set_variable('_loop_indices', (None,))

            if self._loop_value >= 0:
                self.write_final_structure()

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

                self.logger.info(
                    'The loop over table ' + self.parameters['table'].value +
                    ' finished successfully'
                )

                # return the next node after the loop
                return self.exit_node()

            # Set up the index variables
            self.logger.debug('  _loop_value = {}'.format(self._loop_value))
            tmp = self.get_variable('_loop_indices')
            self.logger.debug('  _loop_indices = {}'.format(tmp))
            self.set_variable(
                '_loop_indices',
                (*tmp[0:-1], self.table.index[self._loop_value])
            )
            self.logger.debug(
                '   --> {}'.format(self.get_variable('_loop_indices'))
            )
            self.set_variable(
                '_loop_index', self.table.index[self._loop_value]
            )
            self.table_handle['current index'] = (
                self.table.index[self._loop_value]
            )

            row = self.table.iloc[self._loop_value]
            self.set_variable('_row', row)
            self.logger.debug('   _row = {}'.format(row))

        for edge in self.flowchart.edges(self, direction='out'):
            if edge.edge_subtype == 'loop':
                self.logger.info(
                    'Loop, first node of loop is: {}'.format(edge.node2)
                )

                # Direct most output to iteration.out
                # A handler for the file
                iter_dir = os.path.join(
                    self.directory, f'iter_{self._loop_value}'
                )
                os.makedirs(iter_dir, exist_ok=True)

                self._file_handler = logging.FileHandler(
                    os.path.join(iter_dir, 'iteration.out')
                )
                self._file_handler.setLevel(printing.NORMAL)
                formatter = logging.Formatter(fmt='{message:s}', style='{')
                self._file_handler.setFormatter(formatter)
                job.addHandler(self._file_handler)

                job.handlers[0].setLevel(printing.JOB)
                # Add the iteration to the ids so the directory structure is
                # reasonable
                self.flowchart.reset_visited()
                self.set_subids(
                    (*self._id, 'iter_{}'.format(self._loop_value))
                )
                return edge.node2
            else:
                # No loop body? just go on?
                return self.exit_node()

    def write_final_structure(self):
        """Write the final structure"""
        system_db = self.get_variable('_system_db')
        configuration = system_db.system.configuration
        if configuration.n_atoms > 0:
            # MMCIF file has bonds
            filename = os.path.join(
                self.directory, f'iter_{self._loop_value}',
                'final_structure.mmcif'
            )
            text = None
            try:
                text = configuration.to_mmcif_text()
            except Exception:
                message = (
                    'Error creating the mmcif file at the end of the loop\n\n'
                    + traceback.format_exc()
                )
                self.logger.critical(message)

            if text is not None:
                with open(filename, 'w') as fd:
                    print(text, file=fd)

            # CIF file has cell
            if configuration.periodicity == 3:
                filename = os.path.join(
                    self.directory, f'iter_{self._loop_value}',
                    'final_structure.cif'
                )
                text = None
                try:
                    text = configuration.to_cif_text()
                except Exception:
                    message = (
                        'Error creating the cif file at the end of the loop'
                        '\n\n' + traceback.format_exc()
                    )
                    self.logger.critical(message)

                if text is not None:
                    with open(filename, 'w') as fd:
                        print(text, file=fd)

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

        self.logger.debug(f'loop.default_edge_subtype, n_edges = {n_edges}')

        if n_edges == 0:
            return "loop"
        elif n_edges == 1:
            return "exit"
        else:
            return "too many"

    def create_parser(self):
        """Setup the command-line / config file parser
        """
        parser_name = 'loop-step'
        parser = seamm.getParser()

        # Remember if the parser exists ... this type of step may have been
        # found before
        parser_exists = parser.exists(parser_name)

        # Create the standard options, e.g. log-level
        super().create_parser(name=parser_name)

        if not parser_exists:
            # Any options for loop itself
            pass

        # Now need to walk through the steps in the loop...
        for edge in self.flowchart.edges(self, direction='out'):
            if edge.edge_subtype == 'loop':
                self.logger.debug(
                    'Loop, first node of loop is: {}'.format(edge.node2)
                )
                next_node = edge.node2
                while next_node and next_node != self:
                    next_node = next_node.create_parser()

        return self.exit_node()

    def set_id(self, node_id=()):
        """Sequentially number the loop subnodes"""
        self.logger.debug('Setting ids for loop {}'.format(self))
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
                self.logger.debug(
                    'Loop, first node of loop is: {}'.format(edge.node2)
                )
                next_node = edge.node2
                n = 0
                while next_node and next_node != self:
                    next_node = next_node.set_id((*node_id, str(n)))
                    n += 1

    def exit_node(self):
        """The next node after the loop, if any"""

        for edge in self.flowchart.edges(self, direction='out'):
            if edge.edge_subtype == 'exit':
                self.logger.debug(f'Loop, node after loop is: {edge.node2}')
                return edge.node2

        # loop is the last node in the flowchart
        self.logger.debug('There is no node after the loop')
        return None
