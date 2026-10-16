import re


def normalize_user_name(value: str) -> str:
    """Trim, collapse whitespace, and title-case a user's full name."""
    normalized = re.sub(r"\s+", " ", value).strip()
    return " ".join(word.capitalize() for word in normalized.split(" "))
