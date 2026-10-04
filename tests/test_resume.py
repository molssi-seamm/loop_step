# -*- coding: utf-8 -*-

"""Resuming a flowchart part way through a Loop (phase 5 checkpoints).

Each test runs a flowchart once without interruption, then again in a fresh
directory with a "crash" (an exception no Loop catches, standing in for a kill:
the step's writes are rolled back, as for a killed process) at a chosen step and
iteration, resumes it, and checks that every step ran exactly once overall and
that the job database and directories are the same as the uninterrupted run's.
"""

import os
import sqlite3

import pytest

import loop_step
import seamm
import seamm_exec.exec_flowchart as ef


class Crash(BaseException):
    """Stands in for the process being killed."""


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    import seamm_util.argument_parser

    monkeypatch.setattr(seamm_util.argument_parser, "_parsers", {})
    monkeypatch.delenv(ef.RESUME_ENVIRONMENT, raising=False)
    Step.runs = []
    Step.crash = None
    Step.fail = set()


class Step(seamm.Node):
    """Creates a system named after itself and the loop indices; can crash."""

    version = "2026.10.4"
    runs = []
    crash = None  # (title, indices) to crash at, once
    fail = set()  # (title, indices) that raise an ordinary error

    def run(self):
        indices = self._indices()
        key = (self.title, indices)
        Step.runs.append(key)
        db = self.get_variable("_system_db")
        name = f"{self.title}{list(indices)}"
        db.create_system(name=name).create_configuration(name=name)
        if Step.crash == key or Step.crash == (self.title, None):
            Step.crash = None
            raise Crash(f"crash at {key}")
        if key in Step.fail:
            raise RuntimeError(f"failed at {key}")
        self.extra(db)
        return self.next()

    def extra(self, db):
        pass

    def _indices(self):
        if self.variable_exists("_loop_indices"):
            return tuple(self.get_variable("_loop_indices"))
        return ()


class AppendRow(Step):
    """Appends a row to the table being looped over (which must not grow the
    loop) and records the current row's name."""

    def extra(self, db):
        table = self.get_table("molecules")
        table.set_cell("seen", True)
        table.append_row(name=f"added at {self._indices()}", seen=False)


class MakeTable(Step):
    def extra(self, db):
        table = seamm.Table.create(
            db,
            "molecules",
            columns=[("name", "string"), ("seen", "boolean")],
            index_column="name",
        )
        for name in ("water", "ammonia", "methane", "ethane"):
            table.append_row(name=name, seen=False)
        self.set_variable("molecules", table)


def build(root, body, before=(), after=("After",), **loop_parameters):
    """start -> before... -> Join -> Loop(body...) -> after..., as the editor
    makes it: the body's last step leads back to the Join."""
    flowchart = seamm.Flowchart(directory=str(root))
    previous = flowchart.get_node("1")
    for item in before:
        node = item if isinstance(item, seamm.Node) else Step(flowchart, title=item)
        flowchart.add_node(node)
        flowchart.add_edge(previous, node, edge_type="execution")
        previous = node
    loop = make_loop(flowchart, **loop_parameters)
    add_loop(flowchart, previous, loop, body)
    previous = loop
    subtype = "exit"
    for item in after:
        node = item if isinstance(item, seamm.Node) else Step(flowchart, title=item)
        flowchart.add_node(node)
        flowchart.add_edge(previous, node, edge_type="execution", edge_subtype=subtype)
        previous = node
        subtype = "next"
    flowchart.set_ids()
    return flowchart


def make_loop(flowchart, **parameters):
    loop = loop_step.Loop(flowchart=flowchart)
    for key, value in parameters.items():
        loop.parameters[key.replace("_", " ")].value = value
    return loop


def add_loop(flowchart, previous, loop, body):
    """previous -> Join -> Loop, with the body from the Loop back to the Join."""
    join = seamm.Join(flowchart=flowchart)
    flowchart.add_node(join)
    flowchart.add_node(loop)
    flowchart.add_edge(previous, join, edge_type="execution")
    flowchart.add_edge(join, loop, edge_type="execution")
    attach_body(flowchart, loop, join, body)


def attach_body(flowchart, loop, join, body):
    previous = loop
    subtype = "loop"
    for item in body:
        if isinstance(item, tuple):  # a nested loop: (loop, body)
            inner, inner_body = item
            add_loop_from(flowchart, previous, subtype, inner, inner_body)
            previous = inner
            subtype = "exit"
            continue
        node = item if isinstance(item, seamm.Node) else Step(flowchart, title=item)
        flowchart.add_node(node)
        flowchart.add_edge(previous, node, edge_type="execution", edge_subtype=subtype)
        previous = node
        subtype = "next"
    flowchart.add_edge(previous, join, edge_type="execution", edge_subtype=subtype)


def add_loop_from(flowchart, previous, subtype, loop, body):
    join = seamm.Join(flowchart=flowchart)
    flowchart.add_node(join)
    flowchart.add_node(loop)
    flowchart.add_edge(previous, join, edge_type="execution", edge_subtype=subtype)
    flowchart.add_edge(join, loop, edge_type="execution")
    attach_body(flowchart, loop, join, body)


def execute(root, flowchart, resume=False):
    options = {"SEAMM": {"resume": resume}}
    plan = ef.plan_start(root, options, flowchart, [])
    if resume:
        assert plan["resume"] is not None, plan["message"]
    cwd = os.getcwd()
    try:
        os.chdir(root)
        ef.ExecFlowchart(flowchart, cmdline=[], plan=plan).run(root=str(root))
    finally:
        os.chdir(cwd)


def database(root):
    """What matters in the job database: systems and user tables."""
    db = sqlite3.connect(f"file:{root / 'seamm.db'}?mode=ro", uri=True)
    try:
        names = [r[0] for r in db.execute("SELECT name FROM system ORDER BY id")]
        tables = {}
        for (sql_name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'table_%'"
        ):
            tables[sql_name] = db.execute(f"SELECT * FROM {sql_name}").fetchall()
        return names, tables
    finally:
        db.close()


def directories(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_dir())


def crash_and_resume(tmp_path, make, crash):
    """Run uninterrupted and crashed+resumed; return both runs' records."""
    straight = tmp_path / "straight"
    straight.mkdir()
    execute(straight, make(straight))
    expected_runs = list(Step.runs)

    crashed = tmp_path / "crashed"
    crashed.mkdir()
    Step.runs = []
    Step.crash = crash
    flowchart = make(crashed)
    with pytest.raises(Crash):
        execute(crashed, flowchart)
    first = list(Step.runs)
    assert first[-1][0] == crash[0]
    checkpoint = seamm.read_checkpoint(crashed / "seamm.db")
    assert checkpoint["state"] == "error"

    Step.runs = []
    flowchart = make(crashed)  # a resume reads the flowchart again: new uuids
    execute(crashed, flowchart, resume=True)
    second = list(Step.runs)
    # The crashed step runs again; everything before it does not.
    assert first[:-1] + second == expected_runs
    assert database(crashed) == database(straight)
    assert directories(crashed) == directories(straight)
    assert seamm.read_checkpoint(crashed / "seamm.db")["state"] == "finished"
    return expected_runs, first, second


def test_for_loop_crash_in_second_body_step(tmp_path):
    def make(root):
        return build(root, ["A", "B"], type="For", variable="i", start=1, end=5)

    crash_and_resume(tmp_path, make, ("B", (3,)))


def test_for_loop_crash_in_first_body_step(tmp_path):
    def make(root):
        return build(root, ["A", "B"], type="For", variable="i", start=1, end=5)

    crash_and_resume(tmp_path, make, ("A", (3,)))


def test_crash_after_the_loop(tmp_path):
    def make(root):
        return build(root, ["A"], type="For", variable="i", start=1, end=3)

    expected, first, second = crash_and_resume(tmp_path, make, ("After", ()))
    assert second == [("After", ())]


def test_foreach(tmp_path):
    def make(root):
        return build(root, ["A", "B"], type="Foreach", variable="x", values="a b c d")

    crash_and_resume(tmp_path, make, ("B", (2,)))


def test_float_for_loop(tmp_path):
    def make(root):
        return build(
            root, ["A"], type="For", variable="T", start=0.1, end=0.5, step=0.1
        )

    crash_and_resume(tmp_path, make, ("A", (0.3,)))


@pytest.mark.parametrize(
    "crash",
    [
        ("A", (1,)),
        ("A", (2,)),
        ("B", (2, 1)),
        ("C", (2, 2)),
        ("C", (2, 3)),
        ("D", (2,)),
        ("B", (3, 1)),
        ("After", ()),
    ],
)
def test_nested_loops(tmp_path, crash):
    def make(root):
        flowchart = seamm.Flowchart(directory=str(root))
        inner = make_loop(flowchart, type="Foreach", variable="x", values="a b c")
        outer = make_loop(flowchart, type="For", variable="i", start=1, end=3)
        add_loop(
            flowchart, flowchart.get_node("1"), outer, ["A", (inner, ["B", "C"]), "D"]
        )
        after = Step(flowchart, title="After")
        flowchart.add_node(after)
        flowchart.add_edge(outer, after, edge_type="execution", edge_subtype="exit")
        flowchart.set_ids()
        return flowchart

    crash_and_resume(tmp_path, make, crash)


def test_table_loop_whose_body_appends_rows(tmp_path):
    """The rows appended by the body are not looped over, resumed or not."""

    def make(root):
        flowchart = seamm.Flowchart(directory=str(root))
        return build(
            root,
            [AppendRow(flowchart, title="Append")],
            before=[MakeTable(flowchart, title="Make")],
            type="For rows in table",
            table="molecules",
        )

    expected, first, second = crash_and_resume(tmp_path, make, ("Append", ("methane",)))
    assert len([r for r in expected if r[0] == "Append"]) == 4


def test_errors_continue_then_crash(tmp_path):
    """An iteration that failed (and was continued past) is not retried."""

    def make(root):
        return build(
            root,
            ["A", "B"],
            type="For",
            variable="i",
            start=1,
            end=5,
            errors="continue to next iteration",
        )

    Step.fail = {("A", (2,))}
    expected, first, second = crash_and_resume(tmp_path, make, ("B", (4,)))
    assert ("A", (2,)) not in second


def test_systems_loop_named_directories(tmp_path):
    """Directories named after systems keep their names when resumed."""

    def make(root):
        return build(
            root,
            ["A", "B"],
            before=["S1", "S2", "S3"],
            type="For systems in the database",
            directory_name="system name",
        )

    crash_and_resume(tmp_path, make, ("B", (2,)))


def test_crash_twice(tmp_path):
    """A resumed run that crashes again resumes again."""

    def make(root):
        return build(root, ["A", "B"], type="For", variable="i", start=1, end=5)

    straight = tmp_path / "straight"
    straight.mkdir()
    execute(straight, make(straight))
    expected = list(Step.runs)

    root = tmp_path / "crashed"
    root.mkdir()
    runs = []
    for crash, resume in ((("B", (2,)), False), (("A", (4,)), True)):
        Step.runs = []
        Step.crash = crash
        with pytest.raises(Crash):
            execute(root, make(root), resume=resume)
        runs.extend(Step.runs[:-1])
    Step.runs = []
    execute(root, make(root), resume=True)
    runs.extend(Step.runs)
    assert runs == expected
    assert database(root) == database(straight)


def test_errors_exit_the_loop_then_crash(tmp_path):
    def make(root):
        return build(
            root,
            ["A", "B"],
            after=("After", "Last"),
            type="For",
            variable="i",
            start=1,
            end=5,
            errors="exit the loop",
        )

    Step.fail = {("B", (3,))}
    # (Leaving a loop early leaves its index variables set, as it always has.)
    expected, first, second = crash_and_resume(tmp_path, make, ("Last", None))
    assert [r[0] for r in second] == ["Last"]
    assert ("A", (4,)) not in expected


def test_an_error_while_resuming_keeps_the_loop_position(tmp_path, monkeypatch):
    """A resume that fails before the Loop re-enters its iteration must leave
    the checkpoint where it was, so the next resume continues the loop rather
    than starting it again over the committed iterations."""

    def make(root):
        return build(root, ["A", "B"], type="For", variable="i", start=1, end=5)

    straight = tmp_path / "straight"
    straight.mkdir()
    execute(straight, make(straight))
    expected = list(Step.runs)

    root = tmp_path / "crashed"
    root.mkdir()
    Step.runs = []
    Step.crash = ("B", (3,))
    with pytest.raises(Crash):
        execute(root, make(root))
    runs = list(Step.runs[:-1])
    before = seamm.read_checkpoint(root / "seamm.db")["position"]

    # The resume fails inside the Loop, before it re-enters the iteration
    original = loop_step.Loop._restore_state

    def broken(self, state):
        raise RuntimeError("cannot restore the loop")

    monkeypatch.setattr(loop_step.Loop, "_restore_state", broken)
    Step.runs = []
    with pytest.raises(RuntimeError, match="cannot restore"):
        execute(root, make(root), resume=True)
    checkpoint = seamm.read_checkpoint(root / "seamm.db")
    assert checkpoint["state"] == "error"
    assert checkpoint["position"] == before

    monkeypatch.setattr(loop_step.Loop, "_restore_state", original)
    Step.runs = []
    execute(root, make(root), resume=True)
    runs.extend(Step.runs)
    assert runs == expected
    assert database(root) == database(straight)
    assert directories(root) == directories(straight)
