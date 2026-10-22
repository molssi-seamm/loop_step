#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `loop_step` package."""

import pytest  # noqa: F401
import loop_step  # noqa: F401


@pytest.fixture
def response():
    """Sample pytest fixture.

    See more at: http://doc.pytest.org/en/latest/fixture.html
    """
    # import requests
    # return requests.get('https://github.com/audreyr/cookiecutter-pypackage')


def test_content(response):
    """Sample pytest test function with the pytest fixture as an argument."""
    # from bs4 import BeautifulSoup
    # assert 'GitHub' in BeautifulSoup(response.content).title.string


def test_iteration_cores():
    """'automatic' shares the job's cores among the iterations that run at once;
    a number is used as given (SEAMM job 5368, 2026-10-22: 4 replicas ran on 4 of
    64 cores, one each, by default)."""
    from loop_step.loop import iteration_cores

    assert iteration_cores("automatic", 64, 4) == (16, 4)
    assert iteration_cores("automatic", 32, 4) == (8, 4)
    # limited by 'iterations at once' or by memory
    assert iteration_cores("automatic", 64, 8, at_once=2) == (32, 2)
    assert iteration_cores("automatic", 64, 8, job_memory=8e9, memory=2e9) == (16, 4)
    # more iterations than cores: one each
    assert iteration_cores("automatic", 4, 10) == (1, 10)
    assert iteration_cores(8, 64, 4) == (8, None)
    assert iteration_cores("3", 64, 4) == (3, None)


def test_resource_parameters_are_marked():
    """How the iterations run, not what they compute: a resume survives changing
    them (seamm's checkpoint fingerprint leaves them out)."""
    from loop_step import LoopParameters

    P = LoopParameters()
    for key in (
        "cores per iteration",
        "memory per iteration",
        "time per iteration",
        "iterations at once",
        "placement",
    ):
        assert P[key]._data.get("resource") is True, key
    assert P["cores per iteration"].default == "automatic"
    # Its default until 2026.10.22, for checkpoints written then
    assert P["cores per iteration"]._data.get("former defaults") == ("1",)
