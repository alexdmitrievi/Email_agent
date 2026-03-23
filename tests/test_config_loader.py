"""Tests for business config loading and validation."""

import os
import tempfile

import pytest
import yaml

from app.config_loader import BusinessConfig, load_business_config

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_business.yaml")


# ---- Loading & basic validation ----


def test_load_valid_config():
    config = load_business_config(FIXTURE_PATH)
    assert config.business.name == "Test Company"
    assert config.business.niche == "test"
    assert config.business.language == "ru"


def test_config_has_products():
    config = load_business_config(FIXTURE_PATH)
    assert config.products.summary
    assert len(config.products.details) >= 1
    assert config.products.details[0].name == "Product A"


def test_config_has_stages():
    config = load_business_config(FIXTURE_PATH)
    assert len(config.funnel.stages) >= 4
    stage_ids = [s.id for s in config.funnel.stages]
    assert "NEW_REPLY" in stage_ids
    assert "INTERESTED" in stage_ids
    assert "MATERIALS_SENT" in stage_ids


def test_config_has_categories():
    config = load_business_config(FIXTURE_PATH)
    assert len(config.funnel.categories) >= 4
    cat_ids = [c.id for c in config.funnel.categories]
    assert "INTERESTED" in cat_ids
    assert "NOT_INTERESTED" in cat_ids


def test_config_has_transitions():
    config = load_business_config(FIXTURE_PATH)
    assert len(config.funnel.transitions) >= 10


def test_config_has_stage_instructions():
    config = load_business_config(FIXTURE_PATH)
    assert "NEW_REPLY" in config.stage_instructions
    assert "INTERESTED" in config.stage_instructions


def test_config_has_handoff_keywords():
    config = load_business_config(FIXTURE_PATH)
    assert len(config.handoff.telegram_keywords) >= 3


def test_config_has_tone():
    config = load_business_config(FIXTURE_PATH)
    assert config.tone.max_sentences_email == 5
    assert config.tone.max_sentences_telegram == 3


def test_config_has_follow_ups():
    config = load_business_config(FIXTURE_PATH)
    assert config.follow_ups.delay_days == 3
    assert config.follow_ups.max_count == 2


def test_config_has_telegram():
    config = load_business_config(FIXTURE_PATH)
    assert "{first_name}" in config.telegram.welcome_message
    assert "{company_name}" in config.telegram.welcome_message


def test_config_not_interested_reply():
    config = load_business_config(FIXTURE_PATH)
    assert len(config.not_interested_reply) > 0


# ---- Validation errors ----


def _write_yaml(data: dict) -> str:
    """Write a dict to a temp YAML file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)
    return path


def _base_config() -> dict:
    """Return a minimal valid config dict."""
    return {
        "business": {"name": "X", "niche": "x", "description": "x"},
        "products": {"summary": "x"},
        "funnel": {
            "stages": [
                {"id": "NEW_REPLY", "label": "New"},
                {"id": "DONE", "label": "Done"},
            ],
            "categories": [{"id": "INTERESTED", "description": "x"}],
            "transitions": [
                {"from": "NEW_REPLY", "on": "INTERESTED", "to": "DONE", "action": "reply"},
            ],
        },
    }


def test_missing_business_name():
    data = _base_config()
    del data["business"]["name"]
    path = _write_yaml(data)
    with pytest.raises(Exception):
        load_business_config(path)
    os.unlink(path)


def test_missing_funnel():
    data = _base_config()
    del data["funnel"]
    path = _write_yaml(data)
    with pytest.raises(Exception):
        load_business_config(path)
    os.unlink(path)


def test_transition_references_unknown_stage():
    data = _base_config()
    data["funnel"]["transitions"] = [
        {"from": "NONEXISTENT", "on": "INTERESTED", "to": "DONE", "action": "x"},
    ]
    path = _write_yaml(data)
    with pytest.raises(Exception, match="unknown stage"):
        load_business_config(path)
    os.unlink(path)


def test_transition_references_unknown_category():
    data = _base_config()
    data["funnel"]["transitions"] = [
        {"from": "NEW_REPLY", "on": "FAKE_CATEGORY", "to": "DONE", "action": "x"},
    ]
    path = _write_yaml(data)
    with pytest.raises(Exception, match="unknown category"):
        load_business_config(path)
    os.unlink(path)


def test_follow_up_stages_reference_valid():
    config = load_business_config(FIXTURE_PATH)
    stage_ids = {s.id for s in config.funnel.stages}
    for stage_id in config.funnel.follow_up_eligible_stages:
        assert stage_id in stage_ids


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_business_config("/nonexistent/path.yaml")


def test_stage_attachment_field():
    config = load_business_config(FIXTURE_PATH)
    materials_stage = next(s for s in config.funnel.stages if s.id == "MATERIALS_SENT")
    assert materials_stage.attachment == "assets/test.pdf"


def test_calendar_config():
    config = load_business_config(FIXTURE_PATH)
    assert config.calendar.enabled is False
