import re


def parse_title(title: str) -> tuple[str, float | None]:
    """
    Berserk 17 -> ("Berserk", 17)
    One Piece 108 -> ("One Piece", 108)
    Vagabond -> ("Vagabond", None)
    """

    match = re.search(r"^(.*?)\s+(\d+(?:\.\d+)?)$", title.strip())

    if not match:
        return title.strip(), None

    series = match.group(1).strip()
    volume = float(match.group(2))

    return series, volume