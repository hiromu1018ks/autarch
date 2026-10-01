import pytest

from pricing import tier_price


@pytest.mark.parametrize("seat_count,expected", [(1, 10), (5, 50)])
def test_tier_price(seat_count, expected):
    assert tier_price(seat_count) == expected
