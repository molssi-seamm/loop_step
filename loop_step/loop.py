# -*- coding: utf-8 -*-

"""Non-graphical part of the Loop step in a SEAMM flowchart"""

import logging
from pathlib import Path
import re
import sys
import traceback

import psutil
import pprint

import loop_step
import seamm
import seamm_util
import seamm_util.printing as printing
from seamm_util.printing import FormattedText as __

logger = logging.getLogger(__name__)
job = printing.getPrinter()
printer = printing.getPrinter("loop")


class Loop(seamm.Node):
    def __init__(self, flowchart=None, extension=None):
        """Setup the non-graphical part of the Loop step in a
        SEAMM flowchart.

        Keyword arguments:
        """
        logger.debug("Creating Loop {}".format(self))

        self.table_handle = None
        self.table = None
        self._loop_value = None
        self._loop_length = None
        self._file_handler = None

        super().__init__(
            flowchart=flowchart, title="Loop", extension=extension, logger=logger
        )

        # This needs to be after initializing subclasses...
        self.parameters = loop_step.LoopParameters()

    @property
    def version(self):
        """The semantic version of this module."""
        return loop_step.__version__

    @property
    def iter_format(self):
        if self._loop_length is None:
            return "07"
        else:
            n = len(str(self._loop_length))
            return f"0{n}"

    @property
    def git_revision(self):
        """The git version of this module."""
        return loop_step.__git_revision__

    @property
    def working_path(self):
        return Path(self.directory) / f"iter_{self._loop_value:{self.iter_format}}"

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

        text = ""

        if P["type"] == "For":
            subtext = "For {variable} from {start} to {end} by {step}\n"
        elif P["type"] == "Foreach":
            subtext = "Foreach {variable} in {values}\n"
        elif P["type"] == "For rows in table":
            subtext = "For rows in table {table}\n"
        else:
            subtext = "Loop type defined by {type}\n"

        text += self.header + "\n" + __(subtext, **P, indent=4 * " ").__str__()

        # Print the body of the loop
        for edge in self.flowchart.edges(self, direction="out"):
            if edge.edge_subtype == "loop":
                self.logger.debug("Loop, first node of loop is: {}".format(edge.node2))
                next_node = edge.node2
                while next_node and not next_node.visited:
                    next_node.visited = True
                    text += "\n\n"
                    text += __(next_node.description_text(), indent=4 * " ").__str__()
                    next_node = next_node.next()

        return text

    def describe(self):
        """Write out information about what this node will do"""

        self.visited = True

        # The description
        job.job(__(self.description_text(), indent=self.indent))

        return self.exit_node()

    def run(self):
        """Run a Loop step."""
        # If the loop is empty, just go on
        if self.loop_node() is None:
            return self.exit_node()

        # Set up the directory, etc.
        super().run()

        P = self.parameters.current_values_to_dict(
            context=seamm.flowchart_variables._data
        )

        # Print out header to the main output
        printer.important(self.description_text(P))

        # Remove any redirection of printing.
        if self._file_handler is not None:
            job.removeHandler(self._file_handler)
            self._file_handler = None

        # Find the handler for job.out and set the level up
        job_handler = None
        out_handler = None
        for handler in job.handlers:
            if (
                isinstance(handler, logging.FileHandler)
                and "job.out" in handler.baseFilename
            ):
                job_handler = handler
                job_level = job_handler.level
                job_handler.setLevel(printing.JOB)
            elif isinstance(handler, logging.StreamHandler):
                out_handler = handler
                out_level = out_handler.level
                out_handler.setLevel(printing.JOB)

        # Set up some unchanging variables
        if P["type"] == "For rows in table":
            if self._loop_value is None:
                self.table_handle = self.get_variable(P["table"])
                self.table = self.table_handle["table"]
                self.table_handle["loop index"] = True

                self.logger.info(
                    "Initialize loop over {} rows in table {}".format(
                        self.table.shape[0], P["table"]
                    )
                )
                self._loop_value = -1
                self._loop_length = self.table.shape[0]
                printer.job(f"    The loop will have {self._loop_length} iterations.")
                if self.variable_exists("_loop_indices"):
                    tmp = self.get_variable("_loop_indices")
                    self.set_variable(
                        "_loop_indices",
                        (
                            *tmp,
                            None,
                        ),
                    )
                else:
                    self.set_variable("_loop_indices", (None,))
            where = P["where"]
            if where == "Use all rows":
                pass
            elif where == "Select rows where column":
                column = P["query-column"]
                op = P["query-op"]
                value = P["query-value"]
                if self.table.shape[0] > 0:
                    row = self.table.iloc[0]
                    tmp = pprint.pformat(row)
                    self.logger.debug(f"Row is\n{tmp}")
                    if column not in row:
                        for key in row.keys():
                            if column.lower() == key.lower():
                                column = key
                                break
                    if column not in row:
                        raise ValueError(
                            f"Looping over table with criterion on column '{column}': "
                            "that column does not exist."
                        )
            else:
                raise NotImplementedError(f"Loop cannot handle '{where}'")

        # Cycle through the iterations, setting up the first time.
        next_node = self
        while next_node is not None:
            if next_node is self:
                next_node = self.loop_node()

                if P["type"] == "For":
                    if self._loop_value is None:
                        self.logger.info(
                            "For {} from {} to {} by {}".format(
                                P["variable"], P["start"], P["end"], P["step"]
                            )
                        )

                        # See if loop variables are all integers
                        start = P["start"]
                        if isinstance(start, str):
                            start = float(start)
                        if isinstance(start, float) and start.is_integer():
                            start = int(start)
                        step = P["step"]
                        if isinstance(step, str):
                            step = float(step)
                        if isinstance(step, float) and step.is_integer():
                            step = int(step)
                        end = P["end"]
                        if isinstance(end, str):
                            end = float(end)
                        if isinstance(end, float) and end.is_integer():
                            end = int(end)

                        self.logger.info("Initializing loop")
                        self._loop_value = start
                        self.set_variable(P["variable"], self._loop_value)

                        # Loop to get length... range doesn't work for nonintegers
                        count = 0
                        tmp = start
                        while tmp <= end:
                            count += 1
                            tmp += step
                        self._loop_length = count
                        printer.job(
                            f"    The loop will have {self._loop_length} iterations."
                        )
                        if self.variable_exists("_loop_indices"):
                            tmp = self.get_variable("_loop_indices")
                            self.set_variable("_loop_indices", (*tmp, self._loop_value))
                        else:
                            self.set_variable("_loop_indices", (self._loop_value,))
                            self.set_variable("_loop_index", self._loop_value)
                    else:
                        self.write_final_structure()

                        self._loop_value += step
                        self.set_variable(P["variable"], self._loop_value)

                        # Set up the index variables
                        tmp = self.get_variable("_loop_indices")
                        self.set_variable(
                            "_loop_indices",
                            (
                                *tmp[0:-1],
                                self._loop_value,
                            ),
                        )
                        self.set_variable("_loop_index", self._loop_value)

                        # See if we are at the end of loop
                        if self._loop_value > end:
                            self._loop_value = None

                            # Revert the loop index variables to the next outer loop
                            # if there is one, or remove them.
                            tmp = self.get_variable("_loop_indices")

                            if len(tmp) <= 1:
                                self.delete_variable("_loop_indices")
                                self.delete_variable("_loop_index")
                            else:
                                self.set_variable("_loop_indices", tmp[0:-1])
                                self.set_variable("_loop_index", tmp[-2])

                            self.logger.info(
                                f"The loop over {P['variable']} from {start} to "
                                f"{end} by {step} finished successfully"
                            )
                            break

                    self.logger.info("    Loop value = {}".format(self._loop_value))
                elif P["type"] == "Foreach":
                    self.logger.info(f"Foreach {P['variable']} in {P['values']}")
                    if self._loop_value is None:
                        self._loop_value = -1
                        self._loop_length = len(P["values"])
                        printer.job(
                            f"    The loop will have {self._loop_length} iterations."
                        )
                        if self.variable_exists("_loop_indices"):
                            tmp = self.get_variable("_loop_indices")
                            self.set_variable(
                                "_loop_indices",
                                (
                                    *tmp,
                                    None,
                                ),
                            )
                        else:
                            self.set_variable("_loop_indices", (None,))

                    if self._loop_value >= 0:
                        self.write_final_structure()

                    self._loop_value += 1

                    if self._loop_value >= self._loop_length:
                        self._loop_value = None
                        self._loop_length = None

                        # Revert the loop index variables to the next outer loop
                        # if there is one, or remove them.
                        tmp = self.get_variable("_loop_indices")
                        if len(tmp) <= 1:
                            self.delete_variable("_loop_indices")
                            self.delete_variable("_loop_index")
                        else:
                            self.set_variable("_loop_indices", tmp[0:-1])
                            self.set_variable("_loop_index", tmp[-2])
                        self.logger.info("The loop over value finished successfully")

                        # return the next node after the loop
                        break

                    value = P["values"][self._loop_value]
                    self.set_variable(P["variable"], value)

                    # Set up the index variables
                    tmp = self.get_variable("_loop_indices")
                    self.set_variable(
                        "_loop_indices",
                        (
                            *tmp[0:-1],
                            self._loop_value,
                        ),
                    )
                    self.set_variable("_loop_index", self._loop_value)
                    self.logger.info("    Loop value = {}".format(value))
                elif P["type"] == "For rows in table":
                    if self._loop_value >= 0:
                        self.write_final_structure()

                    # Loop until query is satisfied
                    while True:
                        self._loop_value += 1

                        if self._loop_value >= self.table.shape[0]:
                            break

                        if where == "Use all rows":
                            break

                        row = self.table.iloc[self._loop_value]

                        self.logger.debug(f"Query {row[column]} {op} {value}")
                        if op == "==":
                            if row[column] == value:
                                break
                        elif op == "!=":
                            if row[column] != value:
                                break
                        elif op == ">":
                            if row[column] > value:
                                break
                        elif op == ">=":
                            if row[column] >= value:
                                break
                        elif op == "<":
                            if row[column] < value:
                                break
                        elif op == "<=":
                            if row[column] <= value:
                                break
                        elif op == "contains":
                            if value in row[column]:
                                break
                        elif op == "does not contain":
                            if value not in row[column]:
                                break
                        elif op == "contains regexp":
                            if re.search(value, row[column]) is not None:
                                break
                        elif op == "does not contain regexp":
                            if re.search(value, row[column]) is None:
                                break
                        elif op == "is empty":
                            # Might be numpy.nan, and NaN != NaN hence odd test.
                            if row[column] == "" or row[column] != row[column]:
                                break
                        elif op == "is not empty":
                            if row[column] != "" and row[column] == row[column]:
                                break
                        else:
                            raise NotImplementedError(
                                f"Loop query '{op}' not implemented"
                            )

                    if self._loop_value >= self.table.shape[0]:
                        self._loop_value = None

                        self.delete_variable("_row")
                        # Revert the loop index variables to the next outer loop
                        # if there is one, or remove them.
                        tmp = self.get_variable("_loop_indices")
                        if len(tmp) <= 1:
                            self.delete_variable("_loop_indices")
                            self.delete_variable("_loop_index")
                        else:
                            self.set_variable("_loop_indices", tmp[0:-1])
                            self.set_variable("_loop_index", tmp[-2])

                        # and the other info in the table handle
                        self.table_handle["loop index"] = False

                        self.table = None
                        self.table_handle = None

                        self.logger.info(
                            "The loop over table "
                            + self.parameters["table"].value
                            + " finished successfully"
                        )

                        # return the next node after the loop
                        break

                    # Set up the index variables
                    self.logger.debug("  _loop_value = {}".format(self._loop_value))
                    tmp = self.get_variable("_loop_indices")
                    self.logger.debug("  _loop_indices = {}".format(tmp))
                    self.set_variable(
                        "_loop_indices",
                        (*tmp[0:-1], self.table.index[self._loop_value]),
                    )
                    self.logger.debug(
                        "   --> {}".format(self.get_variable("_loop_indices"))
                    )
                    self.set_variable("_loop_index", self.table.index[self._loop_value])
                    self.table_handle["current index"] = self.table.index[
                        self._loop_value
                    ]

                    row = self.table.iloc[self._loop_value]
                    self.set_variable("_row", row)
                    self.logger.debug("   _row = {}".format(row))

                # Direct most output to iteration.out
                # A handler for the file
                iter_dir = self.working_path
                iter_dir.mkdir(parents=True, exist_ok=True)

                if self._file_handler is not None:
                    self._file_handler.close()
                    job.removeHandler(self._file_handler)
                self._file_handler = logging.FileHandler(iter_dir / "iteration.out")
                self._file_handler.setLevel(printing.NORMAL)
                formatter = logging.Formatter(fmt="{message:s}", style="{")
                self._file_handler.setFormatter(formatter)
                job.addHandler(self._file_handler)

                # Add the iteration to the ids so the directory structure is
                # reasonable
                self.flowchart.reset_visited()
                self.set_subids(
                    (*self._id, f"iter_{self._loop_value:{self.iter_format}}")
                )

            # Run through the steps in the loop body
            try:
                next_node = next_node.run()
            except DeprecationWarning as e:
                printer.normal("\nDeprecation warning: " + str(e))
                traceback.print_exc(file=sys.stderr)
                traceback.print_exc(file=sys.stdout)
            except Exception as e:
                printer.job(
                    f"Caught exception in loop iteration {self._loop_value}: {str(e)}"
                )
                with open(iter_dir / "stderr.out", "a") as fd:
                    traceback.print_exc(file=fd)
                if "continue" in P["errors"]:
                    next_node = self
                elif "exit" in P["errors"]:
                    break
                else:
                    raise

            if self.logger.isEnabledFor(logging.DEBUG):
                p = psutil.Process()
                self.logger.debug(pprint.pformat(p.open_files()))

            self.logger.debug(f"Bottom of loop {next_node}")

        # Return to the normally scheduled step, i.e. fall out of the loop.

        # Remove any redirection of printing.
        if self._file_handler is not None:
            self._file_handler.close()
            job.removeHandler(self._file_handler)
            self._file_handler = None
        if job_handler is not None:
            job_handler.setLevel(job_level)
        if out_handler is not None:
            out_handler.setLevel(out_level)

        return self.exit_node()

    def write_final_structure(self):
        """Write the final structure"""
        system_db = self.get_variable("_system_db")
        system = system_db.system
        if system is None:
            return
        configuration = system.configuration
        if configuration is None:
            return
        if configuration.n_atoms > 0:
            # MMCIF file has bonds
            filename = self.working_path / "final_structure.mmcif"
            text = None
            try:
                text = configuration.to_mmcif_text()
            except Exception:
                message = (
                    "Error creating the mmcif file at the end of the loop\n\n"
                    + traceback.format_exc()
                )
                self.logger.critical(message)

            if text is not None:
                with open(filename, "w") as fd:
                    print(text, file=fd)

            # CIF file has cell
            if configuration.periodicity == 3:
                filename = self.working_path / "final_structure.cif"
                text = None
                try:
                    text = configuration.to_cif_text()
                except Exception:
                    message = (
                        "Error creating the cif file at the end of the loop"
                        "\n\n" + traceback.format_exc()
                    )
                    self.logger.critical(message)

                if text is not None:
                    with open(filename, "w") as fd:
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
        n_edges = len(self.flowchart.edges(self, direction="out"))

        self.logger.debug(f"loop.default_edge_subtype, n_edges = {n_edges}")

        if n_edges == 0:
            return "loop"
        elif n_edges == 1:
            return "exit"
        else:
            return "too many"

    def create_parser(self):
        """Setup the command-line / config file parser"""
        parser_name = "loop-step"
        parser = seamm_util.getParser()

        # Remember if the parser exists ... this type of step may have been
        # found before
        parser_exists = parser.exists(parser_name)

        # Create the standard options, e.g. log-level
        super().create_parser(name=parser_name)

        if not parser_exists:
            # Any options for loop itself
            pass

        # Now need to walk through the steps in the loop...
        for edge in self.flowchart.edges(self, direction="out"):
            if edge.edge_subtype == "loop":
                self.logger.debug("Loop, first node of loop is: {}".format(edge.node2))
                next_node = edge.node2
                while next_node and next_node != self:
                    next_node = next_node.create_parser()

        return self.exit_node()

    def set_id(self, node_id=()):
        """Sequentially number the loop subnodes"""
        self.logger.debug("Setting ids for loop {}".format(self))
        if self.visited:
            return None
        else:
            self.visited = True
            self._id = node_id
            self.set_subids(self._id)
            return self.exit_node()

    def set_subids(self, node_id=()):
        """Set the ids of the nodes in the loop"""
        for edge in self.flowchart.edges(self, direction="out"):
            if edge.edge_subtype == "loop":
                self.logger.debug("Loop, first node of loop is: {}".format(edge.node2))
                next_node = edge.node2
                n = 0
                while next_node and next_node != self:
                    next_node = next_node.set_id((*node_id, str(n)))
                    n += 1

    def exit_node(self):
        """The next node after the loop, if any"""

        for edge in self.flowchart.edges(self, direction="out"):
            if edge.edge_subtype == "exit":
                self.logger.debug(f"Loop, node after loop is: {edge.node2}")
                return edge.node2

        # loop is the last node in the flowchart
        self.logger.debug("There is no node after the loop")
        return None

    def loop_node(self):
        """The first node in the loop body"""

        for edge in self.flowchart.edges(self, direction="out"):
            if edge.edge_subtype == "loop":
                self.logger.debug(f"Loop, first node in loop is: {edge.node2}")
                return edge.node2

        # There is no body of the loop!
        self.logger.debug("There is no loop body")
        return None
