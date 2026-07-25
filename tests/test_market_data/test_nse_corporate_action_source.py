"""The corporate-action subject parser (research/62 P3, §11.2). Hermetic tests
use the EXACT free-text `subject` forms NSE returns (captured from real nselib
rows), so the parser is verified against real strings without a network call.
"""

from datetime import date

import pytest

from nse_algo_trader.market_data.nse_corporate_action_source import (
    CorporateActionType,
    corporate_action_from_nselib_row,
    parse_corporate_action_subject,
)


@pytest.mark.parametrize(
    "subject, expected_type, expected_factor",
    [
        # Real NSE split subjects (10→2, 10→1).
        (
            "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
            CorporateActionType.SPLIT,
            0.2,
        ),
        (
            "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share",
            CorporateActionType.SPLIT,
            0.1,
        ),
        # Real NSE bonus subjects: X free per Y held → factor Y/(X+Y).
        ("Bonus 1:1", CorporateActionType.BONUS, 0.5),
        ("Bonus 1:3", CorporateActionType.BONUS, 0.75),
        ("Bonus 10:1", CorporateActionType.BONUS, 1 / 11),
        ("Bonus 5:1", CorporateActionType.BONUS, 1 / 6),
        # Non price-affecting actions → identity.
        ("Dividend - Rs 5 Per Share", CorporateActionType.OTHER, 1.0),
        ("Annual General Meeting", CorporateActionType.OTHER, 1.0),
    ],
)
def test_parse_real_subject_forms(subject, expected_type, expected_factor):
    action_type, factor = parse_corporate_action_subject(subject)
    assert action_type is expected_type
    assert factor == pytest.approx(expected_factor)


def test_row_parsing_from_a_real_nselib_record_shape():
    row = {
        "symbol": "KRISHANA",
        "exDate": "03-Jul-2026",
        "subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
        "faceVal": "2",
        "series": "EQ",
    }
    action = corporate_action_from_nselib_row(row)
    assert action is not None
    assert action.symbol == "KRISHANA"
    assert action.ex_date == date(2026, 7, 3)
    assert action.action_type is CorporateActionType.SPLIT
    assert action.price_adjustment_factor == pytest.approx(0.2)


def test_row_with_unparseable_ex_date_is_dropped():
    assert corporate_action_from_nselib_row(
        {"symbol": "X", "exDate": "-", "subject": "Bonus 1:1"}
    ) is None
