# -*- coding: utf-8 -*-

"""The graphical part of a Loop step"""

import configargparse
import logging
import seamm
import loop_step
import tkinter as tk

logger = logging.getLogger(__name__)


class TkLoop(seamm.TkNode):
    """The node_class is the class of the 'real' node that this
    class is the Tk graphics partner for
    """

    node_class = loop_step.Loop

    def __init__(
        self,
        tk_flowchart=None,
        node=None,
        canvas=None,
        x=120,
        y=20,
        w=200,
        h=50,
        my_logger=logger
    ):
        """Initialize the graphical Tk Loop node

        Keyword arguments:
        """

        # Argument/config parsing
        self.parser = configargparse.ArgParser(
            auto_env_var_prefix='',
            default_config_files=[
                '/etc/seamm/tk_loop.ini',
                '/etc/seamm/seamm.ini',
                '~/.seamm/tk_loop.ini',
                '~/.seamm/seamm.ini',
            ]
        )

        self.parser.add_argument(
            '--seamm-configfile',
            is_config_file=True,
            default=None,
            help='a configuration file to override others'
        )

        # Options for this plugin
        self.parser.add_argument(
            "--tk-loop-log-level",
            default=configargparse.SUPPRESS,
            choices=[
                'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'
            ],
            type=lambda string: string.upper(),
            help="the logging level for the Tk_Loop step"
        )

        self.options, self.unknown = self.parser.parse_known_args()

        # Set the logging level for this module if requested
        if 'tk_loop_log_level' in self.options:
            logger.setLevel(self.options.tk_loop_log_level)
            logger.critical(
                'Set log level to {}'.format(self.options.tk_loop_log_level)
            )

        # Call the constructor for the energy
        super().__init__(
            tk_flowchart=tk_flowchart,
            node=node,
            node_type='loop',
            canvas=canvas,
            x=x,
            y=y,
            w=w,
            h=h,
            my_logger=my_logger
        )

    def create_dialog(self):
        """Create the dialog!"""
        frame = super().create_dialog(title='Edit Loop Step')

        # Create the widgets and grid them in
        P = self.node.parameters
        for key in P:
            self[key] = P[key].widget(frame)

        self['type'].combobox.bind("<<ComboboxSelected>>", self.reset_dialog)

    def reset_dialog(self, widget=None):
        """Lay out the edit dialog according to the type of loop."""

        # Get the type of loop currently requested
        loop_type = self['type'].get()

        logger.debug('Updating edit loop dialog: {}'.format(loop_type))

        # Remove any widgets previously packed
        frame = self['frame']
        for slave in frame.grid_slaves():
            slave.grid_forget()

        # keep track of the row in a variable, so that the layout is flexible
        # if e.g. rows are skipped to control such as 'method' here
        row = 0
        self['type'].grid(row=row, column=0, sticky=tk.W)
        if loop_type == 'For':
            self['variable'].grid(row=row, column=2, sticky=tk.W)
            self['start'].grid(row=row, column=3, sticky=tk.W)
            self['end'].grid(row=row, column=4, sticky=tk.W)
            self['step'].grid(row=row, column=5, sticky=tk.W)
        elif loop_type == 'Foreach':
            self['variable'].grid(row=row, column=2, sticky=tk.W)
            self['values'].grid(row=row, column=3, sticky=tk.W)
        elif loop_type == 'For rows in table':
            self['table'].grid(row=row, column=2, sticky=tk.W)
        else:
            raise RuntimeError(
                "Don't recognize the loop_type {}".format(loop_type)
            )
        row += 1

    def right_click(self, event):
        """Probably need to add our dialog...
        """

        super().right_click(event)
        self.popup_menu.add_command(label="Edit..", command=self.edit)

        self.popup_menu.tk_popup(event.x_root, event.y_root, 0)

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
        n_edges = len(self.tk_flowchart.edges(self, direction='out'))

        logger.debug('loop.default_edge_subtype, n_edges = {}'.format(n_edges))

        if n_edges == 0:
            return "loop"
        elif n_edges == 1:
            return "exit"
        else:
            return "too many"

    def next_anchor(self):
        """Return where the next node should be positioned. The default is
        <gap> below the 's' anchor point.
        """

        # how many outgoing edges are there?
        n_edges = len(self.tk_flowchart.edges(self, direction='out'))

        if n_edges == 0:
            return "e"
        elif n_edges == 1:
            return "s"
        else:
            return "sw"
