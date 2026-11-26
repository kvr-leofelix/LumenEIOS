import re


def normalize_option(value: str) -> str:
    """Option labels are presentation, not part of the answer's meaning."""
    return re.sub(r"^(?:[A-D][.):]|[1-4][.):])\s+", "", value.strip(), flags=re.IGNORECASE).strip()


def option_identity(value: str) -> str:
    return " ".join(normalize_option(value).casefold().split())
