from django.urls import Resolver404, resolve

from .audit import log_audit_event
from .models import AuditLog


EXPORT_URL_NAMES = {
    "export_excel",
    "export_pdf",
    "export_all_zip",
    "export_company_zip",
    "analytics_excel",
}

ACTION_LABELS = {
    "home": "Преглед на началното работно пространство",
    "fuel_card_chains": "Преглед на веригите за картови зареждания",
    "index": "Преглед на ЕКО таблото",
    "upload": "Импорт на данни",
    "company_list": "Преглед на фирмите",
    "company_transactions": "Преглед на фирмените транзакции",
    "unknown_transactions": "Преглед на несвързаните транзакции",
    "company_prices": "Преглед на ценовата история на фирма",
    "card_list": "Преглед на картите",
    "price_list": "Преглед на импортираните цени",
    "analytics": "Преглед на Аналитика",
    "profile": "Преглед на профила",
    "change_password": "Промяна на парола",
    "export_excel": "Генериране на Excel отчет",
    "export_pdf": "Генериране на PDF отчет",
    "export_all_zip": "Експорт на всички фирмени отчети",
    "export_company_zip": "Експорт на фирмен архив",
    "analytics_excel": "Генериране на аналитичен Excel отчет",
    "company_add": "Добавяне на фирма",
    "company_edit": "Редактиране на фирма",
    "company_delete": "Изтриване на фирма",
    "company_delete_all": "Изтриване на всички фирми",
    "card_add": "Добавяне на карта",
    "card_edit": "Редактиране на карта",
    "card_delete": "Изтриване на карта",
    "card_delete_all": "Изтриване на всички карти",
    "price_delete_all": "Изтриване на всички цени",
    "transaction_delete_all": "Изтриване на всички транзакции",
    "relink_data": "Повторно свързване на данните",
}

EXCLUDED_URL_NAMES = {
    "login",
    "logout",
    "audit_logs",
    "company_search_suggestions",
}


class AuditLogMiddleware:
    """Record meaningful authenticated activity without storing request bodies."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        self._record(request, response)
        return response

    def _record(self, request, response):
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return

        path = request.path or ""
        if path.startswith(("/static/", "/media/")) or path == "/favicon.ico":
            return

        try:
            match = getattr(request, "resolver_match", None) or resolve(request.path_info)
        except Resolver404:
            match = None

        url_name = (match.url_name if match else "") or ""
        view_name = (match.view_name if match else "") or ""

        if url_name in EXCLUDED_URL_NAMES:
            return

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        method = request.method.upper()
        if method == "GET" and is_ajax:
            return

        if url_name in EXPORT_URL_NAMES:
            action = AuditLog.Action.EXPORT
        elif method == "POST":
            if url_name == "upload":
                action = AuditLog.Action.IMPORT
            elif "delete" in url_name:
                action = AuditLog.Action.DELETE
            elif url_name.endswith("_add"):
                action = AuditLog.Action.CREATE
            elif url_name.endswith("_edit") or url_name in {"change_password", "relink_data"}:
                action = AuditLog.Action.UPDATE
            else:
                action = AuditLog.Action.ACTION
        else:
            action = AuditLog.Action.VIEW

        description = ACTION_LABELS.get(url_name)
        if not description:
            description = f"{'Преглед' if method == 'GET' else 'Действие'}: {view_name or path}"

        metadata = {}
        if match and match.kwargs:
            metadata["route"] = {key: str(value) for key, value in match.kwargs.items()}

        if url_name == "upload" and method == "POST":
            imported = []
            files = []
            if request.FILES.get("cards_file"):
                imported.append("карти и фирми")
                files.append(request.FILES["cards_file"].name)
            price_files = request.FILES.getlist("prices_files")
            if price_files:
                imported.append(f"ценови листи ({len(price_files)})")
                files.extend(upload.name for upload in price_files)
            if request.FILES.get("transactions_file"):
                imported.append("транзакции")
                files.append(request.FILES["transactions_file"].name)
            if imported:
                description = "Импорт: " + ", ".join(imported)
                metadata["files"] = files[:20]

        log_audit_event(
            action=action,
            request=request,
            user=user,
            description=description,
            url_name=view_name or url_name,
            status_code=getattr(response, "status_code", None),
            metadata=metadata,
        )
