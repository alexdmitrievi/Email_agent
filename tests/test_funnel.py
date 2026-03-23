"""Tests for funnel pipeline transitions."""

from app.funnel.pipeline import get_transition
from app.funnel.stages import ReplyCategory, Stage


def test_new_reply_interested():
    new_stage, action = get_transition(Stage.NEW_REPLY, ReplyCategory.INTERESTED)
    assert new_stage == Stage.INTERESTED
    assert action == "reply_with_interest"


def test_new_reply_not_interested():
    new_stage, action = get_transition(Stage.NEW_REPLY, ReplyCategory.NOT_INTERESTED)
    assert new_stage == Stage.NOT_INTERESTED
    assert action == "reply_not_interested"


def test_new_reply_spam():
    new_stage, action = get_transition(Stage.NEW_REPLY, ReplyCategory.SPAM)
    assert new_stage == Stage.ARCHIVED
    assert action == "ignore"


def test_new_reply_out_of_office():
    new_stage, action = get_transition(Stage.NEW_REPLY, ReplyCategory.OUT_OF_OFFICE)
    assert new_stage == Stage.NEW_REPLY
    assert action == "ignore"


def test_new_reply_ready_to_order():
    new_stage, action = get_transition(Stage.NEW_REPLY, ReplyCategory.READY_TO_ORDER)
    assert new_stage == Stage.HANDOFF_TO_MANAGER
    assert action == "handoff_to_manager"


def test_interested_to_portfolio():
    new_stage, action = get_transition(Stage.INTERESTED, ReplyCategory.INTERESTED)
    assert new_stage == Stage.PORTFOLIO_SENT
    assert action == "send_portfolio"


def test_portfolio_sent_to_discussion():
    new_stage, action = get_transition(Stage.PORTFOLIO_SENT, ReplyCategory.INTERESTED)
    assert new_stage == Stage.IN_DISCUSSION
    assert action == "continue_discussion"


def test_in_discussion_continues():
    new_stage, action = get_transition(Stage.IN_DISCUSSION, ReplyCategory.QUESTION)
    assert new_stage == Stage.IN_DISCUSSION
    assert action == "continue_discussion"


def test_any_stage_ready_to_order():
    for stage in [Stage.INTERESTED, Stage.PORTFOLIO_SENT, Stage.IN_DISCUSSION]:
        new_stage, action = get_transition(stage, ReplyCategory.READY_TO_ORDER)
        assert new_stage == Stage.HANDOFF_TO_MANAGER
        assert action == "handoff_to_manager"


def test_unknown_transition_defaults():
    new_stage, action = get_transition("UNKNOWN_STAGE", "UNKNOWN_CATEGORY")
    assert action == "continue_discussion"
