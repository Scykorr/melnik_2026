from __future__ import annotations

import platform
import statistics
from decimal import Decimal

from django.conf import settings

from apps.common.exceptions import EvaluationError
from apps.documents.dedup import EmbeddingDedup, TfidfDedup
from apps.experiments.models import EvaluationRun, GoldDocumentLabel, StudyResult, WorkSession


def labor_summary(package_id: int | None = None) -> dict:
    sessions = WorkSession.objects.filter(status=WorkSession.Status.COMPLETED, comparable=True)
    if package_id:
        sessions = sessions.filter(package_id=package_id)
    grouped: dict[tuple[int, str], dict[str, WorkSession]] = {}
    for session in sessions:
        grouped.setdefault((session.package_id, session.analyst_code), {})[session.mode] = session
    ratios = []
    saved = []
    for pair in grouped.values():
        manual = pair.get(WorkSession.Mode.AS_IS)
        system = pair.get(WorkSession.Mode.TO_BE)
        if manual is None or system is None:
            continue
        t0 = manual.human_active_minutes / 60
        t1 = system.human_active_minutes / 60
        if t0 <= 0:
            continue
        ratios.append((t0 - t1) / t0 * 100)
        saved.append(t0 - t1)
    if not ratios:
        return {
            "status": "не измерено",
            "pairs": 0,
            "median": None,
            "minimum": None,
            "maximum": None,
            "saved_hours": None,
        }
    return {
        "status": "измерено",
        "pairs": len(ratios),
        "median": round(statistics.median(ratios), 2),
        "minimum": round(min(ratios), 2),
        "maximum": round(max(ratios), 2),
        "saved_hours": round(sum(saved), 2),
    }


def store_summary(package) -> StudyResult:
    summary = labor_summary(package.pk)
    return StudyResult.objects.create(
        package=package,
        pair_count=summary["pairs"],
        median_k_t=summary["median"],
        min_k_t=summary["minimum"],
        max_k_t=summary["maximum"],
        saved_hours=summary["saved_hours"],
        status_label=summary["status"],
        note="Расчёт только по завершённым сопоставимым парам. Незавершённая сессия не считается выпуском ИАМ.",
    )


def economic_effect(*, t0: Decimal, t1: Decimal, releases: Decimal, hourly: Decimal, operating: Decimal, capex: Decimal | None):
    effect = (t0 - t1) * releases * hourly - operating
    if effect <= 0:
        payback: str | Decimal = "не достигается"
    elif capex is None:
        payback = "не заданы первоначальные затраты"
    else:
        payback = (capex / effect).quantize(Decimal("0.01"))
    return {
        "effect": effect.quantize(Decimal("0.01")),
        "payback": payback,
        "label": "прогноз, не фактический результат проекта",
    }


def evaluate_dedup(*, dataset: str, method: str, split: str, threshold: float = 0.55) -> EvaluationRun:
    labels = list(GoldDocumentLabel.objects.filter(dataset=dataset, split=split, status="active").order_by("document_uid"))
    if len(labels) < 2:
        raise EvaluationError("Эталонный набор для выбранного разбиения не найден. Метрики не вычисляются.")
    if any(not (item.text or "").strip() for item in labels):
        raise EvaluationError("В эталоне нет текста для сравнения. Метрики не вычисляются.")
    if method == "embedding":
        scorer = EmbeddingDedup()
        if not scorer.available():
            raise EvaluationError("Локальная модель эмбеддингов не установлена. Метрики не вычисляются.")
    elif method == "tfidf":
        scorer = TfidfDedup()
    else:
        raise EvaluationError("Неизвестный метод. Доступен tfidf.")
    import time

    started = time.perf_counter()
    matrix = scorer.score_pairs([item.text for item in labels])
    true_positive = false_positive = false_negative = candidates = 0
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            if labels[i].region_code != labels[j].region_code:
                continue
            candidates += 1
            truth = bool(labels[i].event_group_id) and labels[i].event_group_id == labels[j].event_group_id
            predicted = matrix[i][j] >= threshold
            if predicted and truth:
                true_positive += 1
            elif predicted and not truth:
                false_positive += 1
            elif truth and not predicted:
                false_negative += 1
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else None
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else None
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    duration_ms = int((time.perf_counter() - started) * 1000)
    unreliable = len(labels) < 30
    warning = "Выборка меньше 30 документов: оценка ненадёжна и не является результатом проекта." if unreliable else ""
    kind = labels[0].dataset_kind
    return EvaluationRun.objects.create(
        dataset=dataset,
        dataset_kind=kind,
        method=method,
        method_version=scorer.version,
        split=split,
        parameters={"threshold": threshold, "window": "same-region"},
        sample_size=len(labels),
        candidate_count=candidates,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=None if precision is None else round(precision, 4),
        recall=None if recall is None else round(recall, 4),
        f1=None if f1 is None else round(f1, 4),
        duration_ms=duration_ms,
        environment={"python": platform.python_version(), "app": settings.APP_VERSION},
        unreliable=unreliable or kind == "synthetic",
        warning=warning or ("Синтетическая техническая проверка, не подтверждение качества." if kind == "synthetic" else ""),
    )
