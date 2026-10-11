"""Rules: the types a rule works with, and a toy rule showing what they can express."""

import dataclasses

import pandas as pd
import pytest

from rules import Action, SignalValues, State

DAY = pd.Timestamp("2025-04-24")


# ---- SignalValues ------------------------------------------------------------------------------
def test_signal_values_are_read_as_attributes():
    signals = SignalValues({"dip": True, "overbought": False})
    assert signals.dip is True
    assert signals.overbought is False


def test_signal_values_may_hold_numbers_as_well_as_booleans():
    assert SignalValues({"rsi": 28.5}).rsi == 28.5  # room for numeric indicators later


def test_asking_for_a_signal_that_does_not_exist_names_the_ones_that_do():
    signals = SignalValues({"dip": True, "overbought": False})
    with pytest.raises(AttributeError, match=r"no signal named 'rsi_up'.*\['dip', 'overbought'\]"):
        _ = signals.rsi_up


def test_signal_values_cannot_be_changed_by_a_rule():
    signals = SignalValues({"dip": True})
    with pytest.raises(AttributeError, match="read-only"):
        signals.dip = False
    with pytest.raises(AttributeError, match="read-only"):
        del signals.dip


def test_true_names_lists_only_the_signals_that_are_on_in_the_order_given():
    signals = SignalValues({"crash": True, "vix_fading": False, "rsi_up": True})
    assert signals.true_names() == ["crash", "rsi_up"]
    assert signals.names == ["crash", "vix_fading", "rsi_up"]


# ---- State --------------------------------------------------------------------------------------
def test_a_new_state_is_flat_and_has_never_sold():
    state = State()
    assert state.flat and not state.holding
    assert state.days_since_sale is None


def test_a_buy_filling_starts_the_holding_clock_at_zero():
    state = State().bought(DAY)
    assert state.holding and not state.flat
    assert (state.days_held, state.entry_day) == (0, DAY)


def test_each_trading_day_while_holding_adds_one_to_days_held():
    state = State().bought(DAY).advance().advance().advance()
    assert state.days_held == 3
    assert state.entry_day == DAY  # the entry day does not move


def test_a_sale_ends_the_position_and_starts_the_cooldown_clock():
    state = State().bought(DAY).advance().sold()
    assert state.flat and state.entry_day is None
    assert state.days_since_sale == 0


def test_days_since_sale_counts_up_only_after_a_sale():
    never_sold = State().advance().advance()
    assert never_sold.days_since_sale is None  # still no sale, so nothing to count
    after_sale = State().bought(DAY).sold().advance().advance()
    assert after_sale.days_since_sale == 2


def test_a_strategy_that_has_never_sold_is_not_in_a_cooldown():
    assert State().cooled_down(21)  # free to make its first buy


def test_cooldown_ends_once_enough_days_have_passed_since_the_sale():
    state = State().bought(DAY).sold()
    assert not state.cooled_down(21)  # sold today
    for _ in range(20):
        state = state.advance()
    assert not state.cooled_down(21)  # 20 days after the sale
    assert state.advance().cooled_down(21)  # 21 days after the sale


def test_a_state_cannot_be_modified_only_replaced():
    state = State()
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.holding = True


def test_advancing_never_changes_the_state_it_was_called_on():
    state = State().bought(DAY)
    state.advance()
    assert state.days_held == 0


# ---- Action -------------------------------------------------------------------------------------
def test_there_are_exactly_three_actions():
    assert {action.name for action in Action} == {"BUY", "SELL", "HOLD"}


# ---- a toy rule: shows the types are enough to express "signals + state -> decision" ------------
def toy_rule(signals: SignalValues, state: State, params: dict) -> Action:
    """Buy when a dip and a bounce agree (and we are not overbought, and not in a cooldown).
    Sell once overbought, but only after the minimum hold."""
    if state.flat:
        wants_in = signals.dip and signals.bounce and not signals.overbought
        if wants_in and state.cooled_down(params["cooldown_days"]):
            return Action.BUY
        return Action.HOLD
    if state.days_held >= params["min_hold_days"] and signals.overbought:
        return Action.SELL
    return Action.HOLD


PARAMS = {"cooldown_days": 21, "min_hold_days": 252}
HELD_100_DAYS = State().bought(DAY)
for _ in range(100):
    HELD_100_DAYS = HELD_100_DAYS.advance()
HELD_300_DAYS = State().bought(DAY)
for _ in range(300):
    HELD_300_DAYS = HELD_300_DAYS.advance()
SOLD_5_DAYS_AGO = State().bought(DAY).sold()
for _ in range(5):
    SOLD_5_DAYS_AGO = SOLD_5_DAYS_AGO.advance()

DIP_AND_BOUNCE = {"dip": True, "bounce": True, "overbought": False}


@pytest.mark.parametrize(
    ("signals", "state", "expected"),
    [
        pytest.param(DIP_AND_BOUNCE, State(), Action.BUY, id="flat_and_dip_and_bounce_buys"),
        pytest.param(
            {"dip": True, "bounce": False, "overbought": False},
            State(),
            Action.HOLD,
            id="flat_and_only_the_dip_does_not_buy",
        ),
        pytest.param(
            {"dip": False, "bounce": True, "overbought": False},
            State(),
            Action.HOLD,
            id="flat_and_only_the_bounce_does_not_buy",
        ),
        pytest.param(
            {"dip": True, "bounce": True, "overbought": True},
            State(),
            Action.HOLD,
            id="flat_and_overbought_does_not_buy_even_if_the_others_agree",
        ),
        pytest.param(
            DIP_AND_BOUNCE, SOLD_5_DAYS_AGO, Action.HOLD, id="flat_but_sold_5_days_ago_waits"
        ),
        pytest.param(
            {"dip": False, "bounce": False, "overbought": True},
            HELD_100_DAYS,
            Action.HOLD,
            id="holding_100_days_and_overbought_keeps_holding_before_the_minimum_hold",
        ),
        pytest.param(
            {"dip": False, "bounce": False, "overbought": True},
            HELD_300_DAYS,
            Action.SELL,
            id="holding_300_days_and_overbought_sells",
        ),
        pytest.param(
            {"dip": False, "bounce": False, "overbought": False},
            HELD_300_DAYS,
            Action.HOLD,
            id="holding_300_days_and_not_overbought_keeps_holding",
        ),
    ],
)
def test_toy_rule_decisions(signals, state, expected):
    assert toy_rule(SignalValues(signals), state, PARAMS) == expected


def test_the_same_signal_means_different_things_depending_on_the_state():
    overbought = SignalValues({"dip": True, "bounce": True, "overbought": True})
    assert toy_rule(overbought, State(), PARAMS) == Action.HOLD  # flat: a reason not to buy
    assert toy_rule(overbought, HELD_300_DAYS, PARAMS) == Action.SELL  # holding: a reason to sell
