"""Tests for config-driven funnel pipeline transitions."""

from app.funnel.pipeline import get_transition
from app.funnel.stages import get_stage_ids, get_category_ids, is_terminal, get_stage_attachment


# ---- Stage/category helpers ----


def test_stages_loaded():
    ids = get_stage_ids()
    assert "NEW_REPLY" in ids
    assert "INTERESTED" in ids
    assert "MATERIALS_SENT" in ids
    assert "IN_DISCUSSION" in ids
    assert "HANDOFF_TO_MANAGER" in ids


def test_categories_loaded():
    ids = get_category_ids()
    assert "INTERESTED" in ids
    assert "NOT_INTERESTED" in ids
    assert "SPAM" in ids
    assert "READY_TO_ORDER" in ids


def test_terminal_stages():
    assert is_terminal("HANDOFF_TO_MANAGER")
    assert is_terminal("ORDER")
    assert is_terminal("NOT_INTERESTED")
    assert is_terminal("ARCHIVED")
    assert not is_terminal("NEW_REPLY")
    assert not is_terminal("IN_DISCUSSION")


def test_stage_attachment():
    assert get_stage_attachment("MATERIALS_SENT") == "assets/test.pdf"
    assert get_stage_attachment("NEW_REPLY") is None


# ---- Transitions ----


def test_new_reply_interested():
    new_stage, action = get_transition("NEW_REPLY", "INTERESTED")
    assert new_stage == "INTERESTED"
    assert action == "reply_with_interest"


def test_new_reply_not_interested():
    new_stage, action = get_transition("NEW_REPLY", "NOT_INTERESTED")
    assert new_stage == "NOT_INTERESTED"
    assert action == "reply_not_interested"


def test_new_reply_spam():
    new_stage, action = get_transition("NEW_REPLY", "SPAM")
    assert new_stage == "ARCHIVED"
    assert action == "ignore"


def test_new_reply_out_of_office():
    new_stage, action = get_transition("NEW_REPLY", "OUT_OF_OFFICE")
    assert new_stage == "NEW_REPLY"
    assert action == "ignore"


def test_new_reply_ready_to_order():
    new_stage, action = get_transition("NEW_REPLY", "READY_TO_ORDER")
    assert new_stage == "HANDOFF_TO_MANAGER"
    assert action == "handoff_to_manager"


def test_interested_to_materials():
    new_stage, action = get_transition("INTERESTED", "INTERESTED")
    assert new_stage == "MATERIALS_SENT"
    assert action == "send_materials"


def test_materials_sent_to_discussion():
    new_stage, action = get_transition("MATERIALS_SENT", "INTERESTED")
    assert new_stage == "IN_DISCUSSION"
    assert action == "continue_discussion"


def test_in_discussion_continues():
    new_stage, action = get_transition("IN_DISCUSSION", "QUESTION")
    assert new_stage == "IN_DISCUSSION"
    assert action == "continue_discussion"


def test_any_stage_ready_to_order():
    for stage in ["INTERESTED", "MATERIALS_SENT", "IN_DISCUSSION"]:
        new_stage, action = get_transition(stage, "READY_TO_ORDER")
        assert new_stage == "HANDOFF_TO_MANAGER"
        assert action == "handoff_to_manager"


def test_unknown_transition_defaults():
    new_stage, action = get_transition("UNKNOWN_STAGE", "UNKNOWN_CATEGORY")
    assert action == "continue_discussion"
