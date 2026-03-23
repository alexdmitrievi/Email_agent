"""Tests that different niche configs produce different behavior."""

import os

import pytest

from app.config_loader import load_business_config
from app.services.ai_agent import _render

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "configs", "examples")


def _load_example(name: str):
    return load_business_config(os.path.join(EXAMPLES_DIR, name))


def test_furniture_config_has_materials_stage():
    config = _load_example("furniture_ru.yaml")
    stage_ids = [s.id for s in config.funnel.stages]
    assert "MATERIALS_SENT" in stage_ids


def test_construction_config_has_kp_and_estimate_stages():
    config = _load_example("construction_ru.yaml")
    stage_ids = [s.id for s in config.funnel.stages]
    assert "KP_SENT" in stage_ids
    assert "ESTIMATE_SCHEDULED" in stage_ids


def test_consulting_config_has_case_study_and_demo_stages():
    config = _load_example("consulting_ru.yaml")
    stage_ids = [s.id for s in config.funnel.stages]
    assert "CASE_STUDY_SENT" in stage_ids
    assert "DEMO_SCHEDULED" in stage_ids


def test_different_configs_have_different_names():
    furniture = _load_example("furniture_ru.yaml")
    construction = _load_example("construction_ru.yaml")
    consulting = _load_example("consulting_ru.yaml")
    names = {furniture.business.name, construction.business.name, consulting.business.name}
    assert len(names) == 3  # All different


def test_different_configs_have_different_niches():
    furniture = _load_example("furniture_ru.yaml")
    construction = _load_example("construction_ru.yaml")
    consulting = _load_example("consulting_ru.yaml")
    niches = {furniture.business.niche, construction.business.niche, consulting.business.niche}
    assert len(niches) == 3


def test_system_prompt_differs_by_niche():
    """Loading different configs should produce different system prompts."""
    import app.config_loader as cl

    furniture = _load_example("furniture_ru.yaml")
    cl._config = furniture
    prompt_furniture = _render("system_prompt.j2")

    construction = _load_example("construction_ru.yaml")
    cl._config = construction
    prompt_construction = _render("system_prompt.j2")

    assert prompt_furniture != prompt_construction
    assert furniture.business.name in prompt_furniture
    assert construction.business.name in prompt_construction
