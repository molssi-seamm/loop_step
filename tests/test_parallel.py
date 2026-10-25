# -*- coding: utf-8 -*-

"""A parallel Loop, end to end, without external codes (phase 6).

A tiny step plug-in, installed for the test on PYTHONPATH (a module and its
dist-info with the entry points), makes a system named after the loop's value,
appends a row to a table it creates if needed, writes a job-level file, and records
a run in ``_md_runs`` as an MD step does, with a data file in its directory. The
same flowchart is run serially and in parallel, each by ``run_flowchart`` in its
own directory, and the databases and files are compared.
"""

import json
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
    """A step for testing parallel loops: a system, a table row, a file, a run."""

    import json
    from pathlib import Path

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
            # A marker file in the job asks this iteration to fail
            if (Path(self.flowchart.root_directory) / f"fail_{name}").exists():
                raise RuntimeError(f"failing {name}, as asked")
            if name == "report":
                # The runs recorded so far, with their paths relative to the job
                runs = []
                if self.variable_exists("_md_runs"):
                    runs = self.get_variable("_md_runs")
                job = Path(self.flowchart.root_directory).resolve()
                text = [
                    dict(r, path=str(Path(r["path"]).relative_to(job))) for r in runs
                ]
                (self.job_path / "md_runs.json").write_text(json.dumps(text))
                return next_node
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
            # A run, as an MD step records it
            directory = Path(self.directory)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "md.h5md"
            path.write_text(name + "\\n")
            runs = []
            if self.variable_exists("_md_runs"):
                runs = list(self.get_variable("_md_runs"))
            runs.append(
                {
                    "path": str(path.resolve()),
                    "step": f"{'.'.join(str(i) for i in self._id)} {self.title}",
                    "name": name,
                }
            )
            self.set_variable("_md_runs", runs)
            if name == "skipped":
                from loop_step import skip_iteration

                skip_iteration()
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
        values: {values}
        {parallel}
        body:
        - Fake:
            name: $name
    {after}""")


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


def run(site, directory, parallel, values="alpha beta gamma delta", after=""):
    directory.mkdir()
    text = "parallel: 'yes'" if parallel else ""
    if parallel:
        text += "\n    iterations at once: '2'\n    memory per iteration: '0.2'"
    (directory / "spec.yaml").write_text(
        SPEC.format(parallel=text, values=values, after=after)
    )
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


AFTER = """\
- Fake:
      name: report
"""


@pytest.mark.skipif(
    not (BIN / "run_flowchart").exists(),
    reason="run_flowchart (for the iterations) is not installed beside Python",
)
def test_parallel_loop_keeps_the_runs_of_its_iterations(fake_plugin, tmp_path):
    """The runs recorded in ``_md_runs`` in the iterations are there after the
    loop, in order, as after a serial loop; a skipped iteration's are not."""
    values = "alpha beta skipped delta"
    serial = run(fake_plugin, tmp_path / "serial", False, values, AFTER)
    parallel = run(fake_plugin, tmp_path / "parallel", True, values, AFTER)
    expected = json.loads((serial / "md_runs.json").read_text())
    assert [r["name"] for r in expected] == ["alpha", "beta", "delta"]
    assert json.loads((parallel / "md_runs.json").read_text()) == expected
    for directory in (serial, parallel):
        for record in expected:
            assert (directory / record["path"]).read_text() == record["name"] + "\n"


def job(site, directory, values, loop="", after="", resume=False, fail=()):
    """Build (once) and run the parallel-loop flowchart; return the result."""
    env = environment(site)
    if not resume:
        directory.mkdir()
        text = (
            "parallel: 'yes'\n    iterations at once: '2'\n"
            "    memory per iteration: '0.2'" + loop
        )
        (directory / "spec.yaml").write_text(
            SPEC.format(parallel=text, values=values, after=after)
        )
        built = subprocess.run(
            [sys.executable, "-c", BUILD, "build", "spec.yaml", "-o", "test.flow"],
            cwd=directory,
            env=env,
            capture_output=True,
            text=True,
        )
        assert built.returncode == 0, built.stdout[-3000:] + built.stderr[-3000:]
    for name in fail:
        (directory / f"fail_{name}").write_text("")
    return subprocess.run(
        [sys.executable, "-c", RUN, "test.flow", *(["--resume"] if resume else [])],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def system_names(directory):
    db = sqlite3.connect(f"file:{directory / 'seamm.db'}?mode=ro", uri=True)
    try:
        return [s for (s,) in db.execute("SELECT name FROM system ORDER BY id")]
    finally:
        db.close()


@pytest.mark.skipif(
    not (BIN / "run_flowchart").exists(),
    reason="run_flowchart (for the iterations) is not installed beside Python",
)
def test_parallel_all_failed_stops_and_resume_reruns(fake_plugin, tmp_path):
    """SEAMM job 5366, 2026-10-24: every iteration failed and the loop counted
    as done. Now the job stops at the loop, and a resume runs the iterations
    again, each from where it failed."""
    d = tmp_path / "job"
    result = job(fake_plugin, d, "alpha beta", after=AFTER, fail=("alpha", "beta"))
    assert result.returncode != 0
    out = (d / "job.out").read_text()
    assert "All 2 iterations of the loop failed" in out
    # The same wording as a serial loop's, which the docs tell users to look for
    assert out.count("Caught exception in loop iteration") == 2
    assert not (d / "md_runs.json").exists()  # the step after the loop did not run

    for name in ("alpha", "beta"):
        (d / f"fail_{name}").unlink()
    result = job(fake_plugin, d, "alpha beta", after=AFTER, resume=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert system_names(d) == ["alpha", "beta"]
    assert [r["name"] for r in json.loads((d / "md_runs.json").read_text())] == [
        "alpha",
        "beta",
    ]


@pytest.mark.skipif(
    not (BIN / "run_flowchart").exists(),
    reason="run_flowchart (for the iterations) is not installed beside Python",
)
def test_parallel_rerun_failed_iterations(fake_plugin, tmp_path):
    """With 'rerun failed', one failed iteration stops the job at the end of the
    loop; the resume runs only it again and merges it after the others."""
    d = tmp_path / "job"
    loop = "\n    rerun failed: 'yes'"
    result = job(fake_plugin, d, "alpha beta gamma", loop=loop, fail=("beta",))
    assert result.returncode != 0
    assert "1 of 3 iterations of the loop failed" in (d / "job.out").read_text()
    assert system_names(d) == ["alpha", "gamma"]

    (d / "fail_beta").unlink()
    result = job(fake_plugin, d, "alpha beta gamma", loop=loop, resume=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert system_names(d) == ["alpha", "gamma", "beta"]
    # Only the failed iteration ran again
    evaluators = sorted(p.parent.parent.name for p in d.rglob("_evaluator/job.out"))
    assert len(evaluators) == 3


@pytest.mark.skipif(
    not (BIN / "run_flowchart").exists(),
    reason="run_flowchart (for the iterations) is not installed beside Python",
)
def test_parallel_some_failed_carries_on_by_default(fake_plugin, tmp_path):
    d = tmp_path / "job"
    result = job(fake_plugin, d, "alpha beta gamma", fail=("beta",))
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert system_names(d) == ["alpha", "gamma"]
