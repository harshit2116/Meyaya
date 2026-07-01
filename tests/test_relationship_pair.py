"""Tests for relationship pair normalization."""

from bot.models.relationship import normalize_pair


def test_normalize_pair_orders_ids() -> None:
    """The smaller user ID should always be stored first."""

    assert normalize_pair(9, 2) == (2, 9)
