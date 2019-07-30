# -*- coding: utf-8 -*-
"""The graphical part of a Loop step"""

import logging
import seamm
import loop_step
import Pmw
import tkinter as tk
import tkinter.ttk as ttk

logger = logging.getLogger(__name__)


class TkLoop(seamm.TkNode):
    """The node_class is the class of the 'real' node that this
    class is the Tk graphics partner for
    """

    node_class = loop_step.Loop

    def __init__(self, tk_flowchart=None, node=None, canvas=None,
                 x=120, y=20, w=200, h=50):
        '''Initialize a node

        Keyword arguments:
        '''
        self.dialog = None

        super().__init__(tk_flowchart=tk_flowchart, node=node,
                         canvas=canvas, x=x, y=y, w=w, h=h)

        self.node_type = 'loop'

    def create_dialog(self):
        """Create the dialog!"""
        self.dialog = Pmw.Dialog(
            self.toplevel,
            buttons=('OK', 'Help', 'Cancel'),
            master=self.toplevel,
            title='Edit Loop step',
            command=self.handle_dialog)
        self.dialog.withdraw()

        # Create a frame to hold everything
        frame = ttk.Frame(self.dialog.interior())
        frame.pack(expand=tk.YES, fill=tk.BOTH)
        self['frame'] = frame

        # Create the widgets and grid them in
        P = self.node.parameters
        for key in P:
            self[key] = P[key].widget(frame)

        self['type'].combobox.bind("<<ComboboxSelected>>", self.reset_dialog)

        self.reset_dialog()

    def reset_dialog(self, widget=None):

        # and get the method, which in this example controls
        # how the widgets are laid out.
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
            self['variable'].grid(row=row, column=3, sticky=tk.W)
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

        # Shortcut for parameters
        P = self.node.parameters

        for key in P:
            P[key].set_from_widget()

    def handle_help(self):
        """Not implemented yet ... you'll need to fill this out!"""
        print('Help!')

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
