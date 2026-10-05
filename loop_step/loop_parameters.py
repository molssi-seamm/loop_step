# -*- coding: utf-8 -*-
"""Control parameters for loops"""

import logging
import seamm

logger = logging.getLogger(__name__)


# Legacy (pre-2026.9.18) names and values for the system selection, translated on
# loading an old flowchart to the standard SEAMM structure-selection parameters.
_legacy_keys = {
    "where system name": "source systems",
    "system name": "source system name",
    "default configuration": "source configurations",
    "configuration name": "source configuration name",
}
_legacy_values = {
    "source systems": {
        "is anything": "all",
        "is": "name is",
        "matches": "name matches",
        "regexp": "name regexp",
    },
    "source configurations": {"-1": "last", "1": "first"},
}

_selection_parameters = {
    key: dict(value)
    for key, value in seamm.standard_parameters.structure_selection_parameters.items()
}
_selection_parameters["source systems"]["default"] = "all"
_selection_parameters["source systems"]["description"] = "For systems:"
_selection_parameters["source configurations"]["default"] = "last"
_selection_parameters["source configurations"]["description"] = "using configuration:"


class LoopParameters(seamm.Parameters):
    """The control parameters for loops"""

    parameters = {
        "type": {
            "default": "For",
            "kind": "enumeration",
            "default_units": "",
            "enumeration": (
                "For",
                "Foreach",
                "For rows in table",
                "For systems in the database",
            ),
            "format_string": "s",
            "description": "",
            "help_text": ("The type of loop used."),
        },
        "variable": {
            "default": "i",
            "kind": "string",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "",
            "description": "loop variable",
            "help_text": ("The name of the loop variable."),
        },
        "start": {
            "default": "1",
            "kind": "float",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "",
            "description": "from",
            "help_text": ("The starting value of the loop."),
        },
        "end": {
            "default": "10",
            "kind": "float",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "",
            "description": "to",
            "help_text": ("The ending value of the loop."),
        },
        "step": {
            "default": "1",
            "kind": "float",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "",
            "description": "by",
            "help_text": ("The step or increment of the loop value."),
        },
        "values": {
            "default": "",
            "kind": "string",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "s",
            "description": "value in",
            "help_text": ("The list of values for the loop."),
        },
        "table": {
            "default": "table1",
            "kind": "string",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "s",
            "description": "",
            "help_text": ("The table to iterate over."),
        },
        "where": {
            "default": "Use all rows",
            "kind": "string",
            "default_units": "",
            "enumeration": ("Use all rows", "Select rows where column"),
            "format_string": "s",
            "description": "",
            "help_text": ("The filter for rows, defaults to all rows."),
        },
        "query-column": {
            "default": "",
            "kind": "string",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "s",
            "description": "",
            "help_text": ("The column to test"),
        },
        "query-op": {
            "default": "==",
            "kind": "string",
            "default_units": "",
            "enumeration": (
                "==",
                "!=",
                ">",
                ">=",
                "<",
                "<=",
                "between",
                "contains",
                "does not contain",
                "contains regexp",
                "does not contain regexp",
                "is empty",
                "is not empty",
            ),
            "format_string": "s",
            "description": "",
            "help_text": ("The column to test"),
        },
        "query-value": {
            "default": "",
            "kind": "string",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "s",
            "description": "",
            "help_text": ("Value to use in the test"),
        },
        "query-value2": {
            "default": "",
            "kind": "string",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "s",
            "description": "",
            "help_text": "The second value to use in the test",
        },
        "as variables": {
            "default": "yes",
            "kind": "boolean",
            "default_units": "",
            "enumeration": ("yes", "no"),
            "format_string": "",
            "description": "Values as variables:",
            "help_text": "Whether to put the values for the row as seperate variables.",
        },
        # The standard SEAMM structure selection, but looping over every system
        # and its last configuration by default, as this step always has.
        **_selection_parameters,
        "directory name": {
            "default": "loop iteration",
            "kind": "string",
            "default_units": "",
            "enumeration": (
                "loop iteration",
                "system name",
                "configuration name",
            ),
            "format_string": "s",
            "description": "Directory names:",
            "help_text": "The directory name for the loop iteration.",
        },
        "errors": {
            "default": "continue to next iteration",
            "kind": "string",
            "default_units": "",
            "enumeration": (
                "continue to next iteration",
                "exit the loop",
                "stop the job",
            ),
            "format_string": "s",
            "description": "On errors",
            "help_text": ("How to handle errors"),
        },
        # Parallel iterations (phase 6 of the parallel-execution campaign)
        "parallel": {
            "default": "no",
            "kind": "boolean",
            "default_units": "",
            "enumeration": ("no", "yes"),
            "format_string": "",
            "description": "Run iterations in parallel:",
            "help_text": (
                "Run the iterations at the same time, each in its own evaluator. "
                "They must be independent: each sees the job as it was when the "
                "loop started, and variables set in the body are not visible "
                "after the loop. Tables, properties, structures and files come "
                "back, merged in iteration order."
            ),
        },
        "iterations at once": {
            "default": "as many as fit",
            "kind": "integer",
            "default_units": "",
            "enumeration": ("as many as fit",),
            "format_string": "",
            "description": "Iterations at once:",
            "help_text": (
                "How many iterations run at the same time on this machine. By "
                "default as many as the cores and memory allow, given the cores "
                "and memory per iteration."
            ),
        },
        "cores per iteration": {
            "default": 1,
            "kind": "integer",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "",
            "description": "Cores per iteration:",
            "help_text": "The cores each iteration uses for its calculations.",
        },
        "memory per iteration": {
            "default": 2.0,
            "kind": "float",
            "default_units": "GB",
            "enumeration": tuple(),
            "format_string": ".1f",
            "description": "Memory per iteration:",
            "help_text": "The memory each iteration needs at most.",
        },
        "time per iteration": {
            "default": "not given",
            "kind": "float",
            "default_units": "h",
            "enumeration": ("not given",),
            "format_string": ".2f",
            "description": "Time per iteration:",
            "help_text": (
                "An estimate of the time each iteration takes, used to bundle "
                "iterations into queue jobs."
            ),
        },
        "snapshot": {
            "default": "selected structures",
            "kind": "enumeration",
            "default_units": "",
            "enumeration": ("selected structures", "whole database"),
            "format_string": "s",
            "description": "Each iteration gets:",
            "help_text": (
                "What of the job's database each iteration starts with: the "
                "structure it works on (and the current one) with all the "
                "tables, or a copy of the whole database."
            ),
        },
        "placement": {
            "default": "inline",
            "kind": "enumeration",
            "default_units": "",
            "enumeration": ("inline", "separate tasks"),
            "format_string": "s",
            "description": "Calculations run:",
            "help_text": (
                "Where each iteration's calculations run: inline, in the "
                "iteration's own share of the machine, or as separate tasks on "
                "the job's target."
            ),
        },
        "same-cell writes": {
            "default": "are an error",
            "kind": "enumeration",
            "default_units": "",
            "enumeration": ("are an error", "the later iteration wins"),
            "format_string": "s",
            "description": "Two iterations writing one table cell:",
            "help_text": (
                "What to do when two iterations write the same cell of a table "
                "row that existed before the loop: stop with an error, or keep "
                "the value from the later iteration, with a warning."
            ),
        },
    }

    def __init__(self, defaults={}, data=None):
        """Initialize the instance, by default from the default
        parameters given in the class"""

        super().__init__(defaults={**LoopParameters.parameters, **defaults}, data=data)

    def update(self, data):
        """Update from a dictionary, translating the legacy system-selection keys
        ('where system name', 'system name', 'default configuration',
        'configuration name') and their values from flowcharts saved before
        2026.9.18 to the standard structure-selection parameters."""
        translated = {}
        for key, value in data.items():
            new_key = _legacy_keys.get(key, key)
            if new_key in _legacy_values and isinstance(value, dict):
                value = dict(value)
                value["value"] = _legacy_values[new_key].get(
                    str(value.get("value", "")).strip(), value.get("value")
                )
            translated[new_key] = value
        super().update(translated)
