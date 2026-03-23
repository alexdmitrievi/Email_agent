"""Tests that all example configs load and validate correctly."""

import glob
import os

import pytest

from app.config_loader import load_business_config

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "configs", "examples")
EXAMPLE_CONFIGS = sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.yaml")))


@pytest.mark.parametrize("config_path", EXAMPLE_CONFIGS, ids=lambda p: os.path.basename(p))
def test_example_config_loads(config_path):
    """Every example config must load and validate without errors."""
    config = load_business_config(config_path)
    assert config.business.name
    assert config.business.niche
    assert len(config.funnel.stages) >= 4
    assert len(config.funnel.transitions) >= 6


@pytest.mark.parametrize("config_path", EXAMPLE_CONFIGS, ids=lambda p: os.path.basename(p))
def test_example_config_has_stage_instructions(config_path):
    """Every non-terminal stage should have an instruction."""
    config = load_business_config(config_path)
    terminal = {"NOT_INTERESTED", "ARCHIVED", "ORDER"}
    for s in config.funnel.stages:
        if s.id not in terminal:
            assert s.id in config.stage_instructions, f"Missing instruction for {s.id} in {config_path}"


@pytest.mark.parametrize("config_path", EXAMPLE_CONFIGS, ids=lambda p: os.path.basename(p))
def test_example_config_has_handoff_keywords(config_path):
    """Every config should have at least 3 handoff keywords."""
    config = load_business_config(config_path)
    assert len(config.handoff.telegram_keywords) >= 3


@pytest.mark.parametrize("config_path", EXAMPLE_CONFIGS, ids=lambda p: os.path.basename(p))
def test_example_config_has_products(config_path):
    """Every config should have a product summary and at least one detail."""
    config = load_business_config(config_path)
    assert config.products.summary
    assert len(config.products.details) >= 1
