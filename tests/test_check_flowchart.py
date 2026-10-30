# -*- coding: utf-8 -*-

"""The check of a parallel loop's body before the job runs: steps writing their
structure over the configuration the iterations share."""

import pytest

import seamm
from seamm import edit
from seamm.builder import validate

import loop_step

pytest.importorskip("seamm.problems")


class Step(seamm.Node):
    """A step with the standard structure handling, as MD or optimization has."""

    def __init__(self, flowchart, title):
        super().__init__(flowchart=flowchart, title=title, extension="Step")
        self.parameters = seamm.Parameters(
            defaults=dict(seamm.standard_parameters.structure_handling_parameters)
        )


def _connect(flowchart, a, b, subtype):
    flowchart.add_edge(a, b, edge_type="execution", edge_subtype=subtype)


def make(parallel="yes", kind="For", later=False, inside=False):
    """Start -> Loop, whose body is a step, or a step holding it in a sub-flowchart."""
    flowchart = seamm.Flowchart()
    loop = loop_step.Loop(flowchart=flowchart)
    flowchart.add_node(loop)
    _connect(flowchart, flowchart.get_node("1"), loop, "next")
    if inside:
        body = seamm.Node(flowchart=flowchart, title="LAMMPS", extension="Code")
        body.subflowchart = seamm.Flowchart(parent=body)
        step = Step(body.subflowchart, "NVT")
        body.subflowchart.add_node(step)
        _connect(body.subflowchart, body.subflowchart.get_node("1"), step, "next")
    else:
        body = step = Step(flowchart, "Optimization")
    flowchart.add_node(body)
    _connect(flowchart, loop, body, "loop")
    _connect(flowchart, body, loop, "next")
    loop.parameters["parallel"].value = parallel
    loop.parameters["type"].value = kind
    if later:
        loop.parameters["same-cell writes"].value = "the later iteration wins"
    return flowchart, loop, step


def test_a_parallel_loop_warns_and_offers_fixes():
    flowchart, loop, step = make()
    assert validate(flowchart) == []  # a warning, not an error
    (problem,) = validate(flowchart, warnings=True)
    assert problem.severity == "warning"
    assert "'Optimization' in the parallel loop 'Loop'" in problem
    (described,) = edit.describe_problems(flowchart, [problem])
    assert [f["set"] for f in described["fixes"]] == [
        [
            {
                "step": "1.1",
                "parameter": "structure handling",
                "value": "Discard the structure",
            }
        ],
        [
            {
                "step": "1.1",
                "parameter": "structure handling",
                "value": "Create a new configuration",
            }
        ],
    ]
    problem.fixes[1].apply()
    assert step.parameters["structure handling"].value == "Create a new configuration"
    assert validate(flowchart, warnings=True) == []


def test_a_step_inside_a_body_step():
    flowchart, loop, step = make(inside=True)
    (problem,) = validate(flowchart, warnings=True)
    (described,) = edit.describe_problems(flowchart, [problem])
    assert described["fixes"][0]["set"][0]["step"] == "1.1.1"
    problem.fixes[0].apply()
    assert step.parameters["structure handling"].value == "Discard the structure"
    assert validate(flowchart, warnings=True) == []


@pytest.mark.parametrize(
    "settings",
    [
        {"parallel": "no"},
        {"kind": "For systems in the database"},
        {"later": True},
        {"parallel": "$parallel"},
    ],
)
def test_no_warning(settings):
    flowchart, loop, step = make(**settings)
    assert validate(flowchart, warnings=True) == []


class Velocities(seamm.Node):
    """A step with a random seed, as LAMMPS's Velocities sub-step has."""

    def __init__(self, flowchart, seed="random"):
        super().__init__(flowchart=flowchart, title="Velocities", extension="Step")
        self.parameters = seamm.Parameters(
            defaults={
                "seed": {
                    "default": "random",
                    "kind": "integer",
                    "default_units": None,
                    "enumeration": ("random",),
                    "format_string": "",
                    "description": "Random seed:",
                    "help_text": "The seed.",
                }
            }
        )
        self.parameters["seed"].value = seed


def seeded(seed, parallel="no", kind="For"):
    flowchart = seamm.Flowchart()
    loop = loop_step.Loop(flowchart=flowchart)
    flowchart.add_node(loop)
    _connect(flowchart, flowchart.get_node("1"), loop, "next")
    step = Velocities(flowchart, seed)
    flowchart.add_node(step)
    _connect(flowchart, loop, step, "loop")
    _connect(flowchart, step, loop, "next")
    loop.parameters["parallel"].value = parallel
    loop.parameters["type"].value = kind
    return flowchart, step


@pytest.mark.parametrize("parallel", ["no", "yes"])
def test_a_fixed_seed_in_a_loop(parallel):
    flowchart, step = seeded("12345", parallel)
    (problem,) = validate(flowchart, warnings=True)
    assert "fixed random seed 12345" in problem
    problem.fixes[0].apply()
    assert step.parameters["seed"].value == "random"
    assert validate(flowchart, warnings=True) == []


@pytest.mark.parametrize(
    "seed, kind",
    [("random", "For"), ("$seed", "For"), ("12345", "For systems in the database")],
)
def test_no_seed_warning(seed, kind):
    flowchart, step = seeded(seed, kind=kind)
    assert validate(flowchart, warnings=True) == []


def test_engine_step_in_separate_iterations_is_warned():
    """A step that runs an MDI engine in the iteration gets only the iteration's
    small allocation when its calculations run as separate tasks (Paul,
    2026-10-30), so the check warns and offers 'inline'."""
    flowchart = seamm.Flowchart()
    loop = loop_step.Loop(flowchart=flowchart)
    flowchart.add_node(loop)
    _connect(flowchart, flowchart.get_node("1"), loop, "next")
    body = seamm.Node(flowchart=flowchart, title="Thermo", extension="Thermochemistry")
    flowchart.add_node(body)
    _connect(flowchart, loop, body, "loop")
    _connect(flowchart, body, loop, "next")
    loop.parameters["parallel"].value = "yes"
    loop.parameters["placement"].value = "separate tasks"
    problems = [p for p in validate(flowchart, warnings=True) if "MDI engine" in p]
    assert len(problems) == 1 and problems[0].severity == "warning"
    assert problems[0].fixes[0].edits[0].value == "inline"
    loop.parameters["placement"].value = "inline"
    assert not [p for p in validate(flowchart, warnings=True) if "MDI engine" in p]
