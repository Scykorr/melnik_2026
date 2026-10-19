from __future__ import annotations

import re

RELEVANCE_VERSION = "relevance-rules-1.0.0"
TOPIC_VERSION = "topic-rules-1.0.0"

RELEVANT_PATTERNS = (
    r"митинг",
    r"пикет",
    r"шеств",
    r"забастов",
    r"коллективн\w*\s+требован",
    r"собрани\w*\s+жите",
    r"акци\w*\s+протест",
    r"публичн\w*\s+обращен",
)
IRRELEVANT_PATTERNS = (
    r"комментар",
    r"историческ",
    r"в прошлом веке",
    r"реклам",
    r"один житель жалуется",
    r"бытов\w*\s+жалоб",
    r"не связано с коллектив",
)
TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("labor", (r"зарплат", r"увольн", r"профсоюз", r"трудов")),
    ("socio", (r"тариф", r"пособ", r"пенси", r"рост цен")),
    ("housing", (r"жкх", r"отоплен", r"капремонт", r"теплосет")),
    ("ecology", (r"свалк", r"выброс", r"загрязн", r"лесн")),
    ("transport", (r"маршрут", r"автобус", r"проезд", r"дорог")),
    ("local_gov", (r"администрац", r"мэри", r"депутат", r"местн\w*\s+власт")),
)


def _hits(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify_relevance(text: str) -> tuple[str, float, str]:
    """Отличает коллективное публичное требование от комментария, истории и частной жалобы."""
    low = (text or "").lower()
    relevant = _hits(low, RELEVANT_PATTERNS)
    irrelevant = _hits(low, IRRELEVANT_PATTERNS)
    if relevant and not irrelevant:
        return "relevant", 0.86, "Есть признаки коллективного публичного выражения требования"
    if irrelevant and not relevant:
        return "irrelevant", 0.9, "Похоже на комментарий, историческое упоминание или частную жалобу"
    if relevant and irrelevant:
        return "uncertain", 0.45, "Признаки противоречивы, запись передана аналитику"
    return "uncertain", 0.4, "Недостаточно признаков коллективного события, нужна проверка аналитика"


def classify_topics(text: str) -> tuple[str, list[str], str]:
    low = (text or "").lower()
    hits = [code for code, patterns in TOPIC_RULES if _hits(low, patterns)]
    if not hits:
        return "other", ["other"], f"Явная категория не найдена, правила {TOPIC_VERSION}"
    return hits[0], hits, f"Категория требования по правилам {TOPIC_VERSION}"
