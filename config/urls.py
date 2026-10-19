from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.routers import DefaultRouter

from apps.accounts.views import UserCreateView, UserListView
from apps.analytics.views import DashboardView
from apps.audit.views import AuditListView
from apps.common.api import (
    AuditViewSet,
    EventViewSet,
    ReportViewSet,
    SourceHealthView,
    TimelineView,
    TopicStatsView,
)
from apps.common.health import live, ready
from apps.common.metrics import metrics_view
from apps.events.views import (
    CompareView,
    EventAssignView,
    EventDetailView,
    EventTransitionView,
    QueueView,
    SaveFilterView,
)
from apps.experiments.views import EconomyView, ExperimentHomeView, SessionCreateView
from apps.ingestion.views import ImportView, ManualUrlView
from apps.reports.views import (
    ReportApproveView,
    ReportBuilderView,
    ReportCreateView,
    ReportExportView,
    ReportListView,
    ReportSubmitView,
)
from apps.sources.views import SourceCreateView, SourceListView, SourcePollView

router = DefaultRouter()
router.register("events", EventViewSet, basename="api-events")
router.register("reports", ReportViewSet, basename="api-reports")
router.register("audit", AuditViewSet, basename="api-audit")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
    path("metrics/", metrics_view, name="metrics"),
    path("accounts/login/", LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/users/", UserListView.as_view(), name="users"),
    path("accounts/users/new/", UserCreateView.as_view(), name="user-create"),
    path("", DashboardView.as_view(), name="dashboard"),
    path("queue/", QueueView.as_view(), name="queue"),
    path("queue/filters/", SaveFilterView.as_view(), name="save-filter"),
    path("events/<int:pk>/", EventDetailView.as_view(), name="event-detail"),
    path("events/<int:pk>/transition/", EventTransitionView.as_view(), name="event-transition"),
    path("events/<int:pk>/compare/", CompareView.as_view(), name="event-compare"),
    path("events/assign/", EventAssignView.as_view(), name="event-assign"),
    path("reports/", ReportListView.as_view(), name="reports"),
    path("reports/new/", ReportCreateView.as_view(), name="report-create"),
    path("reports/<int:pk>/", ReportBuilderView.as_view(), name="report-detail"),
    path("reports/<int:pk>/approve/", ReportApproveView.as_view(), name="report-approve"),
    path("reports/<int:pk>/submit/", ReportSubmitView.as_view(), name="report-submit"),
    path("reports/<int:pk>/export/<str:fmt>/", ReportExportView.as_view(), name="report-export"),
    path("sources/", SourceListView.as_view(), name="sources"),
    path("sources/new/", SourceCreateView.as_view(), name="source-create"),
    path("sources/<int:pk>/poll/", SourcePollView.as_view(), name="source-poll"),
    path("ingestion/import/", ImportView.as_view(), name="import-file"),
    path("ingestion/manual/", ManualUrlView.as_view(), name="manual-url"),
    path("audit/", AuditListView.as_view(), name="audit"),
    path("experiments/", ExperimentHomeView.as_view(), name="experiments"),
    path("experiments/sessions/new/", SessionCreateView.as_view(), name="session-create"),
    path("experiments/economy/", EconomyView.as_view(), name="economy"),
    path("api/v1/", include(router.urls)),
    path("api/v1/analytics/timeline/", TimelineView.as_view(), name="api-timeline"),
    path("api/v1/analytics/topics/", TopicStatsView.as_view(), name="api-topics"),
    path("api/v1/sources/health/", SourceHealthView.as_view(), name="api-health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
