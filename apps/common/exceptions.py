from __future__ import annotations


class DomainError(Exception):
    status_code = 400
    code = "domain_error"


class TransitionError(DomainError):
    code = "invalid_transition"


class ImmutableReportError(DomainError):
    status_code = 409
    code = "immutable_report"


class SsrfError(DomainError):
    code = "ssrf_blocked"


class EvaluationError(DomainError):
    code = "evaluation_unavailable"
