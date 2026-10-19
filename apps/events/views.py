from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.models import User
from apps.analytics.formula import ContributionInput, FormulaParams, contribution
from apps.analytics.services import _factors
from apps.common.exceptions import TransitionError
from apps.common.mixins import RoleRequiredMixin
from apps.documents.models import Document
from apps.events.models import Event
from apps.events.selectors import filtered_events, similar_events
from apps.events.services import assign_events, transition_event
from apps.regions.models import Topic


class QueueView(RoleRequiredMixin, View):
    roles = ("analyst", "approver", "auditor")

    def get(self, request):
        params = {
            "region": request.GET.get("region", ""),
            "status": request.GET.get("status", ""),
            "topic": request.GET.get("topic", ""),
            "source": request.GET.get("source", ""),
            "q": request.GET.get("q", ""),
            "ordering": request.GET.get("ordering", "-occurred_at"),
            "date_from": request.GET.get("date_from", ""),
            "date_to": request.GET.get("date_to", ""),
        }
        if request.GET.get("confidence_min"):
            params["confidence_min"] = request.GET["confidence_min"]
        qs = filtered_events(params)
        page = Paginator(qs, 20).get_page(request.GET.get("page"))
        context = {
            "page": page,
            "filters": params,
            "topics": Topic.objects.filter(is_active=True),
            "statuses": Event.Status.choices,
            "analysts": User.objects.filter(role__in=["analyst", "admin"]),
        }
        template = "events/_table.html" if request.headers.get("HX-Request") == "true" else "events/queue.html"
        return render(request, template, context)

    def post(self, request):
        return EventAssignView.as_view()(request)


class SaveFilterView(RoleRequiredMixin, View):
    roles = ("analyst", "approver")

    def post(self, request):
        name = (request.POST.get("filter_name") or "").strip()[:40]
        if name:
            saved = request.session.get("saved_filters", [])
            saved = [item for item in saved if item.get("name") != name][:9]
            saved.insert(0, {"name": name, "query": request.GET.urlencode()})
            request.session["saved_filters"] = saved
            messages.success(request, "Фильтр сохранён в этой сессии")
        return redirect(request.META.get("HTTP_REFERER", "queue"))


class EventDetailView(RoleRequiredMixin, View):
    roles = ("analyst", "approver", "auditor")

    def get(self, request, pk):
        event = get_object_or_404(
            Event.objects.select_related("region", "topic", "reviewed_by", "assigned_to").prefetch_related(
                "links__document__source",
                "decisions__actor",
                "assessments",
                "topics__topic",
            ),
            pk=pk,
        )
        part = None
        if event.status == Event.Status.CONFIRMED:
            quality, novelty = _factors(event)
            age = (timezone.localdate() - timezone.localtime(event.occurred_at).date()).days
            part = round(
                contribution(
                    ContributionInput(event.pk, event.relevance_score, event.scale_score, quality, novelty, age),
                    FormulaParams(),
                ),
                4,
            )
        return render(
            request,
            "events/detail.html",
            {
                "event": event,
                "similar": similar_events(event),
                "contribution": part,
                "formula_version": FormulaParams().version,
                "topics": Topic.objects.filter(is_active=True),
            },
        )


class EventTransitionView(RoleRequiredMixin, View):
    roles = ("analyst",)

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        try:
            transition_event(
                event=event,
                new_status=request.POST.get("status", ""),
                actor=request.user,
                comment=request.POST.get("comment", ""),
                request=request,
            )
        except TransitionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Решение записано")
        return redirect("event-detail", pk=pk)


class EventAssignView(RoleRequiredMixin, View):
    roles = ("analyst",)

    def post(self, request):
        raw_ids = request.POST.getlist("event_ids")
        assignee = get_object_or_404(User, pk=request.POST.get("assignee"))
        try:
            count = assign_events(
                event_ids=[int(item) for item in raw_ids if item.isdigit()],
                assignee=assignee,
                actor=request.user,
                request=request,
            )
        except (TransitionError, ValueError) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Назначено карточек: {count}. Массовое подтверждение недоступно.")
        return redirect(request.META.get("HTTP_REFERER", "queue"))


class CompareView(RoleRequiredMixin, View):
    roles = ("analyst", "approver", "auditor")

    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        left = get_object_or_404(Document, pk=request.GET.get("left"), links__event=event)
        right = get_object_or_404(Document, pk=request.GET.get("right"), links__event=event)
        return render(request, "events/compare.html", {"event": event, "left": left, "right": right})
