"""Tests du normaliseur de nombres francais parles."""

from reports.numbers import (
    digits_in,
    source_number_set,
    spelled_numbers_to_digits,
)


def test_units_and_teens():
    got = spelled_numbers_to_digits("cinq et dix-huit et quatre")
    assert {"5", "18", "4"} <= got


def test_tens_composites():
    got = spelled_numbers_to_digits("vingt-six trente-deux quatre-vingt-quatre")
    assert {"26", "32", "84"} <= got


def test_digits_extraction():
    assert digits_in("lesion de 18 mm, 26 ganglions") == ["18", "26"]


def test_source_set_combines_digits_and_words():
    src = "une carotte de cinq millimetres et 26 ganglions"
    numbers = source_number_set(src)
    assert "5" in numbers  # ecrit en lettres
    assert "26" in numbers  # ecrit en chiffres


def test_no_false_number_from_plain_words():
    # "adenocarcinome" ne doit pas produire de nombre
    assert spelled_numbers_to_digits("adenocarcinome infiltrant") == set()
