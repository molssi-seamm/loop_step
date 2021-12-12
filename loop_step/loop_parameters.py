# -*- coding: utf-8 -*-
"""Control parameters for loops
"""

import logging
import seamm

logger = logging.getLogger(__name__)


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
    }

    def __init__(self, defaults={}, data=None):
        """Initialize the instance, by default from the default
        parameters given in the class"""

        super().__init__(defaults={**LoopParameters.parameters, **defaults}, data=data)
