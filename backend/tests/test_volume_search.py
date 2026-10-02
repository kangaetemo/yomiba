"""'<series> <number>' search queries ("one piece 47")."""

import pytest

from app.services.catalog_service import split_volume_query


@pytest.mark.parametrize(
    "query, expected",
    [
        ("one piece 47", ("one piece", 47)),
        ("One Piece Cilt 47", ("One Piece", 47)),
        ("berserk #3", ("berserk", 3)),
        ("one piece", None),
        ("47", None),
        ("20th century boys", None),
    ],
)
def test_split_volume_query(query, expected):
    assert split_volume_query(query) == expected
