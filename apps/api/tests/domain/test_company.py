from app.domain.company import vat_number


def test_vat_number_is_computed_from_the_siren() -> None:
    assert vat_number("404833048") == "FR83404833048"  # published example
    assert vat_number("000000001") == "FR15000000001"  # key padded to two digits
