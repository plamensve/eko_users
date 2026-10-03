from django.db import OperationalError, ProgrammingError

from .models import AuditLog


def get_client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def get_user_agent(request):
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:500]


def log_audit_event(
    *,
    action,
    request=None,
    user=None,
    username="",
    description="",
    method="",
    path="",
    url_name="",
    status_code=None,
    metadata=None,
):
    """Write an audit event without ever breaking the user request."""
    resolved_user = user
    if resolved_user is None and request is not None:
        candidate = getattr(request, "user", None)
        if getattr(candidate, "is_authenticated", False):
            resolved_user = candidate

    if not username and resolved_user is not None:
        username = resolved_user.get_username()

    try:
        return AuditLog.objects.create(
            user=resolved_user if getattr(resolved_user, "is_authenticated", False) else None,
            username=(username or "")[:150],
            action=action,
            description=(description or "")[:255],
            method=(method or getattr(request, "method", "") or "")[:10],
            path=(path or getattr(request, "path", "") or "")[:500],
            url_name=(url_name or "")[:120],
            status_code=status_code,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            metadata=metadata or {},
        )
    except (OperationalError, ProgrammingError):
        return None
