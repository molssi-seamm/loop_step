# -*- coding: utf-8 -*-

"""Non-graphical part of the Loop step in a SEAMM flowchart"""

import json
import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
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


def _plain(value):
    """A plain Python value for JSON, e.g. from a numpy scalar."""
    if hasattr(value, "item") and not isinstance(value, (list, tuple, dict)):
        return value.item()
    return value


printer = printing.getPrinter("loop")

# How many times an iteration of a parallel loop whose evaluator stopped early
# (killed, out of memory) is run again, resuming from its checkpoint
MAX_RETRIES = 2


class _Collect(logging.Handler):
    """Collects the warnings of a merge, for job.out."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _yes(value):
    """A boolean parameter's value, as text or as a bool."""
    if isinstance(value, str):
        return value.strip().lower() in ("yes", "true", "1")
    return bool(value)


def _in_units(value, units):
    """A quantity's magnitude in ``units``; None when not given."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text.startswith("not"):
            return None
        from seamm_util import Q_

        value = Q_(text)
    if hasattr(value, "to"):
        return float(value.to(units).magnitude)
    return float(value)


def _get_decimal_places(value):
    """Get the number of decimal places in a float."""
    if not isinstance(value, float):
        return 0
    parts = str(value).split(".")
    if len(parts) == 2:
        return len(parts[1])
    return 0


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
    def all_options(self):
        """The complete set of all options."""
        return self._all_options

    @all_options.setter
    def all_options(self, value):
        self._all_options = value
        # and set for the subnodes
        node = self.loop_node()
        while node is not None and node != self:
            node.all_options = value
            node = node.next()

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
            subtext = seamm.standard_parameters.structure_selection_description(
                P
            ).replace("will be used", "will be looped over")
            subtext += "\n"
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

        # Resuming a job part way through this loop? Then the checkpoint holds
        # the loop's state and the variables, so the set-up below is skipped and
        # the iteration it was in is set up again rather than advanced to.
        checkpointer = seamm.checkpoint.get_checkpointer()
        resume = None
        if checkpointer is not None:
            resume = checkpointer.loop_resume(self)
        state = None
        resume_node = None
        if resume is not None:
            state, resume_node = resume

        # The evaluator of one iteration of a parallel loop runs just that one
        only = state is not None and state.get("only", False)
        parallel = not only and self._parallel(P, checkpointer)
        if state is not None and state.get("parallel") and not parallel:
            raise seamm.CheckpointError(
                "This loop was running its iterations in parallel when the job "
                "stopped, and cannot resume them one after another."
            )
        if state is not None and not state.get("parallel"):
            self._restore_state(state)

        # Print out header to the main output
        printer.important(__(self.description_text(P), indent=self.indent))

        context = self._prepare(P, state)

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

        try:
            if parallel:
                self._run_parallel(P, context, checkpointer, state)
            else:
                self._run_serial(
                    P, context, checkpointer, state, resume_node, only=only
                )
        finally:
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

    # ------------------------------------------------------------------
    # Setting the loop and its iterations up
    # ------------------------------------------------------------------
    def _prepare(self, P, state=None):
        """What the iterations are: a dict with their number, ``length``.

        On a fresh start (``state`` None) also initializes the loop's variables;
        resuming, the items of a loop over rows or systems are the ones in the
        checkpoint, frozen when the loop started.
        """
        fresh = state is None
        context = {}
        if P["type"] == "For":
            # See if loop variables are all integers
            start = P["start"]
            if isinstance(start, str):
                start = float(start)
            if start.is_integer():
                start = int(start)

            step = P["step"]
            if isinstance(step, str):
                step = float(step)
            if step.is_integer():
                step = int(step)

            end = P["end"]
            if isinstance(end, str):
                end = float(end)
            if end.is_integer():
                end = int(end)

            # If floating point, remove nasty extra digits
            ndigits = max(
                _get_decimal_places(start),
                _get_decimal_places(step),
                _get_decimal_places(end),
            )
            if ndigits > 0:
                fmt = f".{ndigits}f"
            else:
                fmt = f"0{len(str(end))}d"

            # The values, as adding the step each iteration gives them (range
            # doesn't work for nonintegers)
            values = []
            tmp = start
            while tmp <= end:
                values.append(tmp)
                tmp += step
                if ndigits > 0:
                    tmp = round(tmp, ndigits)
            context.update(
                start=start, step=step, end=end, ndigits=ndigits, fmt=fmt, values=values
            )
            context["past"] = tmp
            context["length"] = len(values)
            if fresh:
                self.logger.info(
                    "For {} from {} to {} by {}".format(
                        P["variable"], P["start"], P["end"], P["step"]
                    )
                )
                self.logger.info("Initializing loop")
                self._loop_count = 0
                self._loop_value = start
                self.set_variable(P["variable"], self._loop_value)
                self._loop_length = len(values)
                self._push_loop_indices(self._loop_value)
        elif P["type"] == "Foreach":
            if isinstance(P["values"], str):
                values = shlex.split(P["values"])
            else:
                values = list(P["values"])
            context["values"] = values
            context["length"] = len(values)
            if fresh:
                self._loop_value = 0
                self._loop_length = len(values)
                self._push_loop_indices(None)
        elif P["type"] == "For rows in table":
            self.table = self.get_table(P["table"], create=False)
            if not fresh:
                table_rows = state["items"]
                table_indices = state["indices"]
            else:
                self.table["loop index"] = True
                self.logger.info(
                    "Initialize loop over {} rows in table {}".format(
                        self.table.n_rows, P["table"]
                    )
                )
                self._loop_value = 0
                self._loop_length = self.table.n_rows
                self._push_loop_indices(None)
                table_rows = self._select_rows(P)
                table_indices = [self.table.label(row) for row in table_rows]
            n_table_indices = len(table_indices)
            index_is_int = False
            fmt = None
            if n_table_indices > 0:
                index_is_int = isinstance(table_indices[0], int)
                if index_is_int:
                    fmt = f"0{len(str(max(table_indices) + 1))}d"
            context.update(
                rows=table_rows,
                indices=table_indices,
                index_is_int=index_is_int,
                fmt=fmt,
                length=n_table_indices,
            )
        elif P["type"] == "For systems in the database":
            # The configurations to loop over: the standard SEAMM selection. An
            # empty selection is simply a loop with no iterations.
            if not fresh:
                system_db = self.get_variable("_system_db")
                configurations = [
                    system_db.get_configuration(cid) for cid in state["items"]
                ]
            else:
                configurations = self.select_configurations(P, errors=False)
                self._loop_value = 0
                self._loop_length = len(configurations)
                self._push_loop_indices(None)
            context["configurations"] = configurations
            context["length"] = len(configurations)
        else:
            raise RuntimeError(f"Don't recognize the loop type {P['type']}")
        if fresh:
            printer.important(
                __(
                    f"The loop will have {context['length']} iterations.\n\n",
                    indent=self.indent + 4 * " ",
                )
            )
        return context

    def _push_loop_indices(self, value):
        """Add this loop's index to the loop indices of the enclosing loops."""
        if self.variable_exists("_loop_indices"):
            tmp = self.get_variable("_loop_indices")
            self.set_variable("_loop_indices", (*tmp, value))
        else:
            self.set_variable("_loop_indices", (value,))
            if value is not None:
                self.set_variable("_loop_index", value)

    def _pop_loop_indices(self):
        """Revert the loop index variables to the next outer loop, if any."""
        tmp = self.get_variable("_loop_indices")
        if len(tmp) <= 1:
            self.delete_variable("_loop_indices")
            self.delete_variable("_loop_index")
        else:
            self.set_variable("_loop_indices", tmp[0:-1])
            self.set_variable("_loop_index", tmp[-2])

    def _set_loop_index(self, value):
        tmp = self.get_variable("_loop_indices")
        self.set_variable("_loop_indices", (*tmp[0:-1], value))
        self.set_variable("_loop_index", value)

    def _select_rows(self, P):
        """The rows of the table to loop over."""
        where = P["where"]
        if where == "Use all rows":
            return [row for row, _ in self.table.rows()]
        if where == "Select rows where column":
            op = P["query-op"]
            if op not in seamm.table.operators:
                raise NotImplementedError(f"Loop query '{op}' not implemented")
            try:
                selection = (
                    P["query-column"],
                    op,
                    P["query-value"],
                    P["query-value2"],
                )
                return [row for row, _ in self.table.rows(where=selection)]
            except ValueError as e:
                if "has no column" not in str(e):
                    raise
                column = P["query-column"]
                raise ValueError(
                    f"Looping over table with criterion on column '{column}': "
                    "that column does not exist."
                )
        raise NotImplementedError(f"Loop cannot handle '{where}'")

    def _iteration_number(self, P):
        """The number (1, 2, ...) of the current iteration, 0 before the first."""
        if P["type"] == "For":
            return self._loop_count
        return self._loop_value

    def _setup_iteration(self, P, context, k):
        """Set the loop's variables, directory name, etc. for iteration ``k``."""
        loop_type = P["type"]
        self._custom_directory_name = None
        if loop_type == "For":
            self._loop_count = k
            self._loop_value = context["values"][k - 1]
            self.set_variable(P["variable"], self._loop_value)
            # Use the value for the directory names
            self._custom_directory_name = f"iter_{self._loop_value:{context['fmt']}}"
            self._set_loop_index(self._loop_value)
            self.logger.info("    Loop value = {}".format(self._loop_value))
        elif loop_type == "Foreach":
            self.logger.debug(f"Foreach {P['variable']} in {P['values']}")
            self._loop_value = k
            value = context["values"][k - 1]
            self.set_variable(P["variable"], value)
            self._set_loop_index(self._loop_value)
            self.logger.info("    Loop value = {}".format(value))
        elif loop_type == "For rows in table":
            self._loop_value = k
            index = context["indices"][k - 1]
            self._set_loop_index(index)
            self.table.current_row = context["rows"][k - 1]

            # Name of directory is the index (+1 since tends to be 0 based)
            if context["index_is_int"]:
                self._custom_directory_name = f"iter_{index + 1:{context['fmt']}}"
            else:
                self._custom_directory_name = self.safe_filename(str(index))

            row = {
                k: v
                for k, v in self.table.get_row().items()
                if k != self.table.index_column
            }
            self.set_variable("_row", row)
            if P["as variables"]:
                for key, value in row.items():
                    # Make a safe variable name
                    key = re.sub(r"[-\\ / \+\*()]", "_", key)
                    self.set_variable(key, value)
            self.logger.debug("   _row = {}".format(row))
        elif loop_type == "For systems in the database":
            self._loop_value = k
            # Set the default system and configuration
            configuration = context["configurations"][k - 1]
            system_db = configuration.system_db
            system = configuration.system
            system_db.system = configuration.system
            system.configuration = configuration

            if P["directory name"] == "system name":
                self._custom_directory_name = self.safe_filename(system.name)
            elif P["directory name"] == "configuration name":
                self._custom_directory_name = self.safe_filename(configuration.name)
            else:
                self._custom_directory_name = None
            self._set_loop_index(self._loop_value)
            self.logger.info(f"       system = {system.name}")
            self.logger.info(f"configuration = {configuration.name}")

    def _end_loop(self, P, context):
        """Tidy the loop's variables away after its last iteration."""
        loop_type = P["type"]
        if loop_type == "For":
            # As always: the loop variable is left one step past the end
            self.set_variable(P["variable"], context["past"])
            self._loop_value = None
            self._custom_directory_name = None
            self._pop_loop_indices()
            self.logger.info(
                f"The loop over {P['variable']} from {context['start']} to "
                f"{context['end']} by {context['step']} finished successfully"
            )
        elif loop_type == "Foreach":
            self._loop_value = None
            self._loop_length = None
            self._pop_loop_indices()
            self.logger.info("The loop over value finished successfully")
        elif loop_type == "For rows in table":
            self._loop_value = None
            self.delete_variable("_row")
            self._pop_loop_indices()
            # and the other info in the table
            self.table["loop index"] = False
            self.table = None
            self.logger.info(
                "The loop over table "
                + self.parameters["table"].value
                + " finished successfully"
            )
        elif loop_type == "For systems in the database":
            self._loop_value = None
            self._loop_length = None
            self._custom_directory_name = None
            self._pop_loop_indices()
            self.logger.info("The loop over value finished successfully")

    def _items(self, P, context):
        """The frozen items of the loop, for the checkpoint."""
        if P["type"] == "For rows in table":
            return (context["rows"], context["indices"])
        elif P["type"] == "For systems in the database":
            return ([c.id for c in context["configurations"]], None)
        return (None, None)

    def _open_iteration_output(self, iter_dir, keep):
        """Direct most output to the iteration's iteration.out."""
        if self._file_handler is not None:
            self._file_handler.close()
            job.removeHandler(self._file_handler)
        path = iter_dir / "iteration.out"
        if not keep:
            path.unlink(missing_ok=True)
        self._file_handler = logging.FileHandler(path)
        self._file_handler.setLevel(printing.NORMAL)
        formatter = logging.Formatter(fmt="{message:s}", style="{")
        self._file_handler.setFormatter(formatter)
        job.addHandler(self._file_handler)

    def _close_iteration_output(self):
        if self._file_handler is not None:
            self._file_handler.close()
            job.removeHandler(self._file_handler)
            self._file_handler = None

    # ------------------------------------------------------------------
    # One iteration after another
    # ------------------------------------------------------------------
    def _run_serial(self, P, context, checkpointer, state, resume_node, only=False):
        """Run the iterations in this evaluator, one after another.

        ``only``: this evaluator runs one iteration of a parallel loop, the one
        it resumed into, and stops when it ends (seamm.IterationDone).
        """
        length = context["length"]
        resuming = state is not None
        if only and resume_node is None:
            # The iteration had finished, but the evaluator had not.
            raise seamm.IterationDone()

        # Cycle through the iterations. Resuming in the middle of an iteration,
        # set it up again without advancing, then start its body at the step
        # that had not finished.
        next_node = self
        advance = not resuming or resume_node is None
        ran = False
        iter_dir = None
        while next_node is not None:
            if next_node is self:
                if only and ran:
                    raise seamm.IterationDone()
                next_node = self.loop_node()
                k = self._iteration_number(P)
                if advance:
                    k += 1
                if k > length:
                    self._end_loop(P, context)
                    break
                self._setup_iteration(P, context, k)

                # Resuming this iteration: its directory is the one it had, not
                # a new unique name next to it.
                if not advance:
                    self._custom_directory_name = state["directory"]

                # Add the iteration to the ids so the directory structure is
                # reasonable
                self.flowchart.reset_visited()
                tmp = self.working_path.name
                self.set_subids((*self._id, tmp))

                # Checkpoint the start of the iteration, with what is needed to
                # set it up again -- before its directory exists, so a kill in
                # between cannot leave a directory the checkpoint does not know.
                if checkpointer is not None:
                    if not advance:
                        next_node = self._find_body_node(resume_node)
                    iteration_state = self._checkpoint_state(
                        P, *self._items(P, context)
                    )
                    if only:
                        iteration_state.update(only=True, done=False)
                    checkpointer.enter_iteration(self, iteration_state, next_node)
                resuming_iteration = not advance
                advance = True
                ran = True

                iter_dir = self.working_path
                iter_dir.mkdir(parents=True, exist_ok=True)
                self._open_iteration_output(iter_dir, keep=resuming_iteration)

            # Run through the steps in the loop body
            try:
                node = next_node
                next_node = next_node.run()
                seamm.step_completed(node, next_node)
            except DeprecationWarning as e:
                printer.normal("\nDeprecation warning: " + str(e))
                traceback.print_exc(file=sys.stderr)
                traceback.print_exc(file=sys.stdout)
            except BreakLoop:
                if only:
                    raise seamm.IterationDone(broke=True)
                break
            except ContinueLoop:
                next_node = self
            except SkipIteration:
                if only:
                    # The parent removes the iteration's directory
                    raise seamm.IterationDone(skipped=True)
                next_node = self
                shutil.rmtree(iter_dir, ignore_errors=True)
            except Exception as e:
                tmp = self.working_path.name
                printer.job(f"Caught exception in loop iteration {tmp}: {str(e)}")
                with open(iter_dir / "stderr.out", "a") as fd:
                    traceback.print_exc(file=fd)
                if only:
                    # The parent decides what a failed iteration means
                    raise
                if "continue" in P["errors"]:
                    next_node = self
                elif "exit" in P["errors"]:
                    if checkpointer is not None:
                        checkpointer.iteration_failed(self, node)
                    break
                else:
                    raise
                # Keep what the failed iteration wrote, as before; a resume
                # carries on with the next iteration.
                if checkpointer is not None:
                    checkpointer.iteration_failed(self, node)

            if self.logger.isEnabledFor(logging.DEBUG):
                p = psutil.Process()
                self.logger.debug(pprint.pformat(p.open_files()))

            self.logger.debug(f"Bottom of loop {next_node}")

        # Return to the normally scheduled step, i.e. fall out of the loop.
        if checkpointer is not None:
            checkpointer.leave_loop(self)

    # ------------------------------------------------------------------
    # Iterations in parallel
    # ------------------------------------------------------------------
    def _parallel(self, P, checkpointer):
        """Whether to run the iterations in parallel."""
        if not _yes(P["parallel"]):
            return False
        if checkpointer is None:
            printer.important(
                __(
                    "The iterations run one after another: running them in "
                    "parallel needs the job's database in a file in the job, with "
                    "checkpoints.",
                    indent=self.indent + 4 * " ",
                )
            )
            return False
        return True

    def _job_database_path(self, system_db):
        """The file of the job's database."""
        name = system_db.filename
        if name.startswith("file:"):
            name = name[5:]
        name = name.split("?")[0]
        path = Path(name)
        if not path.is_absolute():
            path = Path(self.flowchart.job_directory) / path
        return path

    def _run_parallel(self, P, context, checkpointer, state):
        """Run each iteration in an evaluator of its own, then merge them in order.

        See the phase 6 notes in seamm_exec's developer guide. The Loop's
        checkpoint frame holds the frozen items, the directories given out, the
        next iteration to merge, the failed ones, and what the merge needs from
        one iteration to the next; each iteration is merged in one transaction,
        committed with that frame.
        """
        from molsystem.snapshot import baseline, snapshot
        from seamm_exec import LocalPool, TaskSet
        from seamm_exec import iteration as iterations

        length = context["length"]
        system_db = self.get_variable("_system_db")
        loop_directory = Path(self.directory)
        job_directory = Path(self.flowchart.job_directory)
        first = self.loop_node()
        if self._loop_length is None:
            self._loop_length = length
        later_wins = "later" in P["same-cell writes"]

        if state is None:
            items, indices = self._items(P, context)
            current = None
            if system_db.system is not None:
                configuration = system_db.system.configuration
                if configuration is not None:
                    current = configuration.id
            state = {
                "type": P["type"],
                "parallel": True,
                "count": 0,
                "length": length,
                "next": 1,
                "directories": {},
                "failed": [],
                "merge": {},
                "exports": {},
                "current": current,
                "directory": None,
                "loop_count": None,
                "loop_value": None,
            }
            if items is not None:
                state["items"] = [_plain(x) for x in items]
            if indices is not None:
                state["indices"] = [_plain(x) for x in indices]
        else:
            state = json.loads(json.dumps(state))
            printer.important(
                __(
                    f"Resuming the parallel loop: {state['next'] - 1} of {length} "
                    "iterations were done and merged.",
                    indent=self.indent + 4 * " ",
                )
            )
        merge_state = iterations.decode_merge_state(state.get("merge"))

        # Commit the loop's set-up with its frame, then keep the database as the
        # loop starts: every iteration's snapshot is taken from it.
        checkpointer.parallel_loop(self, state)
        entry = loop_directory / "loop_entry.db"
        if state["next"] <= length and not entry.exists():
            loop_directory.mkdir(parents=True, exist_ok=True)
            tmp = entry.with_name(entry.name + ".tmp")
            snapshot(self._job_database_path(system_db), tmp, whole=True)
            # Only ever read: no write-ahead log files beside it
            db = sqlite3.connect(str(tmp))
            try:
                db.execute("PRAGMA journal_mode=DELETE")
            finally:
                db.close()
            os.replace(tmp, entry)

        # A merge stopped after its database part: finish its files
        pending = state.pop("files", None)
        if pending is not None:
            self._merge_iteration_files(pending, loop_directory, job_directory)

        # The resources of each iteration
        cores = max(1, int(P["cores per iteration"]))
        memory = _in_units(P["memory per iteration"], "byte")
        walltime = _in_units(P["time per iteration"], "s")
        at_once = P["iterations at once"]
        if isinstance(at_once, str):
            at_once = None if "as many" in at_once else int(at_once)
        placement = "inline" if P["placement"] == "inline" else "separate"
        whole = P["snapshot"] == "whole database"
        root = None
        try:
            root = self.global_options.get("root")
        except Exception:
            pass
        pool = LocalPool(self.flowchart.executor, root=root, max_concurrent=at_once)
        task_set = TaskSet(self, local=pool, root=root)

        # A loop that had stopped (a break, or an error) dispatches nothing more
        stopped = None
        if state.get("stopped") is not None:
            stopped = tuple(state["stopped"])
        last = length if stopped is None else 0

        # Set each iteration up, write its snapshot and checkpoint, add its task
        keys = {}
        for k in range(state["next"], last + 1):
            self._setup_iteration(P, context, k)
            name = state["directories"].get(str(k))
            if name is None:
                # On record before the directory exists, as for a serial loop
                name = self.working_path.name
                state["directories"][str(k)] = name
                checkpointer.parallel_loop(self, state)
            self._custom_directory_name = name
            self.flowchart.reset_visited()
            self.set_subids((*self._id, name))

            evaluator = loop_directory / name / iterations.EVALUATOR_DIRECTORY
            if not (evaluator / "seamm.db").exists():
                shutil.rmtree(evaluator, ignore_errors=True)
                evaluator.mkdir(parents=True)
                configurations = [state["current"]]
                if P["type"] == "For systems in the database":
                    configurations.append(context["configurations"][k - 1].id)
                tmp = evaluator / "seamm.db.tmp"
                snapshot(
                    entry,
                    tmp,
                    configurations=[c for c in configurations if c is not None],
                    whole=whole,
                )
                checkpointer.write_child(
                    tmp,
                    self,
                    self._checkpoint_state(P, *self._items(P, context)),
                    first,
                )
                baseline(tmp, evaluator / "baseline.db")
                os.replace(tmp, evaluator / "seamm.db")
            task = iterations.iteration_task(
                f"iteration_{k}",
                evaluator,
                job_directory,
                command_line=checkpointer.command_line,
                cores=cores,
                memory=memory,
                walltime=walltime,
                placement=placement,
                root_directory=self.flowchart.root_directory,
                # A file the iteration has not written: this evaluator's, then
                # those it reads itself
                read_directories=[
                    job_directory,
                    *getattr(self.flowchart, "job_read_directories", []),
                ],
            )
            task_set.add(task)
            keys[task.key] = k

        n = len(keys)
        if n > 0:
            printer.important(
                __(
                    f"Running {n} iterations in parallel, each with {cores} cores "
                    f"and {P['memory per iteration']} of memory.",
                    indent=self.indent + 4 * " ",
                )
            )

        # Merge the iterations in order as they finish. An iteration whose
        # evaluator stopped before the iteration ended (killed, out of memory,
        # a lost node) runs again, resuming from its own checkpoint.
        results = {}
        retries = {}
        to_run = task_set if n > 0 else None
        while to_run is not None:
            again = []
            runs = to_run.run()
            try:
                for result in runs:
                    k = keys[result.key]
                    if self._stopped_early(state, k, loop_directory):
                        if retries.get(k, 0) < MAX_RETRIES:
                            retries[k] = retries.get(k, 0) + 1
                            printer.job(
                                f"    Loop iteration {state['directories'][str(k)]} "
                                "stopped before it ended; running it again."
                            )
                            again.append(task_set.tasks[result.key])
                            continue
                    results[k] = result
                    while state["next"] in results:
                        k = state["next"]
                        stopped = self._merge_iteration(
                            P,
                            context,
                            state,
                            merge_state,
                            k,
                            results.pop(k),
                            checkpointer,
                            system_db,
                            loop_directory,
                            job_directory,
                            later_wins,
                        )
                        if stopped is not None:
                            break
                    if stopped is not None:
                        break
            finally:
                # Cancels the iterations still running
                runs.close()
            to_run = None
            if stopped is None and len(again) > 0:
                to_run = TaskSet(self, local=pool, root=root)
                for task in again:
                    to_run.add(task)

        if stopped is not None:
            k, why = stopped
            unmerged = sorted(results) + [
                keys[key]
                for key in task_set.tasks
                if keys[key] > k and keys[key] not in results
            ]
            if len(unmerged) > 0:
                names = ", ".join(
                    state["directories"][str(i)] for i in sorted(unmerged)
                )
                printer.important(
                    __(
                        f"The iterations after {state['directories'][str(k)]} are "
                        f"not merged; their directories are kept: {names}.",
                        indent=self.indent + 4 * " ",
                    )
                )
        # Tables the iterations exported, written again from the merged ones
        for name, filename in state.get("exports", {}).items():
            try:
                self.get_table(name, create=False).export(filename)
            except Exception as e:
                printer.important(f"Could not export the table '{name}': {e}")
        if stopped is None or stopped[1] != "raise":
            # Nothing more is dispatched (a resume after "stop the job" runs the
            # failed iteration again, from the loop's entry)
            for suffix in ("", "-wal", "-shm"):
                Path(str(entry) + suffix).unlink(missing_ok=True)

        n_failed = len(state["failed"])
        text = f"Merged {state['next'] - 1 - n_failed} of {length} iterations"
        if n_failed > 0:
            failed = ", ".join(state["directories"][str(i)] for i in state["failed"])
            text += f"; {n_failed} failed and were not merged: {failed}"
        printer.important(__(text + ".", indent=self.indent + 4 * " "))

        if stopped is None:
            self._end_loop(P, context)
        else:
            k, why = stopped
            # The loop's variables as the iteration that ended it left them
            self._setup_iteration(P, context, k)
            if why == "raise":
                raise RuntimeError(
                    f"Iteration {state['directories'][str(k)]} of the loop failed."
                )
        checkpointer.leave_loop(self)

    def _evaluator_directory(self, state, k, loop_directory):
        from seamm_exec import iteration as iterations

        return (
            loop_directory
            / state["directories"][str(k)]
            / iterations.EVALUATOR_DIRECTORY
        )

    def _stopped_early(self, state, k, loop_directory):
        """Whether iteration ``k``'s evaluator stopped before the iteration ended.

        It did if its checkpoint is still 'running': an evaluator that ends,
        with an error or not, says so in its checkpoint.
        """
        path = self._evaluator_directory(state, k, loop_directory) / "seamm.db"
        if not path.exists():
            return False
        try:
            checkpoint = seamm.read_checkpoint(path)
        except Exception:
            return False
        return checkpoint is not None and checkpoint.get("state") == "running"

    def _merge_iteration(
        self,
        P,
        context,
        state,
        merge_state,
        k,
        result,
        checkpointer,
        system_db,
        loop_directory,
        job_directory,
        later_wins,
    ):
        """Merge iteration ``k``, or record that it failed.

        Returns
        -------
        (int, str) or None
            ``(k, why)`` if the loop stops here ("break", "exit" or "raise").
        """
        from seamm_exec import iteration as iterations

        name = state["directories"][str(k)]
        iter_dir = loop_directory / name
        evaluator = iter_dir / iterations.EVALUATOR_DIRECTORY
        # The iteration's own final checkpoint says whether it ended: an
        # evaluator killed as it exited, after finishing, did its work.
        outcome = iterations.iteration_outcome(evaluator)
        if outcome is None:
            reason = result.reason or f"return code {result.returncode}"
            printer.job(
                f"Caught an error in loop iteration {name} ({reason}); see "
                f"{evaluator / 'job.out'}."
            )
            if "stop" in P["errors"]:
                # The job fails here; a resume runs the iteration again
                return (k, "raise")
            state["failed"].append(k)
            state["next"] = k + 1
            state["count"] = k
            if "continue" in P["errors"]:
                checkpointer.parallel_loop(self, state)
                return None
            state["stopped"] = [k, "exit"]
            checkpointer.parallel_loop(self, state)
            return (k, "exit")

        from molsystem.snapshot import MergeConflict

        if P["type"] == "For systems in the database":
            # As a serial loop leaves it: the iteration's configuration current,
            # unless its body chose another (merged below). The merge cannot see
            # a choice of the configuration that was current at the loop's entry.
            configuration = context["configurations"][k - 1]
            system_db.system = configuration.system
            configuration.system.configuration = configuration
        tables_before = set(system_db.user_tables)
        warnings = _Collect()
        merge_logger = logging.getLogger("molsystem.snapshot")
        merge_logger.addHandler(warnings)
        try:
            merged = iterations.merge_database(
                system_db, evaluator, merge_state, k, later_wins=later_wins
            )
        except MergeConflict as e:
            text = str(e).replace(" (The Loop can let the later one win.)", "")
            raise MergeConflict(
                f"{text} Set the Loop's 'Two iterations writing one table cell' to "
                "'the later iteration wins' to keep the later value instead."
            ) from None
        finally:
            merge_logger.removeHandler(warnings)
        for message in warnings.messages:
            printer.job(f"    Warning: {message}")
        # Tables made in the body are variables, as a serial loop leaves them
        for table in set(system_db.user_tables) - tables_before:
            if not self.variable_exists(table):
                self.set_variable(table, seamm.Table(system_db, table))
        if P["type"] == "For rows in table":
            # As a serial loop leaves it: the iteration's row, unless its body
            # moved on (below). The merge cannot see a move to the row that was
            # current when the loop started.
            self.table.current_row = context["rows"][k - 1]
        for table, row in merged["current_rows"].items():
            system_db.user_tables[table].current_row = row
        for table, filename in merged["exports"].items():
            state["exports"][table] = str(
                iterations.export_path(filename, evaluator, job_directory)
            )
        system_id = outcome.get("system_id")
        if system_id is not None:
            system_id = merged["maps"].get("system", {}).get(system_id, system_id)
            if system_id in system_db.system_ids:
                system_db.system = system_id
        plan = iterations.plan_files(evaluator, job_directory, outcome.get("run_id"))
        state["files"] = {"iteration": k, "directory": name, "plan": plan}
        state["next"] = k + 1
        state["count"] = k
        state["merge"] = iterations.encode_merge_state(merge_state)
        stop = None
        if outcome.get("break"):
            stop = (k, "break")
            state["stopped"] = [k, "break"]
        checkpointer.parallel_loop(self, state)
        self._merge_iteration_files(state.pop("files"), loop_directory, job_directory)
        if outcome.get("skip"):
            shutil.rmtree(iter_dir, ignore_errors=True)
        printer.job(f"    Merged loop iteration {name}.")
        return stop

    def _merge_iteration_files(self, pending, loop_directory, job_directory):
        """The job-level files and citations of a merged iteration.

        ``pending`` is the record in the Loop's frame, committed with the
        iteration's database merge; doing it twice gives the same files.
        """
        from seamm_exec import iteration as iterations

        evaluator = (
            loop_directory / pending["directory"] / iterations.EVALUATOR_DIRECTORY
        )
        if not evaluator.exists():
            # Merged and removed (a skipped iteration) before the job stopped
            return
        iterations.merge_files(evaluator, job_directory, pending["plan"])
        iterations.merge_citations(evaluator, self.references)

    def _checkpoint_state(self, P, items=None, indices=None):
        """The loop's state at the start of an iteration, for the checkpoint."""
        if P["type"] == "For":
            count = self._loop_count
        else:
            count = self._loop_value
        state = {
            "type": P["type"],
            "count": count,
            "length": self._loop_length,
            "loop_count": self._loop_count,
            "loop_value": _plain(self._loop_value),
            "directory": self._custom_directory_name,
        }
        if items is not None:
            state["items"] = [_plain(x) for x in items]
        if indices is not None:
            state["indices"] = [_plain(x) for x in indices]
        return state

    def _restore_state(self, state):
        """Restore the loop's state from the checkpoint, to resume it."""
        self._loop_count = state["loop_count"]
        self._loop_value = state["loop_value"]
        self._loop_length = state["length"]
        self._custom_directory_name = state["directory"]

    def _find_body_node(self, node_id):
        """The node of the loop's body with the given id (a list of strings)."""
        node = seamm.checkpoint.find_node(self.flowchart, node_id)
        if node is not None:
            return node
        raise seamm.CheckpointError(
            f"Cannot find step {'.'.join(node_id)} in the loop to resume at."
        )

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
