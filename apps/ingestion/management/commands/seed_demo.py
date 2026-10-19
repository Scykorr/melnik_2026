from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics.models import DailyMetric
from apps.analytics.services import rebuild_region_metrics
from apps.audit.models import AuditEntry
from apps.documents.models import Document
from apps.documents.services import ingest_payload
from apps.events.models import Assessment, Event, EventDecision, EventDocument, EventTopic
from apps.events.services import transition_event
from apps.experiments.models import StudyPackage
from apps.ingestion.models import IngestJob
from apps.regions.models import Region, Topic
from apps.reports.models import Report
from apps.reports.services import build_report
from apps.sources.models import Source

USERS = [
    ("admin", User.Role.ADMIN, "Admin-IAM-2026!", True),
    ("operator", User.Role.OPERATOR, "Operator-IAM-2026!", False),
    ("analyst", User.Role.ANALYST, "Analyst-IAM-2026!", False),
    ("approver", User.Role.APPROVER, "Approver-IAM-2026!", False),
    ("auditor", User.Role.AUDITOR, "Auditor-IAM-2026!", False),
]
TOPICS = [
    ("labor", "Трудовые отношения", "Коллективные требования о занятости и оплате труда"),
    ("socio", "Социально-экономические требования", "Тарифы, цены и пособия"),
    ("housing", "ЖКХ", "Отопление, ремонт и содержание домов"),
    ("ecology", "Экология и землепользование", "Среда и земля"),
    ("transport", "Транспорт", "Маршруты, проезд и дороги"),
    ("local_gov", "Местное управление", "Работа местных органов"),
    ("other", "Прочее", "Иные коллективные требования"),
]
CLUSTERS = [
    ("NORTH", "housing", "heat-01", "ремонта теплосетей на улице Примерной", 5, "confirmed"),
    ("NORTH", "labor", "wage-02", "задержки зарплаты на демонстрационном комбинате", 9, "confirmed"),
    ("NORTH", "socio", "price-03", "рост цен на набор продуктов", 13, "confirmed"),
    ("NORTH", "ecology", "dump-04", "свалки у вымышленного ручья", 17, "confirmed"),
    ("NORTH", "transport", "bus-05", "отмены автобусного маршрута 12-демо", 21, "confirmed"),
    ("NORTH", "local_gov", "office-06", "решения районной администрации по двору", 25, "confirmed"),
    ("RIVER", "housing", "yard-07", "капремонта двора на набережной Образцовой", 32, "confirmed"),
    ("RIVER", "labor", "union-08", "спора с профсоюзом о сменах", 40, "confirmed"),
    ("RIVER", "socio", "benefit-09", "задержки пособия", 8, "in_review"),
    ("RIVER", "ecology", "smoke-10", "выброса на учебной площадке", 12, "in_review"),
    ("RIVER", "transport", "road-11", "ям на дороге к вымышленной пристани", 16, "in_review"),
    ("RIVER", "local_gov", "deputies-12", "ответа совета депутатов", 28, "in_review"),
    ("COAST", "housing", "heat-13", "отопления домов на Береговой", 44, "new"),
    ("COAST", "labor", "jobs-14", "массового увольнения на учебном причале", 52, "new"),
    ("COAST", "socio", "pension-15", "пересчёта пенсии в учебном примере", 60, "new"),
    ("COAST", "ecology", "forest-16", "вырубки лесного участка у маяка", 36, "needs_info"),
    ("COAST", "transport", "fare-17", "повышения стоимости проезда", 48, "needs_info"),
    ("NORTH", "local_gov", "hall-18", "приёма в мэрии по коллективному обращению", 56, "rejected"),
    ("NORTH", "housing", "pipes-19", "замены стояков жкх в доме 4", 68, "rejected"),
    ("RIVER", "transport", "ferry-20", "изменения маршрута парома", 76, "archived"),
]


def _wipe() -> None:
    Report.objects.all().delete()
    DailyMetric.objects.all().delete()
    Assessment.objects.all().delete()
    EventDecision.objects.all().delete()
    EventTopic.objects.all().delete()
    EventDocument.objects.all().delete()
    Event.objects.all().delete()
    Document.objects.all().delete()
    IngestJob.objects.all().delete()
    AuditEntry.objects.all().delete()
    Source.objects.all().delete()
    Topic.objects.all().delete()
    Region.objects.filter(parent__isnull=False).delete()
    Region.objects.all().delete()
    StudyPackage.objects.filter(code="PKG-DEMO").delete()


def _users() -> dict[str, User]:
    created = {}
    for username, role, password, staff in USERS:
        user, _ = User.objects.get_or_create(username=username, defaults={"role": role, "is_staff": staff})
        user.role = role
        user.is_staff = staff
        user.email = f"{username}@example.com"
        user.set_password(password)
        user.save()
        created[username] = user
    return created


class Command(BaseCommand):
    help = "Загружает синтетические демонстрационные данные. Не содержит реальных людей и измерений эффективности."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if Region.objects.filter(code="NORTH").exists() and not options["force"]:
            self.stdout.write("Демоданные уже загружены. Повторите с --force.")
            return
        if options["force"]:
            _wipe()
        users = _users()
        parent = Region.objects.create(
            name="Демонстрационный край",
            code="NORTH",
            min_event_threshold=1,
        )
        river = Region.objects.create(name="Речной округ", code="RIVER", parent=parent)
        coast = Region.objects.create(name="Приморский район", code="COAST", parent=parent)
        regions = {"NORTH": parent, "RIVER": river, "COAST": coast}
        for code, name, description in TOPICS:
            Topic.objects.create(code=code, name=name, description=description, rules_version="topic-rules-1.0.0")
        now = timezone.now()
        catalog = [
            ("ДЕМО: лента края", "rss", parent, 0.82),
            ("ДЕМО: атом-лента края", "atom", parent, 0.74),
            ("ДЕМО: json округа", "json", river, 0.77),
            ("ДЕМО: csv округа", "csv", river, 0.66),
            ("ДЕМО: ручные ссылки побережья", "manual", coast, 0.6),
            ("ДЕМО: официальный API, не подключён", "official_api", coast, 0.58),
            ("ДЕМО: экологическая лента округа", "rss", river, 0.7),
            ("ДЕМО: транспортный json края", "json", parent, 0.8),
        ]
        by_region: dict[str, list[Source]] = {"NORTH": [], "RIVER": [], "COAST": []}
        for index, (name, kind, region, weight) in enumerate(catalog, start=1):
            source = Source.objects.create(
                name=name,
                source_type=kind,
                base_url=f"https://demo.example.com/source-{index}",
                feed_url="",
                region_scope=region,
                terms_url=f"https://demo.example.com/terms-{index}",
                terms_checked_at=now,
                collection_basis="Синтетический открытый источник для стенда. Ограничения сайта не обходятся.",
                poll_interval=1440,
                reliability_weight=weight,
                is_active=True,
            )
            by_region[region.code].append(source)
        for region_code, topic_code, fact, subject, age, _status in CLUSTERS:
            published = now - timedelta(days=age)
            text = (
                f"<p>Жители провели собрание и выдвинули коллективное требование по поводу {subject}. "
                f"Сюжет {fact}. Демонстрационная публикация, не о конкретных людях.</p>"
            )
            if fact == "heat-01":
                text = "<script>alert(1)</script>" + text
            title = f"Собрание жителей: коллективное требование по поводу {subject}"
            sources = by_region[region_code]
            ingest_payload(
                source=sources[0],
                url=f"https://demo.example.com/items/{fact}",
                title=title,
                text=text,
                published_at=published,
                metadata={"fact_code": fact},
                mime="text/html",
            )
            ingest_payload(
                source=sources[1 % len(sources)],
                url=f"https://demo.example.com/reprints/{fact}",
                title=f"Перепечатка: {title}",
                text=text + "<p>Перепечатка открытого сообщения о том же требовании.</p>",
                published_at=published + timedelta(hours=1),
                metadata={"fact_code": fact},
                mime="text/html",
            )
        for index in range(10):
            ingest_payload(
                source=by_region["NORTH"][0],
                url=f"https://demo.example.com/comments/{index}",
                title="Комментарий читателя",
                text=f"Комментарий читателя номер {index}: один житель жалуется на бытовую жалобу крана. Коллективного события нет.",
                published_at=now - timedelta(days=index + 2),
                mime="text/plain",
            )
            ingest_payload(
                source=by_region["RIVER"][0],
                url=f"https://demo.example.com/history/{index}",
                title="Историческая справка",
                text=f"Историческая справка номер {index} о ярмарке в прошлом веке. К текущим публичным требованиям материал не относится.",
                published_at=now - timedelta(days=index + 3),
                mime="text/plain",
            )
        ingest_payload(
            source=by_region["COAST"][0],
            url="notaurl",
            title="Битый адрес",
            text="Текст не должен стать событием",
            published_at=now,
            mime="text/plain",
        )
        ingest_payload(
            source=by_region["COAST"][0],
            url="https://demo.example.com/nodate",
            title="Без даты",
            text="Жители провели собрание и выдвинули коллективное требование.",
            published_at=None,
            mime="text/plain",
        )
        analyst = users["analyst"]
        for region_code, _topic, fact, _subject, _age, status in CLUSTERS:
            document = Document.objects.get(canonical_url=f"https://demo.example.com/items/{fact}")
            link = document.links.select_related("event").first()
            if link is None:
                raise CommandError(f"Не создано событие для {fact}")
            event = link.event
            if status == "new":
                continue
            if status == "archived":
                transition_event(event=event, new_status="archived", actor=analyst, comment="Архив демонстрационной карточки")
                continue
            transition_event(event=event, new_status="in_review", actor=analyst, comment="Карточка взята в проверку")
            event.refresh_from_db()
            if status == "in_review":
                continue
            transition_event(event=event, new_status=status, actor=analyst, comment="Решение аналитика по синтетической карточке")
        end = timezone.localdate()
        start = end - timedelta(days=89)
        for region in regions.values():
            rebuild_region_metrics(region.id, start, end)
        build_report(
            region=parent,
            period_start=start,
            period_end=end,
            user=analyst,
            title="Проект ИАМ «Регион» по демонстрационному краю",
        )
        StudyPackage.objects.get_or_create(
            code="PKG-DEMO",
            defaults={
                "title": "Контейнер протокола без измерений",
                "document_count": 60,
                "notes": "Фактические T0 и T1 не измерялись",
            },
        )
        events = Event.objects.count()
        documents = Document.objects.count()
        if events != 20 or documents < 60:
            raise CommandError(f"Ожидались 20 событий и не меньше 60 документов, получено {events} и {documents}")
        self.stdout.write(self.style.SUCCESS(f"Синтетические данные готовы: документов {documents}, событий {events}."))
