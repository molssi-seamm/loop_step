# -*- coding: utf-8 -*-

"""A parallel Loop, end to end, without external codes (phase 6).

A tiny step plug-in, installed for the test on PYTHONPATH (a module and its
dist-info with the entry points), makes a system named after the loop's value,
appends a row to a table it creates if needed, and writes a job-level file. The
same flowchart is run serially and in parallel, each by ``run_flowchart`` in its
own directory, and the databases and files are compared.
"""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import textwrap

import pytest

BIN = Path(sys.executable).parent
# The source under test first, for this process's tools and the iterations'
SOURCE = Path(__file__).resolve().parents[1]
BUILD = "import sys; from seamm.flowchart_cli import main; sys.exit(main())"
RUN = "import sys; from seamm_exec import run; sys.argv[0] = 'run_flowchart'; run()"

FAKE_STEP = textwrap.dedent('''
    """A step for testing parallel loops: a system, a table row, a file."""

    import seamm


    class FakeParameters(seamm.Parameters):
        parameters = {
            "name": {
                "default": "x",
                "kind": "string",
                "default_units": "",
                "enumeration": tuple(),
                "format_string": "s",
                "description": "Name:",
                "help_text": "The name of the system and row.",
            },
        }

        def __init__(self, defaults={}, data=None):
            super().__init__(
                defaults={**FakeParameters.parameters, **defaults}, data=data
            )


    class Fake(seamm.Node):
        def __init__(self, flowchart=None, extension=None):
            super().__init__(flowchart=flowchart, title="Fake", extension=extension)
            self.parameters = FakeParameters()

        @property
        def version(self):
            return "0.1"

        def description_text(self, P=None):
            return self.header + "\\n    A fake step."

        def run(self):
            next_node = super().run(None)
            P = self.parameters.current_values_to_dict(
                context=seamm.flowchart_variables._data
            )
            name = str(P["name"])
            db = self.get_variable("_system_db")
            system = db.create_system(name=name)
            configuration = system.create_configuration(name=name)
            configuration.atoms.append(
                x=[0.0], y=[0.0], z=[float(len(name))], symbol=["He"]
            )
            db.system = system
            table = self.get_table("results")
            if "name" not in table.columns:
                table.add_column("name", "string", "")
            table.append_row(name=name)
            (self.job_path / "last.txt").write_text(name + "\\n")
            return next_node


    class FakeStep:
        my_description = {
            "description": "A fake step for tests",
            "group": "Control",
            "name": "Fake",
        }

        def __init__(self, flowchart=None, gui=None):
            pass

        def description(self):
            return FakeStep.my_description

        def create_node(self, flowchart=None, **kwargs):
            return Fake(flowchart=flowchart, **kwargs)

        def create_tk_node(self, canvas=None, **kwargs):
            raise NotImplementedError("no GUI for the fake step")
''')

SPEC = textwrap.dedent("""\
    title: Parallel loop test
    steps:
    - Loop:
        type: Foreach
        variable: name
        values: alpha beta gamma delta
        {parallel}
        body:
        - Fake:
            name: $name
    """)


@pytest.fixture(scope="module")
def fake_plugin(tmp_path_factory):
    """A site directory holding the fake step and its entry points."""
    site = tmp_path_factory.mktemp("site")
    (site / "fakestep.py").write_text(FAKE_STEP)
    info = site / "fakestep-0.1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fakestep\nVersion: 0.1\n"
    )
    (info / "entry_points.txt").write_text(
        "[org.molssi.seamm]\nFake = fakestep:FakeStep\n\n"
        "[org.molssi.seamm.tk]\nFake = fakestep:FakeStep\n"
    )
    return site


def environment(site):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("SEAMM_RESUME", "SEAMM_PARENT_JOB", "SEAMM_CE"))
    }
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SOURCE), str(site), *filter(None, [os.environ.get("PYTHONPATH")])]
    )
    return env


def run(site, directory, parallel):
    directory.mkdir()
    text = "parallel: 'yes'" if parallel else ""
    if parallel:
        text += "\n    iterations at once: '2'\n    memory per iteration: '0.2'"
    (directory / "spec.yaml").write_text(SPEC.format(parallel=text))
    env = environment(site)
    built = subprocess.run(
        [sys.executable, "-c", BUILD, "build", "spec.yaml", "-o", "test.flow"],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stdout[-3000:] + built.stderr[-3000:]
    result = subprocess.run(
        [sys.executable, "-c", RUN, "test.flow"],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return directory


def contents(directory):
    db = sqlite3.connect(f"file:{directory / 'seamm.db'}?mode=ro", uri=True)
    try:
        systems = db.execute("SELECT name FROM system ORDER BY id").fetchall()
        coordinates = db.execute(
            "SELECT configuration, z FROM coordinates ORDER BY configuration"
        ).fetchall()
        (sql_name,) = db.execute(
            "SELECT sql_name FROM _tables WHERE name = 'results'"
        ).fetchone()
        rows = db.execute(f'SELECT * FROM "{sql_name}"').fetchall()
    finally:
        db.close()
    return systems, coordinates, rows, (directory / "last.txt").read_text()


@pytest.mark.skipif(
    not (BIN / "run_flowchart").exists(),
    reason="run_flowchart (for the iterations) is not installed beside Python",
)
def test_parallel_loop_gives_the_serial_result(fake_plugin, tmp_path):
    serial = run(fake_plugin, tmp_path / "serial", parallel=False)
    parallel = run(fake_plugin, tmp_path / "parallel", parallel=True)
    expected = contents(serial)
    assert [s for (s,) in expected[0]] == ["alpha", "beta", "gamma", "delta"]
    assert contents(parallel) == expected
    # Each iteration ran in an evaluator of its own
    evaluators = sorted(p.parent.name for p in parallel.rglob("_evaluator/job.out"))
    assert len(evaluators) == 4
