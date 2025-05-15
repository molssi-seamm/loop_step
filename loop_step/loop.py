# -*- coding: utf-8 -*-

"""Non-graphical part of the Loop step in a SEAMM flowchart"""

import fnmatch
import logging
from pathlib import Path
import re
import shlex
import shutil
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


class BreakLoop(Exception):
    """Indicates that SEAMM should break from the loop"""

    def __init__(self, message="break from the loop"):
        super().__init__(message)


def break_loop():
    """Break from the loop and continue on."""
    raise BreakLoop()


class ContinueLoop(Exception):
    """Indicates that SEAMM should continue from the loop"""

    def __init__(self, message="continue with next iteration of loop"):
        super().__init__(message)


def continue_loop():
    """Continue to the next iteration of the loop"""
    raise ContinueLoop()


class SkipIteration(Exception):
    """Indicates that SEAMM should skip this iteration of the loop,
    removing any directories, etc."""

    def __init__(self, message="skip iteration of loop"):
        super().__init__(message)


def skip_iteration():
    """Entirely skip this iteration, removing any files, etc."""
    raise SkipIteration()


class Loop(seamm.Node):
    def __init__(self, flowchart=None, extension=None):
        """Setup the non-graphical part of the Loop step in a
        SEAMM flowchart.

        Keyword arguments:
        """
        logger.debug("Creating Loop {}".format(self))

        self.table_handle = None
        self.table = None
        self._loop_count = None
        self._loop_value = None
        self._loop_length = None
        self._file_handler = None
        self._custom_directory_name = None

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
        if self._custom_directory_name is not None:
            tmp = Path(self.directory) / self._custom_directory_name
        else:
            tmp = Path(self.directory) / f"iter_{self._loop_value:{self.iter_format}}"
        return tmp

    def describe(self):
        """Write out information about what this node will do"""

        self.visited = True

        # The description
        job.job(__(self.description_text(), indent=self.indent))

        return self.exit_node()

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
            if self.is_expr(P["values"]):
                subtext = f"Foreach {P['variable']} in {P['values']}\n"
            else:
                if isinstance(P["values"], str):
                    values = [str(v) for v in shlex.split(P["values"])]
                else:
                    values = [str(v) for v in P["values"]]
                if len(values) > 5:
                    last = values[-1]
                    values = values[0:6]
                    values.append("...")
                    values.append(last)
                tmp = ", ".join(values)
                if len(tmp) < 50:
                    subtext = f"Foreach {P['variable']} in {tmp}\n"
                else:
                    tmp = "\n   ".join(values)
                    subtext = f"Foreach {P['variable']} in\n   {tmp}\n"
        elif P["type"] == "For rows in table":
            subtext = "For rows in table {table}\n"
        elif P["type"] == "For systems in the database":
            subtext = "For system in the database\n"
        else:
            subtext = "Loop type defined by {type}\n"

        text += self.header + "\n" + __(subtext, **P, indent=4 * " ").__str__()

        # Print the body of the loop
        join_node = self.previous()
        next_node = self.loop_node()
        while next_node is not None and next_node != join_node:
            text += "\n\n"
            text += str(__(next_node.description_text(), indent=4 * " ", wrap=False))
            next_node = next_node.next()

        return text

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

        # Reset variables to initial state.
        self._custom_directory_name = None

        # Print out header to the main output
        printer.important(__(self.description_text(P), indent=self.indent))

        # Set up some unchanging variables
        if P["type"] == "For":
            # Some local variables need each iteration

            # See if loop variables are all integers
            integers = True
            start = P["start"]
            if isinstance(start, str):
                start = float(start)
            if start.is_integer():
                start = int(start)
            else:
                integers = False
            step = P["step"]
            if isinstance(step, str):
                step = float(step)
            if step.is_integer():
                step = int(step)
            else:
                integers = False
            end = P["end"]
            if isinstance(end, str):
                end = float(end)
            if end.is_integer():
                end = int(end)
            else:
                integers = False

            if integers:
                fmt = f"0{len(str(end))}d"

            if self._loop_value is None:
                self.logger.info(
                    "For {} from {} to {} by {}".format(
                        P["variable"], P["start"], P["end"], P["step"]
                    )
                )

                self.logger.info("Initializing loop")
                self._loop_count = 0
                self._loop_value = start
                self.set_variable(P["variable"], self._loop_value)

                # Loop to get length... range doesn't work for nonintegers
                count = 0
                tmp = start
                while tmp <= end:
                    count += 1
                    tmp += step
                self._loop_length = count
                printer.important(
                    __(
                        f"The loop will have {self._loop_length} iterations.\n\n",
                        indent=self.indent + 4 * " ",
                    )
                )
                if self.variable_exists("_loop_indices"):
                    tmp = self.get_variable("_loop_indices")
                    self.set_variable("_loop_indices", (*tmp, self._loop_value))
                else:
                    self.set_variable("_loop_indices", (self._loop_value,))
                    self.set_variable("_loop_index", self._loop_value)
        elif P["type"] == "Foreach":
            if self._loop_value is None:
                self._loop_value = 0
                if isinstance(P["values"], str):
                    self._loop_length = len(shlex.split(P["values"]))
                else:
                    self._loop_length = len(P["values"])
                printer.important(
                    __(
                        f"The loop will have {self._loop_length} iterations.\n\n",
                        indent=self.indent + 4 * " ",
                    )
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
        elif P["type"] == "For rows in table":
            if self._loop_value is None:
                self.table_handle = self.get_variable(P["table"])
                self.table = self.table_handle["table"]
                self.table_handle["loop index"] = True

                self.logger.info(
                    "Initialize loop over {} rows in table {}".format(
                        self.table.shape[0], P["table"]
                    )
                )
                self._loop_value = 0
                self._loop_length = self.table.shape[0]
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
                    table_indices = [*self.table.index]
                    n_table_indices = len(table_indices)
                elif where == "Select rows where column":
                    tmp_col = P["query-column"].lower()
                    column = None
                    op = P["query-op"]

                    for col in self.table:
                        if col.lower() == tmp_col:
                            column = col
                    if column is None:
                        column = P["query-column"]
                        raise ValueError(
                            f"Looping over table with criterion on column '{column}': "
                            "that column does not exist."
                        )

                    dtype = self.table.dtypes[column]
                    value = dtype.type(P["query-value"])
                    value2 = dtype.type(P["query-value2"])

                    # Find the indices
                    table_indices = []
                    for i, row_value in zip(self.table.index, self.table[column]):
                        if op == "==":
                            if row_value == value:
                                table_indices.append(i)
                        elif op == "!=":
                            if row_value != value:
                                table_indices.append(i)
                        elif op == ">":
                            if row_value > value:
                                table_indices.append(i)
                        elif op == ">=":
                            if row_value >= value:
                                table_indices.append(i)
                        elif op == "<":
                            if row_value < value:
                                table_indices.append(i)
                        elif op == "<=":
                            if row_value <= value:
                                table_indices.append(i)
                        elif op == "between":
                            if row_value >= value and row_value <= value2:
                                table_indices.append(i)
                        elif op == "contains":
                            if value in row_value:
                                table_indices.append(i)
                        elif op == "does not contain":
                            if value not in row_value:
                                table_indices.append(i)
                        elif op == "contains regexp":
                            if re.search(value, row_value) is not None:
                                table_indices.append(i)
                        elif op == "does not contain regexp":
                            if re.search(value, row_value) is None:
                                table_indices.append(i)
                        elif op == "is empty":
                            # Might be numpy.nan, and NaN != NaN hence odd test.
                            if row_value == "" or row_value != row_value:
                                table_indices.append(i)
                        elif op == "is not empty":
                            if row_value != "" and row_value == row_value:
                                table_indices.append(i)
                        else:
                            raise NotImplementedError(
                                f"Loop query '{op}' not implemented"
                            )
                    n_table_indices = len(table_indices)
                else:
                    raise NotImplementedError(f"Loop cannot handle '{where}'")
                printer.important(
                    __(
                        f"The loop will have {n_table_indices} iterations.\n\n",
                        indent=self.indent + 4 * " ",
                    )
                )

                if n_table_indices > 0:
                    index = table_indices[0]
                    index_is_int = isinstance(index, int)
                    if index_is_int:
                        fmt = f"0{len(str(max(table_indices) + 1))}d"
        elif P["type"] == "For systems in the database":
            # Get a list of all the matching systems and configurations
            system_db = self.get_variable("_system_db")
            systems = system_db.systems

            # Filter on system names
            choice = P["where system name"]
            if choice == "is anything":
                pass
            elif choice == "is":
                name = P["system name"]
                systems = [s for s in systems if s.name == name]
            elif choice == "matches":
                pattern = P["system name"]
                systems = [s for s in systems if fnmatch.fnmatch(s.name, pattern)]
            elif choice == "regexp":
                pattern = P["system name"]
                systems = [s for s in systems if re.search(pattern, s.name) is not None]
            else:
                raise RuntimeError(
                    f"Matching system names by '{choice}' is not supported"
                )

            # Finally, allow only systems that contain the requested configuration
            choice = P["default configuration"]
            if choice == "last" or choice == "-1":
                systems = [s for s in systems if s.n_configurations > 0]
                configurations = [s.configurations[-1] for s in systems]
            elif choice == "first" or choice == "1":
                systems = [s for s in systems if s.n_configurations > 0]
                configurations = [s.configurations[0] for s in systems]
            elif choice == "name is":
                name = P["configuration name"]
                systems = [s for s in systems if s.n_configurations > 0]
                configurations = []
                for s in systems:
                    for c in s.configurations:
                        if c.name is name:
                            configurations.append(c)
            elif choice == "matches":
                pattern = P["configuration name"]
                systems = [s for s in systems if s.n_configurations > 0]
                configurations = []
                for s in systems:
                    for c in s.configurations:
                        if fnmatch.fnmatch(c.name, pattern):
                            configurations.append(c)
            elif choice == "regexp":
                pattern = P["configuration name"]
                configurations = []
                for s in systems:
                    for c in s.configurations:
                        if re.search(pattern, c.name) is not None:
                            configurations.append(c)
            elif choice == "all":
                name = P["configuration name"]
                systems = [s for s in systems if s.n_configurations > 0]
                configurations = []
                for s in systems:
                    configurations.extend(s.configurations)

            if self._loop_value is None:
                self._loop_value = 0
                self._loop_length = len(configurations)
                printer.important(
                    __(
                        f"The loop will have {self._loop_length} iterations.\n\n",
                        indent=self.indent + 4 * " ",
                    )
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

        # Cycle through the iterations
        next_node = self
        while next_node is not None:
            if next_node is self:
                next_node = self.loop_node()

                if P["type"] == "For":
                    self._loop_count += 1
                    if self._loop_count > 1:
                        self._loop_value += step

                    self.set_variable(P["variable"], self._loop_value)

                    # For integer loops, we can use the value for the directory names
                    if integers:
                        self._custom_directory_name = f"iter_{self._loop_value:{fmt}}"

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
                    if self._loop_count > self._loop_length:
                        self._loop_value = None
                        self._custom_directory_name = None

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
                    self.logger.debug(f"Foreach {P['variable']} in {P['values']}")

                    self._loop_value += 1

                    if self._loop_value > self._loop_length:
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

                    if isinstance(P["values"], str):
                        value = shlex.split(P["values"])[self._loop_value - 1]
                    else:
                        value = P["values"][self._loop_value - 1]
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
                    self._loop_value += 1
                    if self._loop_value > n_table_indices:
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
                    index = table_indices[self._loop_value - 1]
                    tmp = self.get_variable("_loop_indices")
                    self.logger.debug("  _loop_indices = {}".format(tmp))
                    self.set_variable("_loop_indices", (*tmp[0:-1], index))
                    self.logger.debug(
                        "   --> {}".format(self.get_variable("_loop_indices"))
                    )
                    self.set_variable("_loop_index", index)
                    self.table_handle["current index"] = index

                    # Name of directory is the index (+1 since tends to be 0 based)
                    if index_is_int:
                        self._custom_directory_name = f"iter_{index + 1:{fmt}}"
                    else:
                        self._custom_directory_name = self.safe_filename(str(index))

                    row = {k: self.table.at[index, k] for k in self.table}
                    self.set_variable("_row", row)
                    if P["as variables"]:
                        for key, value in row.items():
                            # Make a safe variable name
                            key = re.sub(r"[-\\ / \+\*()]", "_", key)
                            self.set_variable(key, value)
                    self.logger.debug("   _row = {}".format(row))
                elif P["type"] == "For systems in the database":
                    self._loop_value += 1

                    if self._loop_value > self._loop_length:
                        self._loop_value = None
                        self._loop_length = None
                        self._custom_directory_name = None

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

                    # Set the default system and configuration
                    configuration = configurations[self._loop_value - 1]
                    system_db = configuration.system_db
                    system = configuration.system
                    system_db.system = configuration.system
                    system.configuration = configuration

                    if P["directory name"] == "system name":
                        self._custom_directory_name = self.safe_filename(system.name)
                    elif P["directory name"] == "configuration name":
                        self._custom_directory_name = self.safe_filename(
                            configuration.name
                        )
                    else:
                        self._custom_directory_name = None

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
                    self.logger.info(f"       system = {system.name}")
                    self.logger.info(f"configuration = {configuration.name}")

                # Direct most output to iteration.out
                # A handler for the file
                iter_dir = self.working_path
                iter_dir.mkdir(parents=True, exist_ok=True)

                if self._file_handler is not None:
                    self._file_handler.close()
                    job.removeHandler(self._file_handler)
                path = iter_dir / "iteration.out"
                path.unlink(missing_ok=True)
                self._file_handler = logging.FileHandler(path)
                self._file_handler.setLevel(printing.NORMAL)
                formatter = logging.Formatter(fmt="{message:s}", style="{")
                self._file_handler.setFormatter(formatter)
                job.addHandler(self._file_handler)

                # Add the iteration to the ids so the directory structure is
                # reasonable
                self.flowchart.reset_visited()
                tmp = self.working_path.name
                self.set_subids((*self._id, tmp))

            # Run through the steps in the loop body
            try:
                next_node = next_node.run()
            except DeprecationWarning as e:
                printer.normal("\nDeprecation warning: " + str(e))
                traceback.print_exc(file=sys.stderr)
                traceback.print_exc(file=sys.stdout)
            except BreakLoop:
                break
            except ContinueLoop:
                next_node = self
            except SkipIteration:
                next_node = self
                shutil.rmtree(iter_dir, ignore_errors=True)
            except Exception as e:
                tmp = self.working_path.name
                printer.job(f"Caught exception in loop iteration {tmp}: {str(e)}")
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
        next_node = self.loop_node()
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

    def safe_filename(self, filename):
        clean = re.sub(r"[/\\?%*:|\"<>\x7F\x00-\x1F]", "-", filename)

        # Check for duplicates...
        path = Path(self.directory) / clean
        count = 1
        while path.exists():
            count += 1
            path = Path(self.directory) / f"{clean}_{count}"

        return path.name
