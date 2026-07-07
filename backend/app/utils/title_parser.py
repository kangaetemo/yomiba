import re


def parse_title(title: str) -> tuple[str, float | None]:
    """
    Berserk 17 -> ("Berserk", 17)
    Berserk Cilt 17 -> ("Berserk", 17)
    Berserk Volume 17 -> ("Berserk", 17)
    Berserk Vol. 17 -> ("Berserk", 17)
    One Piece No. 108 -> ("One Piece", 108)
    Vagabond -> ("Vagabond", None)
    """

    title = title.strip()

    # Cilt / Volume / Vol / No gibi ifadeleri temizle
    clean_title = re.sub(
        r"\b(?:cilt|volume|vol\.?|no\.?)\b",
        "",
        title,
        flags=re.IGNORECASE,
    )

    # Fazla boşlukları temizle
    clean_title = re.sub(r"\s+", " ", clean_title).strip()

    match = re.search(
        r"^(.*?)\s+(\d+(?:\.\d+)?)$",
        clean_title,
    )

    if not match:
        return clean_title, None

    series = match.group(1).strip()
    volume = float(match.group(2))

    return series, volume