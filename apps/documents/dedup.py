from __future__ import annotations

import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[а-яёa-z0-9]{3,}", re.IGNORECASE)
STOP = {
    "это",
    "как",
    "для",
    "или",
    "при",
    "что",
    "жители",
    "вымышленного",
    "демонстрационная",
    "публикация",
    "сообщение",
    "открытого",
}


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def fact_signature(text: str) -> frozenset[str]:
    topic_words = {
        "зарплат",
        "увольн",
        "профсоюз",
        "трудов",
        "тариф",
        "пособ",
        "пенси",
        "жкх",
        "отоплен",
        "капремонт",
        "теплосет",
        "свалк",
        "выброс",
        "загрязн",
        "маршрут",
        "автобус",
        "проезд",
        "дорог",
        "администрац",
        "депутат",
        "митинг",
        "пикет",
        "шествие",
        "забастовка",
        "коллективное",
        "требование",
        "собрание",
    }
    tokens = [token for token in tokenize(text) if token not in STOP and token not in topic_words]
    return frozenset(tokens[:12])


def _tfidf(docs: list[str]) -> list[dict[str, float]]:
    bags = [Counter(tokenize(doc)) for doc in docs]
    df: Counter[str] = Counter()
    for bag in bags:
        df.update(bag.keys())
    n = max(len(docs), 1)
    vectors: list[dict[str, float]] = []
    for bag in bags:
        total = sum(bag.values()) or 1
        vectors.append(
            {token: (count / total) * (math.log((1 + n) / (1 + df[token])) + 1) for token, count in bag.items()}
        )
    return vectors


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(left[token] * right[token] for token in left.keys() & right.keys())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def cosine_texts(left: str, right: str) -> float:
    first, second = _tfidf([left, right])
    return cosine(first, second)


def should_merge_texts(
    left: str,
    right: str,
    *,
    left_fact: str = "",
    right_fact: str = "",
    threshold: float = 0.55,
) -> tuple[bool, float, str]:
    """Общая тема сама по себе не склеивает события: нужны совпавшие факты."""
    similarity = cosine_texts(left, right)
    if left_fact and right_fact and left_fact != right_fact:
        return False, similarity, "Разные факты при общей теме: события не объединяются"
    left_sig = fact_signature(left)
    right_sig = fact_signature(right)
    overlap = 0.0
    if left_sig and right_sig:
        overlap = len(left_sig & right_sig) / min(len(left_sig), len(right_sig))
    if left_fact and right_fact and left_fact == right_fact and similarity >= 0.35:
        return True, similarity, "Совпали код факта, близкий текст, время и территория"
    if overlap >= 0.6 and similarity >= threshold:
        return True, similarity, "Совпали предмет требования, текст, время и территория"
    return False, similarity, "Общей темы и лозунга недостаточно для объединения разных акций"


class TfidfDedup:
    """Базовый метод. Работает без внешних моделей."""

    name = "tfidf"
    version = "tfidf-cosine-1.0.0"

    def score_pairs(self, texts: list[str]) -> list[list[float]]:
        vectors = _tfidf(texts)
        size = len(vectors)
        matrix = [[0.0] * size for _ in range(size)]
        for i in range(size):
            matrix[i][i] = 1.0
            for j in range(i + 1, size):
                value = cosine(vectors[i], vectors[j])
                matrix[i][j] = value
                matrix[j][i] = value
        return matrix


class EmbeddingDedup:
    """Подключается только если локально установлена модель. Иначе baseline остаётся рабочим."""

    name = "embedding"
    version = "embedding-adapter-1.0.0"

    def available(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            return False
        return True

    def score_pairs(self, texts: list[str]) -> list[list[float]]:
        if not self.available():
            raise RuntimeError("Локальная модель эмбеддингов не установлена. Используйте method=tfidf.")
        raise RuntimeError("Адаптер эмбеддингов не активирован в этой поставке MVP.")
