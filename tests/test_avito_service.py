"""Tests for Avito integration — config, pipeline, actions, service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ---- Config tests ----

def test_avito_funnel_config_loads():
    """avito_worker_funnel.yaml must load and validate."""
    from app.config_loader import load_business_config
    config = load_business_config("configs/avito_worker_funnel.yaml")
    assert config.business.niche == "worker_recruitment"
    assert len(config.funnel.stages) >= 5


def test_avito_funnel_has_worker_stages():
    from app.config_loader import load_business_config
    config = load_business_config("configs/avito_worker_funnel.yaml")
    stage_ids = [s.id for s in config.funnel.stages]
    assert "NEW_MESSAGE" in stage_ids
    assert "QUALIFIED" in stage_ids
    assert "LINK_SENT" in stage_ids
    assert "REGISTERED" in stage_ids


def test_avito_funnel_has_stage_instructions():
    from app.config_loader import load_business_config
    config = load_business_config("configs/avito_worker_funnel.yaml")
    assert "NEW_MESSAGE" in config.stage_instructions
    assert "QUALIFIED" in config.stage_instructions
    assert "LINK_SENT" in config.stage_instructions


def test_avito_funnel_transitions():
    from app.config_loader import load_business_config
    config = load_business_config("configs/avito_worker_funnel.yaml")
    assert len(config.funnel.transitions) >= 10


# ---- Pipeline tests ----

def test_avito_pipeline_loads():
    from app.funnel.avito_pipeline import get_avito_transition
    with patch("app.funnel.avito_pipeline.settings") as mock_settings:
        mock_settings.AVITO_ENABLED = True
        mock_settings.AVITO_FUNNEL_CONFIG_PATH = "configs/avito_worker_funnel.yaml"
        from app.funnel.avito_pipeline import load_avito_config
        load_avito_config()
        stage, action = get_avito_transition("NEW_MESSAGE", "INTERESTED")
        assert stage == "QUALIFIED"
        assert action == "reply_with_interest"


def test_avito_pipeline_qualified_to_link_sent():
    from app.funnel.avito_pipeline import get_avito_transition
    with patch("app.funnel.avito_pipeline.settings") as mock_settings:
        mock_settings.AVITO_ENABLED = True
        mock_settings.AVITO_FUNNEL_CONFIG_PATH = "configs/avito_worker_funnel.yaml"
        from app.funnel.avito_pipeline import load_avito_config
        load_avito_config()
        stage, action = get_avito_transition("QUALIFIED", "INTERESTED")
        assert stage == "LINK_SENT"
        assert action == "send_materials"


def test_avito_terminal_stages():
    from app.funnel.avito_pipeline import is_terminal
    assert is_terminal("REGISTERED")
    assert is_terminal("NOT_INTERESTED")
    assert is_terminal("ARCHIVED")
    assert not is_terminal("NEW_MESSAGE")
    assert not is_terminal("QUALIFIED")


# ---- Action map tests ----

def test_avito_action_map_has_required_actions():
    from app.funnel.avito_actions import AVITO_ACTION_MAP
    required = ["reply_with_interest", "send_materials", "continue_discussion",
                 "handoff_to_manager", "reply_not_interested", "ignore"]
    for action_name in required:
        assert action_name in AVITO_ACTION_MAP, f"Missing action: {action_name}"


# ---- Service tests ----

@pytest.mark.asyncio
async def test_avito_send_message():
    """send_message should POST to correct endpoint."""
    with patch("app.services.avito_service._ensure_token", new_callable=AsyncMock, return_value="test-token"):
        with patch("app.services.avito_service.httpx.AsyncClient") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "msg123"}
            mock_resp.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            from app.services.avito_service import send_message
            result = await send_message("chat123", "Hello!")
            assert result["id"] == "msg123"


# ---- Config override in AI agent ----

def test_config_override_in_render():
    """_render should use config_override when provided."""
    from app.config_loader import load_business_config
    from app.services.ai_agent import _render

    alt_config = load_business_config("configs/avito_worker_funnel.yaml")
    prompt = _render("system_prompt.j2", config_override=alt_config)
    assert "ПодрядPRO" in prompt


# ---- New niche configs validation ----

def test_podryadpro_config_loads():
    from app.config_loader import load_business_config
    config = load_business_config("configs/business.yaml")
    assert "Подряд" in config.business.name
    assert config.business.niche == "personnel_and_equipment"


def test_equipment_rental_config_loads():
    from app.config_loader import load_business_config
    config = load_business_config("configs/examples/equipment_rental.yaml")
    assert config.business.niche == "equipment_rental"
    stage_ids = [s.id for s in config.funnel.stages]
    assert "CATALOG_SENT" in stage_ids


def test_personnel_outsourcing_config_loads():
    from app.config_loader import load_business_config
    config = load_business_config("configs/examples/personnel_outsourcing.yaml")
    assert config.business.niche == "personnel_outsourcing"
    stage_ids = [s.id for s in config.funnel.stages]
    assert "CASE_STUDY_SENT" in stage_ids
