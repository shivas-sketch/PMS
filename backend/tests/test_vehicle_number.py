import pytest

from app.utils.vehicle_number import clean_vehicle_number, normalize_vehicle_number


@pytest.mark.parametrize(
    "raw",
    [
        "TS 09 AB 1234",
        "TS-09-AB-1234",
        "ts09ab1234",
        "TSO9ABI234",  # O->0, I->1 position-aware corrections
    ],
)
def test_normalize_known_examples(raw):
    result = normalize_vehicle_number(raw)
    assert result.normalized == "TS09AB1234"
    assert result.is_valid_format is True


def test_normalize_does_not_globally_replace_letters_in_letter_segments():
    # 'O' inside a letter segment must stay a letter, not be rewritten to 0.
    # Neither "KO" nor "KD" are valid state codes, so the original is kept.
    result = normalize_vehicle_number("KO12CD3456")
    assert result.normalized == "KO12CD3456"
    assert result.is_valid_format is True


def test_normalize_garbage_input_falls_back_to_cleaned_string():
    result = normalize_vehicle_number("12345")
    assert result.normalized == "12345"
    assert result.is_valid_format is False


def test_normalize_empty_input():
    result = normalize_vehicle_number("")
    assert result.normalized == ""
    assert result.is_valid_format is False

    result_none = normalize_vehicle_number(None)
    assert result_none.normalized == ""
    assert result_none.is_valid_format is False


def test_normalize_o_to_d_in_letter_segments():
    # OCR reads "D" as "O" — should correct back to D in letter segments.
    result = normalize_vehicle_number("KA01OB1234")
    assert result.normalized == "KA01DB1234"
    assert result.is_valid_format is True


def test_normalize_o_to_d_in_state_code():
    # OCR reads state "OD" (Odisha) as "OO" — should correct to "OD".
    result = normalize_vehicle_number("OO01AB1234")
    assert result.normalized == "OD01AB1234"
    assert result.is_valid_format is True


def test_normalize_zero_to_d_in_letter_segments():
    # OCR reads "D" as "0" (zero) — should correct to D in letter segments.
    result = normalize_vehicle_number("MH010X3699")
    assert result.normalized == "MH01DX3699"
    assert result.is_valid_format is True


def test_normalize_i_to_t_in_state_code():
    # OCR reads "T" as "I" — should correct to T in state code (TN, not IN).
    result = normalize_vehicle_number("IN59AQ1515")
    assert result.normalized == "TN59AQ1515"
    assert result.is_valid_format is True


def test_clean_vehicle_number_does_not_apply_ocr_corrections():
    assert clean_vehicle_number("ts 09-ab-1234") == "TS09AB1234"
    # No character-substitution correction for manual input, only cleanup.
    assert clean_vehicle_number("TSO9ABI234") == "TSO9ABI234"
