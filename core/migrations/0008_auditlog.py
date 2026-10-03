from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_align_eko_reference_precision"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(blank=True, max_length=150, verbose_name="Потребител (snapshot)")),
                ("action", models.CharField(choices=[
                    ("login", "Вход"),
                    ("login_failed", "Неуспешен вход"),
                    ("logout", "Изход"),
                    ("view", "Преглед"),
                    ("import", "Импорт"),
                    ("export", "Експорт"),
                    ("create", "Създаване"),
                    ("update", "Промяна"),
                    ("delete", "Изтриване"),
                    ("action", "Действие"),
                ], db_index=True, max_length=32, verbose_name="Действие")),
                ("description", models.CharField(blank=True, max_length=255, verbose_name="Описание")),
                ("method", models.CharField(blank=True, max_length=10, verbose_name="HTTP метод")),
                ("path", models.CharField(blank=True, max_length=500, verbose_name="Път")),
                ("url_name", models.CharField(blank=True, max_length=120, verbose_name="URL име")),
                ("status_code", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="HTTP статус")),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True, verbose_name="IP адрес")),
                ("user_agent", models.CharField(blank=True, max_length=500, verbose_name="Браузър / устройство")),
                ("metadata", models.JSONField(blank=True, default=dict, verbose_name="Допълнителни данни")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Дата и час")),
                ("user", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="audit_events",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="Потребител",
                )),
            ],
            options={
                "verbose_name": "Системен лог",
                "verbose_name_plural": "Системни логове",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["action", "created_at"], name="audit_action_date_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["user", "created_at"], name="audit_user_date_idx"),
        ),
    ]
