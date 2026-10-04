# -*- coding: utf-8 -*-

"""Smoke test of the Tk dialog: create it and re-lay it out for every choice
that drives the layout. Skipped when no display is available."""

import pytest

from loop_step.tk_loop import PARALLEL_PARAMETERS


@pytest.fixture()
def tk_node():
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    root.withdraw()
    import Pmw
    import seamm

    Pmw.initialise(root)
    flowchart = seamm.Flowchart(namespace="org.molssi.seamm", directory=".")
    tk_flowchart = seamm.TkFlowchart(
        master=root, flowchart=flowchart, namespace="org.molssi.seamm.tk"
    )
    node = flowchart.create_node("Loop")
    flowchart.add_node(node)
    plugin = tk_flowchart.plugin_manager.get("Loop")
    tk_node = plugin.create_tk_node(
        tk_flowchart=tk_flowchart, node=node, canvas=tk_flowchart.canvas, x=100, y=100
    )
    yield tk_node
    root.destroy()


def test_dialog_layouts(tk_node):
    tk_node.create_dialog()
    tk_node.reset_dialog()
    for loop_type in (
        "Foreach",
        "For rows in table",
        "For systems in the database",
        "For",
    ):
        tk_node["type"].set(loop_type)
        for parallel in ("yes", "no"):
            tk_node["parallel"].set(parallel)
            tk_node.reset_dialog()
            shown = [tk_node[k].grid_info() != {} for k in PARALLEL_PARAMETERS]
            assert tk_node["parallel"].grid_info() != {}
            if parallel == "yes":
                assert all(shown), loop_type
            else:
                assert not any(shown), loop_type
    tk_node["type"].set("For rows in table")
    for where in ("Use all rows", "Select rows where column"):
        tk_node["where"].set(where)
        tk_node.reset_dialog()
