from django.db import models

class Company(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Име на фирма")
    eik = models.CharField(max_length=20, verbose_name="ЕИК")
    is_twice_monthly = models.BooleanField(default=False, verbose_name="Двукратно фактуриране (1-15 и 16-край)")
    note = models.TextField(blank=True, null=True, verbose_name="Забележка за отчети")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Фирма"
        verbose_name_plural = "Фирми"
        ordering = ["name"]
        indexes = [models.Index(fields=["eik"], name="company_eik_idx")]

class Card(models.Model):
    card_number = models.CharField(max_length=50, unique=True, verbose_name="Номер на карта")
    vehicle = models.CharField(max_length=255, blank=True, null=True, verbose_name="Превозно средство")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cards', verbose_name="Фирма")

    def __str__(self):
        return f"{self.card_number} ({self.company.name})"

    class Meta:
        verbose_name = "Карта"
        verbose_name_plural = "Карти"
        ordering = ["company__name", "card_number"]

class Price(models.Model):
    date = models.DateField(verbose_name="Дата")
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name='prices', verbose_name="Фирма")
    company_name_tmp = models.CharField(max_length=255, blank=True, null=True, verbose_name="Име на фирма (временно)")
    company_eik_tmp = models.CharField(max_length=20, blank=True, null=True, verbose_name="ЕИК (временно)")
    product = models.CharField(max_length=255, verbose_name="Продукт")
    final_price = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Крайна цена")
    eko_price = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name="ЕКО цена")
    margin = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name="Марж")
    discount = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name="Отстъпка")

    def __str__(self):
        company = self.company.name if self.company else self.company_name_tmp or "Без фирма"
        return f"{self.date} - {company} - {self.product}"

    class Meta:
        verbose_name = "Цена"
        verbose_name_plural = "Цени"
        ordering = ["-date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["date", "company", "product"], name="unique_company_product_price_date")
        ]
        indexes = [models.Index(fields=["company", "product", "date"], name="price_lookup_idx")]

class Transaction(models.Model):
    plant = models.CharField(max_length=255, verbose_name="Станция")
    card_number = models.CharField(max_length=50, verbose_name="Номер на карта")
    card = models.ForeignKey(Card, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    material = models.CharField(max_length=255, verbose_name="Материал")
    date = models.DateField(verbose_name="Дата")
    bill_qty = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Количество")
    bill_qty2 = models.CharField(max_length=50, blank=True, null=True, verbose_name="Тип количество")
    price = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="ЕКО цена")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сума")
    auth_time = models.TimeField(null=True, blank=True, verbose_name="Час")
    km_stand = models.IntegerField(null=True, blank=True, verbose_name="Километри")
    billing_document = models.CharField(max_length=100, blank=True, null=True, verbose_name="Billing Document")

    def __str__(self):
        return f"{self.date} - {self.card_number} - {self.material}"

    class Meta:
        verbose_name = "Транзакция"
        verbose_name_plural = "Транзакции"
        ordering = ["date", "id"]
        indexes = [
            models.Index(fields=["card_number"], name="transaction_card_idx"),
            models.Index(fields=["date"], name="transaction_date_idx"),
        ]
