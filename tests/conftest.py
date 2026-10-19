from types import SimpleNamespace

import pytest

from apps.accounts.models import User
from apps.regions.models import Region, Topic
from apps.sources.models import Source


@pytest.fixture
def analyst(db):
    user = User.objects.create_user("analyst-test", password="Pass-word-123", role=User.Role.ANALYST)
    return user


@pytest.fixture
def world(analyst):
    region = Region.objects.create(name="Демонстрационный край", code="NORTH")
    child = Region.objects.create(name="Речной округ", code="RIVER", parent=region)
    housing = Topic.objects.create(code="housing", name="ЖКХ", rules_version="topic-rules-1.0.0")
    labor = Topic.objects.create(code="labor", name="Труд", rules_version="topic-rules-1.0.0")
    Topic.objects.create(code="other", name="Прочее", rules_version="topic-rules-1.0.0")
    source = Source.objects.create(
        name="Источник",
        source_type=Source.SourceType.MANUAL,
        base_url="https://demo.example.com",
        terms_url="https://demo.example.com/terms",
        terms_checked_at="2026-01-01T00:00:00Z",
        collection_basis="открытая публикация",
        reliability_weight=0.8,
        region_scope=region,
        is_active=True,
    )
    other = Source.objects.create(
        name="Второй",
        source_type=Source.SourceType.RSS,
        base_url="https://demo.example.com/2",
        terms_url="https://demo.example.com/terms-2",
        terms_checked_at="2026-01-01T00:00:00Z",
        collection_basis="открытая публикация",
        reliability_weight=0.4,
        region_scope=region,
        is_active=True,
    )
    return SimpleNamespace(region=region, child=child, housing=housing, labor=labor, source=source, other=other, analyst=analyst)
