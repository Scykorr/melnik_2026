from __future__ import annotations

from datetime import date

import django_filters
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.models import DailyMetric
from apps.analytics.selectors import dashboard_payload
from apps.audit.models import AuditEntry
from apps.common.permissions import RolePermission
from apps.events.models import Event
from apps.events.services import transition_event
from apps.regions.models import Region
from apps.reports.models import Report
from apps.reports.services import approve_report, build_report
from apps.sources.selectors import source_health


class EventFilter(django_filters.FilterSet):
    region = django_filters.CharFilter(field_name="region__code")
    topic = django_filters.CharFilter(field_name="topic__code")
    status = django_filters.CharFilter()
    occurred_after = django_filters.DateFilter(field_name="occurred_at__date", lookup_expr="gte")
    occurred_before = django_filters.DateFilter(field_name="occurred_at__date", lookup_expr="lte")
    confidence_min = django_filters.NumberFilter(field_name="confidence", lookup_expr="gte")
    source = django_filters.NumberFilter(field_name="links__document__source_id", distinct=True)

    class Meta:
        model = Event
        fields = ["region", "topic", "status"]


class EventDocumentSerializer(serializers.Serializer):
    relation_type = serializers.CharField()
    is_primary = serializers.BooleanField()
    title = serializers.CharField(source="document.title")
    canonical_url = serializers.CharField(source="document.canonical_url")
    source_name = serializers.CharField(source="document.source.name")
    clean_text = serializers.CharField(source="document.clean_text", required=False)


class EventListSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source="region.code")
    topic = serializers.CharField(source="topic.code")

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "status",
            "region",
            "topic",
            "occurred_at",
            "scale_score",
            "relevance_score",
            "confidence",
        ]


class EventDetailSerializer(EventListSerializer):
    documents = EventDocumentSerializer(source="links", many=True)
    grouping_explanation = serializers.CharField()

    class Meta(EventListSerializer.Meta):
        fields = [*EventListSerializer.Meta.fields, "summary", "review_comment", "grouping_explanation", "documents"]


class CommentSerializer(serializers.Serializer):
    comment = serializers.CharField(min_length=3, max_length=2000)


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Event.objects.select_related("region", "topic").prefetch_related("links__document__source")
    filterset_class = EventFilter
    ordering_fields = ["occurred_at", "confidence", "status"]
    permission_classes = [RolePermission]
    read_roles = ("analyst", "approver", "auditor", "operator")
    write_roles = ("analyst",)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EventDetailSerializer
        return EventListSerializer

    def _transition(self, request, pk, status):
        payload = CommentSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        event = transition_event(
            event=self.get_object(),
            new_status=status,
            actor=request.user,
            comment=payload.validated_data["comment"],
            request=request,
        )
        return Response(EventDetailSerializer(event).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self._transition(request, pk, Event.Status.CONFIRMED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._transition(request, pk, Event.Status.REJECTED)


class TimelineView(APIView):
    permission_classes = [RolePermission]
    read_roles = ("analyst", "approver", "auditor", "operator")

    def get(self, request):
        region = get_object_or_404(Region, code=request.GET.get("region", ""))
        metrics = DailyMetric.objects.filter(region=region).order_by("date")
        if request.GET.get("date_from"):
            metrics = metrics.filter(date__gte=request.GET["date_from"])
        if request.GET.get("date_to"):
            metrics = metrics.filter(date__lte=request.GET["date_to"])
        return Response(
            {
                "region": region.code,
                "method_version": metrics.values_list("method_version", flat=True).first() or "",
                "points": [
                    {
                        "date": item.date.isoformat(),
                        "index_value": item.index_value,
                        "event_count": item.event_count,
                        "independent_source_count": item.independent_source_count,
                        "review_coverage": item.review_coverage,
                        "status": (item.components_json or {}).get("status"),
                        "low_coverage": (item.components_json or {}).get("low_coverage"),
                    }
                    for item in metrics
                ],
                "request_id": getattr(request, "request_id", ""),
            }
        )


class TopicStatsView(APIView):
    permission_classes = [RolePermission]
    read_roles = ("analyst", "approver", "auditor", "operator")

    def get(self, request):
        region = Region.objects.filter(code=request.GET.get("region", "")).first()
        if region is None:
            return Response({"topics": [], "request_id": getattr(request, "request_id", "")})
        payload = dashboard_payload(region, date.min, date.max)
        return Response({"topics": payload["topics"], "request_id": getattr(request, "request_id", "")})


class SourceHealthView(APIView):
    permission_classes = [RolePermission]
    read_roles = ("operator", "analyst", "approver", "auditor")

    def get(self, request):
        rows = []
        for row in source_health():
            source = row["source"]
            rows.append(
                {
                    "id": source.pk,
                    "name": source.name,
                    "source_type": source.source_type,
                    "is_active": source.is_active,
                    "last_success_at": source.last_success_at,
                    "last_error": source.last_error,
                    "documents": row["documents"],
                    "missed_intervals": row["missed_intervals"],
                    "without_date_share": row["without_date_share"],
                    "coverage_drop": row["coverage_drop"],
                    "queue_status": row["queue_status"],
                }
            )
        return Response({"results": rows, "request_id": getattr(request, "request_id", "")})


class ReportCreateSerializer(serializers.Serializer):
    region = serializers.SlugRelatedField(slug_field="code", queryset=Region.objects.all())
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    title = serializers.CharField(max_length=400)

    def validate(self, attrs):
        if attrs["period_end"] < attrs["period_start"]:
            raise serializers.ValidationError("Конец периода раньше начала")
        return attrs


class ReportSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source="region.code")

    class Meta:
        model = Report
        fields = [
            "id",
            "title",
            "region",
            "period_start",
            "period_end",
            "status",
            "version",
            "input_hash",
            "method_version",
            "template_version",
            "approved_at",
        ]


class ReportViewSet(viewsets.GenericViewSet):
    queryset = Report.objects.select_related("region")
    permission_classes = [RolePermission]
    read_roles = ("analyst", "approver", "auditor")
    write_roles = ("analyst",)
    serializer_class = ReportSerializer

    def list(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(ReportSerializer(page, many=True).data)

    def create(self, request):
        payload = ReportCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        report = build_report(
            region=data["region"],
            period_start=data["period_start"],
            period_end=data["period_end"],
            user=request.user,
            title=data["title"],
        )
        return Response(ReportSerializer(report).data, status=201)

    @action(detail=True, methods=["post"], write_roles=("approver",))
    def approve(self, request, pk=None):
        report = approve_report(report=self.get_object(), user=request.user, request=request)
        return Response(ReportSerializer(report).data)


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEntry
        fields = ["id", "action", "object_type", "object_id", "reason", "request_id", "created_at"]


class AuditViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditEntry.objects.all()
    serializer_class = AuditSerializer
    permission_classes = [RolePermission]
    read_roles = ("auditor",)
    write_roles = ()
    filterset_fields = ["action", "object_type"]
