from celery import shared_task

from apps.analytics.services import rebuild_region_metrics


@shared_task
def rebuild_metrics(region_id: int) -> int:
    return rebuild_region_metrics(region_id)
