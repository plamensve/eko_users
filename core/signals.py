from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .audit import log_audit_event
from .models import AuditLog


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    log_audit_event(
        action=AuditLog.Action.LOGIN,
        request=request,
        user=user,
        description="Вход в системата",
        url_name="login",
        status_code=200,
    )


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    log_audit_event(
        action=AuditLog.Action.LOGOUT,
        request=request,
        user=user,
        description="Изход от системата",
        url_name="logout",
        status_code=200,
    )


@receiver(user_login_failed)
def audit_login_failed(sender, credentials, request, **kwargs):
    username = credentials.get("username") or credentials.get("email") or "неизвестен"
    log_audit_event(
        action=AuditLog.Action.LOGIN_FAILED,
        request=request,
        username=str(username),
        description="Неуспешен опит за вход",
        url_name="login",
        status_code=401,
    )
