from django.contrib import admin

from .models import AuditLog, Card, Company, Price, Transaction


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "eik", "is_twice_monthly")
    search_fields = ("name", "eik")
    list_filter = ("is_twice_monthly",)


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("card_number", "vehicle", "company")
    search_fields = ("card_number", "vehicle", "company__name")
    list_select_related = ("company",)


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ("date", "company", "product", "final_price", "margin", "discount")
    search_fields = ("company__name", "product")
    list_filter = ("date", "product")
    list_select_related = ("company",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "card_number", "material", "bill_qty", "price")
    search_fields = ("card_number", "card__company__name", "material", "billing_document")
    list_filter = ("date", "material")

# Register your models here.


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "username", "action", "description", "status_code", "ip_address")
    search_fields = ("username", "description", "path", "ip_address")
    list_filter = ("action", "created_at")
    readonly_fields = (
        "user", "username", "action", "description", "method", "path", "url_name",
        "status_code", "ip_address", "user_agent", "metadata", "created_at",
    )
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
