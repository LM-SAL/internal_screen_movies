"""
Run with ``python test_display_movies.py`` or ``pytest``.
"""

from display_movies import balance


def test_balance_gives_roughly_equal_parts():
    movies = balance([["iris"] * 3, ["aia"] * 31])
    assert movies.count("iris") == 30
    assert movies.count("aia") == 31


if __name__ == "__main__":
    test_balance_gives_roughly_equal_parts()
