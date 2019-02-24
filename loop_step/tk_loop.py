# -*- coding: utf-8 -*-
"""The graphical part of a Loop step"""

import logging
import molssi_workflow
import molssi_util.molssi_widgets as mw
import loop_step
import Pmw
import pprint  # nopep8
import tkinter as tk
import tkinter.ttk as ttk

logger = logging.getLogger(__name__)


class TkLoop(molssi_workflow.TkNode):
    """The node_class is the class of the 'real' node that this
    class is the Tk graphics partner for
    """

    node_class = loop_step.Loop

    def __init__(self, tk_workflow=None, node=None, canvas=None,
                 x=120, y=20, w=200, h=50):
        '''Initialize a node

        Keyword arguments:
        '''
        self.dialog = None

        super().__init__(tk_workflow=tk_workflow, node=node,
                         canvas=canvas, x=x, y=y, w=w, h=h)

    def create_dialog(self):
        """Create the dialog!"""
        self.dialog = Pmw.Dialog(
            self.toplevel,
            buttons=('OK', 'Help', 'Cancel'),
            defaultbutton='OK',
            master=self.toplevel,
            title='Edit Loop step',
            command=self.handle_dialog)
        self.dialog.withdraw()

        # self._widget, which is inherited from the base class, is
        # a place to store the pointers to the widgets so that we can access
        # them later. We'll set up a short hand 'w' just to keep lines short
        w = self._widget
        frame = ttk.Frame(self.dialog.interior())
        frame.pack(expand=tk.YES, fill=tk.BOTH)
        w['frame'] = frame

        # The type of loop
        loop_type = ttk.Combobox(
            frame, state='readonly',
            values=['For',
                    'Foreach',
                    'For rows in table',
                    'While'
            ],
            justify=tk.LEFT, width=15
        )
        loop_type.set(self.node.loop_type)
        w['loop_type'] = loop_type

        # Loop variable
        w['variable_label'] = ttk.Label(frame, text='Variable:')
        w['variable'] = ttk.Entry(frame, width=15)
        w['variable'].insert(0, self.node.variable)

        # First value
        w['first_value_label'] = ttk.Label(frame, text='from')
        w['first_value'] = ttk.Entry(frame, width=15)
        w['first_value'].insert(0, str(self.node.first_value))

        # Last value
        w['last_value_label'] = ttk.Label(frame, text='to')
        w['last_value'] = ttk.Entry(frame, width=15)
        w['last_value'].insert(0, str(self.node.last_value))

        # Increment, putting units here
        w['increment'] = mw.UnitEntry(frame, width=15, labeltext='by')
        w['increment'].set(str(self.node.increment))

        # Table name
        w['tablename'] = ttk.Entry(frame, width=15)
        w['tablename'].insert(0, self.node.tablename)

        w['loop_type'].bind("<<ComboboxSelected>>", self.reset_dialog)

        self.reset_dialog()

    def reset_dialog(self, widget=None):
        # set up our shorthand for the widgets
        w = self._widget

        # and get the method, which in this example controls
        # how the widgets are laid out.
        loop_type = w['loop_type'].get()
        logger.debug('Updating edit loop dialog: {}'.format(loop_type))

        # Remove any widgets previously packed
        frame = w['frame']
        for slave in frame.grid_slaves():
            slave.grid_forget()

        # keep track of the row in a variable, so that the layout is flexible
        # if e.g. rows are skipped to control such as 'method' here
        row = 0
        w['loop_type'].grid(row=row, column=0, sticky=tk.W)
        row += 1
        if loop_type == 'For':
            w['variable_label'].grid(row=row, column=2, sticky=tk.W)
            w['variable'].grid(row=row, column=3, sticky=tk.W)
            w['first_value_label'].grid(row=row, column=4, sticky=tk.W)
            w['first_value'].grid(row=row, column=5, sticky=tk.W)
            w['last_value_label'].grid(row=row, column=6, sticky=tk.W)
            w['last_value'].grid(row=row, column=7, sticky=tk.W)
            w['increment'].grid(row=row, column=8, sticky=tk.W)
        elif loop_type == 'Foreach':
            pass
        elif loop_type == 'For rows in table':
            w['tablename'].grid(row=row, column=2, sticky=tk.W)
        else:
            raise RuntimeError(
                "Don't recognize the loop_type {}".format(loop_type))
        row += 1

    def right_click(self, event):
        """Probably need to add our dialog...
        """

        super().right_click(event)
        self.popup_menu.add_command(label="Edit..", command=self.edit)

        self.popup_menu.tk_popup(event.x_root, event.y_root, 0)

    def edit(self):
        """Present a dialog for editing the Loop input
        """
        if self.dialog is None:
            self.create_dialog()

        self.dialog.activate(geometry='centerscreenfirst')

    def handle_dialog(self, result):
        if result is None or result == 'Cancel':
            self.dialog.deactivate(result)
            return

        if result == 'Help':
            # display help!!!
            return

        if result != "OK":
            self.dialog.deactivate(result)
            raise RuntimeError(
                "Don't recognize dialog result '{}'".format(result))

        self.dialog.deactivate(result)

        # set up our shorthand for the widgets
        w = self._widget
        # and get the method, which in this example tells
        # whether to use the value ditrectly or get it from
        # a variable in the workflow

        loop_type = w['loop_type'].get()
        logger.debug('Updating loop stage from dialog: {}'.format(loop_type))

        self.node.loop_type = loop_type
        if loop_type == 'For':
            self.node.variable = w['variable'].get()
            self.node.first_value = int(w['first_value'].get())
            self.node.last_value = int(w['last_value'].get())
            self.node.increment = int(w['increment'].get())
        elif loop_type == 'Foreach':
            pass
        elif loop_type == 'For rows in table':
            self.node.tablename = w['tablename'].get()
            logger.debug('  tablename <== {}'.format(self.node.tablename))
        else:
            raise RuntimeError(
                "Don't recognize the type of loop {}".format(loop_type))

    def handle_help(self):
        """Not implemented yet ... you'll need to fill this out!"""
        print('Help!')

    def default_edge_label(self):
        """Return the default label of the edge. Usually this is 'exit'
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
        n_edges = len(self.tk_workflow.edges(self, direction='out'))

        logger.debug('loop.default_edge_label, n_edges = {}'.format(n_edges))

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
        n_edges = len(self.tk_workflow.edges(self, direction='out'))

        if n_edges == 0:
            return "e"
        elif n_edges == 1:
            return "s"
        else:
            return "sw"
