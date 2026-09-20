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
    def test_home_requires_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("index"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('index')}")

    def test_authenticated_user_can_open_dashboard(self):
        user = get_user_model().objects.create_user(username="operator", password="safe-test-password")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("index")).status_code, 200)

    def test_gta_home_and_fuel_chain_selector(self):
        user = get_user_model().objects.create_user(username="manager", password="safe-test-password")
        self.client.force_login(user)
        home = self.client.get(reverse("home"))
        self.assertContains(home, "GTA Manager")
        self.assertContains(home, "Картови зареждания")

        chains = self.client.get(reverse("fuel_card_chains"))
        self.assertContains(chains, "ЕКО")
        self.assertContains(chains, "Petrol")
        self.assertContains(chains, "SNG")
        self.assertContains(chains, "Химойл")
        self.assertContains(chains, "img/logos/eko.png")
        self.assertContains(chains, "img/logos/petrol.png")
        self.assertContains(chains, "img/logos/sng.png")
        self.assertContains(chains, "img/logos/himoil.png")
        self.assertContains(home, "img/logos/gta-petroleum.png")
        self.assertContains(chains, f'href="{reverse("index")}"')

    def test_login_redirects_to_gta_home(self):
        get_user_model().objects.create_user(username="login-user", password="safe-test-password")
        response = self.client.post(reverse("login"), {"username": "login-user", "password": "safe-test-password"})
        self.assertRedirects(response, reverse("home"))

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
        self.assertContains(response, 'class="company-number text-center fw-semibold text-muted"', count=3)
        self.assertContains(response, "№")
        self.assertNotContains(response, 'id="company-suggestions"')


class CardListTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cards", password="safe-test-password")
        self.client.force_login(self.user)
        company = Company.objects.create(name="АВТО ТРАНС ПЕТКОВ", eik="123456789")
        Card.objects.create(card_number="700001", vehicle="СВ 1234 АВ", company=company)

    def test_card_list_uses_professional_filterable_table(self):
        response = self.client.get(reverse("card_list"))
        self.assertContains(response, 'class="page-heading"')
        self.assertContains(response, 'id="card-search"')
        self.assertContains(response, 'class="card-row"')
        self.assertContains(response, 'class="card-list-number text-center fw-semibold text-muted"')
        self.assertContains(response, "АВТО ТРАНС ПЕТКОВ")
        self.assertContains(response, "700001")


class PriceListTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="prices", password="safe-test-password")
        self.client.force_login(self.user)
        first_company = Company.objects.create(name="АЛФА ТРАНС", eik="111111111")
        second_company = Company.objects.create(name="БЕТА ЛОГИСТИК", eik="222222222")
        Price.objects.create(date=date(2026, 9, 18), company=first_company, product="DIESEL", eko_price="1.5000", margin="0.0300", discount="0", final_price="1.5300")
        Price.objects.create(date=date(2026, 9, 19), company=second_company, product="E GAS LPG", eko_price="0.7000", margin="0", discount="0.0200", final_price="0.6800")

    def test_price_list_shows_imported_price_fields(self):
        response = self.client.get(reverse("price_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Импортнати цени")
        self.assertContains(response, "refreshPrices")
        self.assertContains(response, "calendar-weekend")
        self.assertContains(response, "bi-chevron-left")
        self.assertContains(response, "bi-chevron-right")
        self.assertContains(response, "АЛФА ТРАНС")
        self.assertContains(response, "DIESEL")
        self.assertContains(response, "1.5000 €")
        self.assertContains(response, "1.5300 €")
        self.assertEqual(
            [price.date for price in response.context["page_obj"].object_list],
            [date(2026, 9, 18), date(2026, 9, 19)],
        )

    def test_company_price_history_is_ordered_oldest_first(self):
        company = Company.objects.get(name="АЛФА ТРАНС")
        Price.objects.create(date=date(2026, 9, 10), company=company, product="DIESEL", eko_price="1.4000", final_price="1.4300")
        response = self.client.get(reverse("company_prices", args=[company.id]))
        self.assertEqual(
            list(response.context["prices"].values_list("date", flat=True)),
            [date(2026, 9, 10), date(2026, 9, 18)],
        )

    def test_price_list_filters_by_company_product_and_date(self):
        response = self.client.get(reverse("price_list"), {
            "search": "БЕТА",
            "product": "E GAS LPG",
            "date_from": "2026-09-19",
            "date_to": "2026-09-19",
        })
        self.assertContains(response, "БЕТА ЛОГИСТИК")
        self.assertNotContains(response, "АЛФА ТРАНС")
        self.assertEqual(response.context["filtered_count"], 1)

    def test_company_search_matches_only_from_the_beginning(self):
        response = self.client.get(reverse("price_list"), {"search": "ЛОГИСТИК"})
        self.assertEqual(response.context["filtered_count"], 0)
        response = self.client.get(reverse("price_list"), {"search": "222"})
        self.assertContains(response, "БЕТА ЛОГИСТИК")
        self.assertEqual(response.context["filtered_count"], 1)

    def test_company_search_normalizes_lowercase_cyrillic_across_pages(self):
        other_company = Company.objects.create(name="ДРУГА ФИРМА", eik="333333333")
        Price.objects.bulk_create([
            Price(date=date(2026, 9, 1), company=other_company, product=f"PRODUCT {index:03d}", eko_price="1", final_price="1")
            for index in range(105)
        ])
        unfiltered = self.client.get(reverse("price_list"))
        self.assertNotContains(unfiltered, "АЛФА ТРАНС")

        response = self.client.get(reverse("price_list"), {"search": "алф"})
        self.assertContains(response, "АЛФА ТРАНС")
        self.assertEqual(response.context["filtered_count"], 1)
        self.assertEqual(response.context["page_obj"].number, 1)


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
