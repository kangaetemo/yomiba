import re


def normalize_publisher(name: str | None) -> str | None:
    if not name:
        return None

    key = re.sub(r"\s+", " ", name.strip().lower())

    replacements = {
        "athica yayınları": "Athica Yayınları",
        "athica yayinlari": "Athica Yayınları",

        "dark horse": "Dark Horse",
        "dark horse comics": "Dark Horse",
        "dark horse comics,u.s.": "Dark Horse",
        "dark horse comics, u.s.": "Dark Horse",
    }

    return replacements.get(key, name.strip())


def normalize_series_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip())