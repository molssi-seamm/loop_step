# -*- coding: utf-8 -*-

"""The loop over systems uses SEAMM's standard structure selection, and reads
flowcharts saved with the old option names."""

import loop_step
import seamm


def _legacy(where="is anything", system_name="", default="last", conf_name=""):
    return {
        "type": {"value": "For systems in the database", "units": None},
        "where system name": {"value": where, "units": None},
        "system name": {"value": system_name, "units": None},
        "default configuration": {"value": default, "units": None},
        "configuration name": {"value": conf_name, "units": None},
    }


def test_defaults_loop_over_every_system_last_configuration():
    P = loop_step.LoopParameters()
    assert P["source systems"].value == "all"
    assert P["source configurations"].value == "last"
    for key in seamm.standard_parameters.structure_selection_parameters:
        assert key in P
    for key in ("where system name", "default configuration"):
        assert key not in P


def test_legacy_keys_and_values_are_translated():
    P = loop_step.LoopParameters()
    P.from_dict(_legacy())
    assert P["source systems"].value == "all"
    assert P["source configurations"].value == "last"

    P.from_dict(
        _legacy(where="is", system_name="water", default="name is", conf_name="x")
    )
    assert P["source systems"].value == "name is"
    assert P["source system name"].value == "water"
    assert P["source configurations"].value == "name is"
    assert P["source configuration name"].value == "x"

    P.from_dict(_legacy(where="matches", system_name="H2O*", default="-1"))
    assert P["source systems"].value == "name matches"
    assert P["source configurations"].value == "last"

    P.from_dict(_legacy(where="regexp", system_name="^w", default="1"))
    assert P["source systems"].value == "name regexp"
    assert P["source configurations"].value == "first"

    P.from_dict(_legacy(default="name matches", conf_name="frame*"))
    assert P["source configurations"].value == "name matches"


def test_new_keys_pass_through():
    P = loop_step.LoopParameters()
    P.from_dict(
        {
            "source systems": {"value": "current", "units": None},
            "source configurations": {"value": "all", "units": None},
        }
    )
    assert P["source systems"].value == "current"
    assert P["source configurations"].value == "all"
    text = seamm.standard_parameters.structure_selection_description(
        P.current_values_to_dict()
    )
    assert text == "All configurations of the current system will be used."
