from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Card, Company, Price, Transaction
from .services import calculate_pricing
from .utils import ImportResult, get_company_report_data, get_invoice_period


class PricingRulesTests(TestCase):
    def test_margin_uses_base_price_and_truncates_to_three_decimals(self):
        record = SimpleNamespace(margin=Decimal("0.0300"), discount=0, final_price=Decimal("1.4700"), eko_price=Decimal("1.4559"))
        result = calculate_pricing(quantity="10", transaction_price="1.600", product="DIESEL", price_record=record)
        self.assertEqual(result.gta_price, Decimal("1.485"))
        self.assertEqual(result.profit, Decimal("0.30"))

    def test_discount_uses_transaction_price(self):
        record = SimpleNamespace(margin=0, discount=Decimal("0.050"), final_price=Decimal("1.500"), eko_price=Decimal("1.480"))
        result = calculate_pricing(quantity="20", transaction_price="1.600", product="DIESEL", price_record=record)
        self.assertEqual(result.gta_price, Decimal("1.550"))
        self.assertEqual(result.profit, Decimal("1.40"))

    def test_lpg_uses_reference_profit_rule_for_mixed_alphabet_name(self):
        record = SimpleNamespace(margin=0, discount=Decimal("0.025"), final_price=Decimal("0.700"), eko_price=Decimal("0.690"))
        result = calculate_pricing(quantity="100", transaction_price="0.750", product="Е GАS LРG", price_record=record)
        self.assertEqual(result.profit, Decimal("-1.00"))

    def test_lpg_profit_changes_with_discount(self):
        without_discount = SimpleNamespace(margin=0, discount=0, final_price=Decimal("0.700"), eko_price=Decimal("0.690"))
        with_discount = SimpleNamespace(margin=0, discount=Decimal("0.100"), final_price=Decimal("0.700"), eko_price=Decimal("0.690"))
        first = calculate_pricing(quantity="37.5", transaction_price="0.750", product="E GAS LPG", price_record=without_discount)
        second = calculate_pricing(quantity="37.5", transaction_price="0.750", product="Е GАS LРG", price_record=with_discount)
        self.assertEqual(first.profit, Decimal("0.56"))
        self.assertEqual(second.profit, Decimal("-3.19"))

    def test_negative_discount_price_is_clamped_to_zero(self):
        record = SimpleNamespace(margin=0, discount=Decimal("2.000"), final_price=0, eko_price=Decimal("1.000"))
        result = calculate_pricing(quantity="5", transaction_price="1.500", product="DIESEL", price_record=record)
        self.assertEqual(result.gta_price, Decimal("0.000"))


class ReportingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="ТЕСТ ЕООД", eik="123", is_twice_monthly=True)
        self.card = Card.objects.create(card_number="100", company=self.company, vehicle="CA1234AA")
        Price.objects.create(date=date(2026, 9, 1), company=self.company, product="DIESEL", final_price="1.4500", eko_price="1.4200", margin="0.0300")
        Price.objects.create(date=date(2026, 9, 10), company=self.company, product="DIESEL", final_price="1.5500", eko_price="1.5200", margin="0.0300")
        Transaction.objects.create(plant="1", card_number="100", card=self.card, material="DIESEL", date=date(2026, 9, 8), bill_qty="10", price="1.600", amount="16")
        Transaction.objects.create(plant="1", card_number="100", card=self.card, material="DIESEL", date=date(2026, 9, 18), bill_qty="20", price="1.700", amount="34")

    def test_historical_price_on_or_before_transaction(self):
        rows, *_ = get_company_report_data(self.company, period="full")
        self.assertEqual(rows[0]["gta_price"], Decimal("1.450"))
        self.assertEqual(rows[1]["gta_price"], Decimal("1.550"))

    def test_auto_period_uses_second_half(self):
        self.assertEqual(get_invoice_period("auto"), (date(2026, 9, 16), date(2026, 9, 30)))
        rows, total_qty, *_ = get_company_report_data(self.company, period="billing")
        self.assertEqual(len(rows), 1)
        self.assertEqual(total_qty, Decimal("20.00"))


class AccessTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("index"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('index')}")

    def test_authenticated_user_can_open_dashboard(self):
        user = get_user_model().objects.create_user(username="operator", password="safe-test-password")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("index")).status_code, 200)

    def test_relink_is_post_only(self):
        user = get_user_model().objects.create_user(username="operator2", password="safe-test-password")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("relink_data")).status_code, 405)


class CompanySearchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="searcher", password="safe-test-password")
        self.client.force_login(self.user)
        self.auto_petkov = Company.objects.create(name="АВТО ТРАНС ПЕТКОВ", eik="123456789")
        Company.objects.create(name="АВТО СЕРВИЗ ЕООД", eik="987654321")
        Company.objects.create(name="ТРАНС АВТО ЕООД", eik="555555555")

    def test_suggestions_match_company_name_from_the_beginning(self):
        response = self.client.get(reverse("company_search_suggestions"), {"term": "авт"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.json()], ["АВТО СЕРВИЗ ЕООД", "АВТО ТРАНС ПЕТКОВ"])

    def test_suggestions_match_eik_from_the_beginning(self):
        response = self.client.get(reverse("company_search_suggestions"), {"term": "123"})
        self.assertEqual(response.json()[0]["id"], self.auto_petkov.id)

    def test_company_list_contains_rows_for_dynamic_filtering_without_suggestions(self):
        response = self.client.get(reverse("company_list"))
        self.assertContains(response, "АВТО ТРАНС ПЕТКОВ")
        self.assertContains(response, "АВТО СЕРВИЗ ЕООД")
        self.assertContains(response, 'class="company-row"', count=3)
        self.assertNotContains(response, 'id="company-suggestions"')


class PriceUploadTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="importer", password="safe-test-password")
        self.client.force_login(self.user)

    @patch("core.views.import_prices", return_value=ImportResult(created=10, updated=2, skipped=0))
    def test_multiple_price_files_stay_on_upload_page_with_success_message(self, mocked_import):
        files = [
            SimpleUploadedFile("prices-1.xlsx", b"first", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            SimpleUploadedFile("prices-2.xlsx", b"second", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ]
        response = self.client.post(reverse("upload"), {"prices_files": files}, follow=True)
        self.assertRedirects(response, reverse("upload"))
        self.assertContains(response, "Цените са импортирани успешно")
        self.assertContains(response, "Обработени файлове: 2")
        self.assertEqual(mocked_import.call_count, 2)
