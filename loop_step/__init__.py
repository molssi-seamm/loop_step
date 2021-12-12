# -*- coding: utf-8 -*-

"""
loop_step
A step for loops in the SEAMM flowcharts
"""

# Bring up the classes so that they appear to be directly in
# the loop_step package.

from loop_step.loop import Loop  # noqa: F401
from loop_step.loop_parameters import LoopParameters  # noqa: F401
from loop_step.loop_step import LoopStep  # noqa: F401
from loop_step.tk_loop import TkLoop  # noqa: F401

# Handle versioneer
from ._version import get_versions

__author__ = """Paul Saxe"""
__email__ = "psaxe@molssi.org"
versions = get_versions()
__version__ = versions["version"]
__git_revision__ = versions["full-revisionid"]
del get_versions, versions
