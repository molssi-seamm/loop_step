# -*- coding: utf-8 -*-

"""The graphical part of a Loop step"""

import logging
import seamm
import loop_step
import tkinter as tk

import seamm_widgets as sw

logger = logging.getLogger(__name__)

search_fields = {
    "system index": {
        "operators": (
            "=",
            "!=",
            "between",
            "not between",
            ">",
            "<",
        ),
    },
    "system name": {
        "operators": (
            "is",
            "is not",
            "contains",
            "does not contain",
            "matches",
            "does not match",
            "matches regexp",
            "does not match regexp",
        ),
    },
    "configuration name": {
        "operators": (
            "is",
            "is not",
            "contains",
            "does not contain",
            "matches",
            "does not match",
            "matches regexp",
            "does not match regexp",
        ),
    },
}


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
        my_logger=logger,
    ):
        """Initialize the graphical Tk Loop node

        Keyword arguments:
        """

        # Set the logging level for this module if requested
        # if 'tk_loop_log_level' in self.options:
        #     logger.setLevel(self.options.tk_loop_log_level)
        #     logger.critical(
        #         'Set log level to {}'.format(self.options.tk_loop_log_level)
        #     )

        # Call the constructor for the energy
        super().__init__(
            tk_flowchart=tk_flowchart,
            node=node,
            node_type="loop",
            canvas=canvas,
            x=x,
            y=y,
            w=w,
            h=h,
            my_logger=my_logger,
        )

    def create_dialog(self):
        """Create the dialog!"""
        frame = super().create_dialog(title="Edit Loop Step")

        # Create the widgets and grid them in
        P = self.node.parameters
        for key in P:
            if key != "search criteria":
                self[key] = P[key].widget(frame)

        # Create the search widgets for the systems
        self["criteria"] = sw.SearchCriteria(
            frame,
            text="Select systems where",
            labelanchor=tk.NW,
            inclusiontext="",
            inclusionvalues=(
                "",
                "and",
                "or",
                "(",
                ")",
                "ignore",
            ),
            operatorvalues=(
                "is",
                "is not",
                "contains",
                "does not contain",
                "matches",
                "does not match",
                "matches regexp",
                "does not match regexp",
            ),
            fieldvalues=[*search_fields.keys()],
            two_values=("between", "not between"),
            command=self.criteria_callback,
        )

        for widget in (
            "type",
            "where",
            "query-op",
            "where system name",
            "default configuration",
        ):
            self[widget].bind("<<ComboboxSelected>>", self.reset_dialog)
            self[widget].combobox.config(state="readonly")

        self["errors"].combobox.config(state="readonly")

    def criteria_callback(self, widget, criterion, event, what):
        """Handle changes in the search criteria widget.

        Parameters
        ----------
        widget : Tk widget
            The widget.
        criterion : sw.Criterion
            The row -- Criterion widget -- in the table.
        event : tk.Event
            The event causing the callback.
        what : str
            The item that changed: 'inclusion', 'field', 'operator', 'self.two_values',
            'clear', 'set', 'add row', 'remove row'
        """
        if criterion is not None:
            inclusion, field, operator, value, value2 = criterion.get()

            if what == "field":
                operators = search_fields[field]["operators"]
                w = criterion.operator
                w.configure(values=operators)
                if operator in operators:
                    w.set(operator)
                else:
                    w.set(operators[0])

    def reset_dialog(self, widget=None):
        """Lay out the edit dialog according to the type of loop."""

        # Get the type of loop currently requested
        loop_type = self["type"].get()

        logger.debug("Updating edit loop dialog: {}".format(loop_type))

        # Remove any widgets previously packed
        frame = self["frame"]
        for slave in frame.grid_slaves():
            slave.grid_forget()

        # keep track of the row in a variable, so that the layout is flexible
        # if e.g. rows are skipped to control such as 'method' here
        row = 0
        self["type"].grid(row=row, column=0, columnspan=2, sticky=tk.W)
        if loop_type == "For":
            self["variable"].grid(row=row, column=2, sticky=tk.W)
            self["start"].grid(row=row, column=3, sticky=tk.W)
            self["end"].grid(row=row, column=4, sticky=tk.W)
            self["step"].grid(row=row, column=5, sticky=tk.W)
        elif loop_type == "Foreach":
            frame.columnconfigure(5, weight=0)
            self["variable"].grid(row=row, column=2, sticky=tk.W)
            self["values"].grid(row=row, column=3, sticky=tk.EW)
            frame.columnconfigure(3, weight=1)
        elif loop_type == "For rows in table":
            frame.columnconfigure(3, weight=0)
            self["table"].grid(row=row, column=2, columnspan=2, sticky=tk.EW)
            row += 1
            self["where"].grid(row=row, column=1, columnspan=2, sticky=tk.EW)
            where = self["where"].get()
            if where != "Use all rows":
                self["query-column"].grid(row=row, column=3, sticky=tk.EW)
                self["query-op"].grid(row=row, column=4)
                op = self["query-op"].get()
                if "empty" not in op:
                    self["query-value"].grid(row=row, column=5, sticky=tk.EW)
                    frame.columnconfigure(5, weight=1)
        elif loop_type == "For systems in the database":
            row += 1
            self["criteria"].grid(row=row, column=1, columnspan=3, sticky=tk.NSEW)
            frame.rowconfigure(row, weight=1, minsize=100)
            row += 1

            self["default configuration"].grid(
                row=row, column=0, columnspan=2, sticky=tk.EW
            )
            op = self["default configuration"].get()
            if "name" in op:
                self["configuration name"].grid(
                    row=row, column=2, columnspan=2, sticky=tk.EW
                )
            frame.columnconfigure(3, weight=1)
            row += 1
            self["directory name"].grid(row=row, column=0, columnspan=3, sticky=tk.W)
        else:
            raise RuntimeError("Don't recognize the loop_type {}".format(loop_type))
        row += 1
        self["errors"].grid(row=row, column=0, columnspan=4, sticky=tk.W)
        row += 1
        frame.columnconfigure(0, minsize=40)

    def right_click(self, event):
        """Probably need to add our dialog..."""

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
        n_edges = len(self.tk_flowchart.edges(self, direction="out"))

        logger.debug("loop.default_edge_subtype, n_edges = {}".format(n_edges))

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
        n_edges = len(self.tk_flowchart.edges(self, direction="out"))

        if n_edges == 0:
            return "e"
        elif n_edges == 1:
            return "s"
        else:
            return "sw"
