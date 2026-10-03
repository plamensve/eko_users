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
from .utils import ImportResult, get_company_report_data, get_invoice_period, get_unknown_report_data, relink_data


class PricingRulesTests(TestCase):
    def test_margin_uses_base_price_and_truncates_to_three_decimals(self):
        record = SimpleNamespace(margin=Decimal("0.0300"), discount=0, final_price=Decimal("1.4700"), eko_price=Decimal("1.4559"))
        result = calculate_pricing(quantity="10", transaction_price="1.600", product="DIESEL", price_record=record)
        self.assertEqual(result.eko_base_price, Decimal("1.456"))
        self.assertEqual(result.gta_price, Decimal("1.486"))
        self.assertEqual(result.profit, Decimal("0.300000"))

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
        self.assertEqual(first.profit, Decimal("0.562500"))
        self.assertEqual(second.profit, Decimal("-3.187500"))

    def test_negative_discount_price_is_clamped_to_zero(self):
        record = SimpleNamespace(margin=0, discount=Decimal("2.000"), final_price=0, eko_price=Decimal("1.000"))
        result = calculate_pricing(quantity="5", transaction_price="1.500", product="DIESEL", price_record=record)
        self.assertEqual(result.gta_price, Decimal("0.000"))

    def test_reference_pipeline_keeps_six_decimal_quantity_and_three_decimal_totals(self):
        result = calculate_pricing(
            quantity="37.567",
            transaction_price="1.5634",
            product="DIESEL",
            price_record=None,
        )
        self.assertEqual(result.eko_total, Decimal("58.717"))
        self.assertEqual(result.gta_total, Decimal("58.717"))

    def test_reference_pipeline_keeps_profit_to_six_decimals(self):
        record = SimpleNamespace(
            margin=Decimal("0.0300"),
            discount=0,
            final_price=Decimal("1.5000"),
            eko_price=Decimal("1.4550"),
        )
        result = calculate_pricing(
            quantity="37.567",
            transaction_price="1.600",
            product="DIESEL",
            price_record=record,
        )
        self.assertEqual(result.profit, Decimal("1.127010"))


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
        self.assertEqual(rows[0]["eko_price"], Decimal("1.600"))
        self.assertEqual(rows[0]["eko_base_price"], Decimal("1.420"))
        self.assertEqual(rows[0]["gta_price"], Decimal("1.450"))
        self.assertEqual(rows[0]["eko_base_total"], Decimal("14.200"))
        self.assertEqual(rows[1]["gta_price"], Decimal("1.550"))

    def test_auto_period_uses_second_half(self):
        self.assertEqual(get_invoice_period("auto"), (date(2026, 9, 16), date(2026, 9, 30)))
        rows, total_qty, *_ = get_company_report_data(self.company, period="billing")
        self.assertEqual(len(rows), 1)
        self.assertEqual(total_qty, Decimal("20.00"))


    def test_unlinked_transactions_are_grouped_as_unknown(self):
        Transaction.objects.create(
            plant="1",
            card_number="UNKNOWN-CARD",
            card=None,
            material="DIESEL EKONOMY",
            date=date(2026, 9, 12),
            bill_qty="25.266",
            price="2.500",
            amount="63.17",
        )
        rows, total_qty, _total_eko, total_gta, total_profit = get_unknown_report_data(period="full")
        self.assertEqual(len(rows), 1)
        self.assertEqual(total_qty, Decimal("25.266000"))
        self.assertEqual(total_gta, Decimal("63.165"))
        self.assertEqual(total_profit, Decimal("0.000000"))


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
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "img/logos/eko-icon.png")
        self.assertContains(response, 'class="eko-hero-brand"')
        self.assertContains(response, "Текущ отчетен период")
        self.assertNotContains(response, "Проекти и задачи")
        self.assertContains(response, 'class="app-sidebar"')
        self.assertContains(response, "EKO")
        self.assertContains(response, 'class="app-page-back"')
        self.assertContains(response, 'id="appBackButton"')

    def test_gta_home_and_fuel_chain_selector(self):
        user = get_user_model().objects.create_user(username="manager", password="safe-test-password")
        self.client.force_login(user)
        home = self.client.get(reverse("home"))
        self.assertContains(home, "GTA Manager")
        self.assertContains(home, "Картови зареждания")
        self.assertNotContains(home, 'class="app-footer"')
        self.assertNotContains(home, 'id="appBackButton"')

        chains = self.client.get(reverse("fuel_card_chains"))
        self.assertContains(chains, "ЕКО")
        self.assertContains(chains, "Petrol")
        self.assertContains(chains, "SNG")
        self.assertContains(chains, "Химойл")
        self.assertContains(chains, "img/logos/eko-icon.png")
        self.assertContains(chains, "img/logos/petrol-icon.png")
        self.assertContains(chains, "img/logos/sng-icon.png")
        self.assertContains(chains, "img/logos/himoil-icon.png")
        self.assertContains(home, "img/logos/gta-original-diamond.svg")
        self.assertContains(chains, 'width="78" height="78"', count=4)
        self.assertContains(chains, "app.css?v=20261003-table-headings-17")
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

    def test_company_report_uses_scoped_period_navigation(self):
        response = self.client.get(reverse("company_transactions", args=[self.auto_petkov.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "report-period-nav")
        self.assertContains(response, 'class="company-transactions-table"')
        self.assertContains(response, 'class="transaction-index">№</th>')
        self.assertContains(response, "profit-column-heading")
        self.assertContains(response, "bi-graph-up-arrow")
        self.assertContains(response, "ЕКО цена на колонка")
        self.assertContains(response, "FinPr")
        self.assertContains(response, "ЕКО цена към GTA")
        self.assertContains(response, "GTA към клиента")
        self.assertContains(response, "ЕКО ЦЕНА")

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
        self.assertContains(response, "fuel-pill fuel-pill--diesel")
        self.assertContains(response, "bi-truck-front-fill")
        self.assertContains(response, "1.5000 €")
        self.assertContains(response, "1.5300 €")
        self.assertNotContains(response, "ЕКО цена на колонка")
        self.assertNotContains(response, "FinPr")
        self.assertContains(response, "ЕКО цена към GTA")
        self.assertContains(response, "GTA към клиента")
        self.assertContains(response, "ЕКО ЦЕНА")
        self.assertContains(response, "КРАЙНА ЦЕНА")
        self.assertContains(response, "ЕКО ЦЕНА + МАРЖ")
        self.assertContains(response, "bi-fuel-pump-fill")
        self.assertContains(response, "ОТСТЪПКА")
        self.assertNotContains(response, "ЕКО_ЦЕНА")
        self.assertNotContains(response, "КРАЙНА_ЦЕНА")
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
        self.assertContains(response, "fuel-pill fuel-pill--diesel")
        self.assertContains(response, "bi-truck-front-fill")
        self.assertNotContains(response, "ЕКО цена на колонка")
        self.assertNotContains(response, "FinPr")
        self.assertContains(response, "ЕКО цена към GTA")
        self.assertContains(response, "GTA към клиента")
        self.assertContains(response, "ЕКО ЦЕНА")
        self.assertContains(response, "КРАЙНА ЦЕНА")

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

    def test_product_labels_classify_mixed_alphabet_import_names(self):
        products = {
            "DIЕSЕL ЕКОNОМY": "diesel",
            "DIЕSЕL DОUВLЕ FILТЕRЕD": "premium-diesel",
            "95 ЕКОNОМY UNLЕАDЕD": "petrol",
            "ЕКО RАСING 100": "premium-petrol",
            "Е GАS LРG": "lpg",
        }
        for product, expected in products.items():
            with self.subTest(product=product):
                self.assertEqual(Price(product=product).product_kind, expected)

    def test_relink_legacy_prices_with_duplicate_keys_keeps_existing_records(self):
        company = Company.objects.create(name="ПОДИ ЕООД", eik="204195863")
        existing = Price.objects.create(date=date(2026, 9, 1), company=company, product="DIESEL", final_price="1.5000")
        duplicate = Price.objects.create(date=date(2026, 9, 1), company_eik_tmp=company.eik, product="DIESEL", final_price="1.6000")
        later_duplicate = Price.objects.create(date=date(2026, 9, 1), company_name_tmp=company.name, product="DIESEL", final_price="1.7000")
        unique = Price.objects.create(date=date(2026, 9, 2), company_eik_tmp=company.eik, product="DIESEL", final_price="1.8000")

        self.assertEqual(relink_data(), (0, 1))
        self.assertEqual(relink_data(), (0, 0))
        existing.refresh_from_db()
        duplicate.refresh_from_db()
        later_duplicate.refresh_from_db()
        unique.refresh_from_db()
        self.assertEqual(existing.final_price, Decimal("1.5000"))
        self.assertIsNone(duplicate.company_id)
        self.assertIsNone(later_duplicate.company_id)
        self.assertEqual(unique.company_id, company.id)

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


class AnalyticsExcelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="analyst", password="safe-test-password")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="ТЕСТ ФИРМА", eik="123")
        self.card = Card.objects.create(card_number="100", company=self.company)
        for day, qty in ((5, "10"), (20, "20")):
            Transaction.objects.create(plant="1", card_number="100", card=self.card,
                material="DIЕSЕL ЕКОNОМY", date=date(2026, 9, day), bill_qty=qty,
                price="1.5000", amount="15")

    def test_excel_matches_selected_analytics_period_and_five_sheet_layout(self):
        from io import BytesIO
        from openpyxl import load_workbook

        for period, expected_liters in (("first", 10), ("second", 20), ("full", 30)):
            with self.subTest(period=period):
                response = self.client.get(reverse("analytics_excel"), {"report": period})
                self.assertEqual(response.status_code, 200)
                self.assertIn("attachment", response["Content-Disposition"])
                workbook = load_workbook(BytesIO(response.content), data_only=True)
                self.assertEqual(workbook.sheetnames,
                    ["Summary", "Dashboard", "Total", "Top Clients", "Analysis Dataset"])
                self.assertEqual(workbook["Total"]["B4"].value, expected_liters)
                self.assertEqual(workbook["Summary"]["I4"].value, expected_liters)
                self.assertEqual(workbook["Analysis Dataset"]["I2"].value, expected_liters)

    def test_excel_empty_period_shows_message(self):
        Transaction.objects.all().delete()
        response = self.client.get(reverse("analytics_excel"), {"report": "first"}, follow=True)
        self.assertContains(response, "Няма транзакции")

    def test_web_analytics_does_not_mix_products_into_weighted_prices(self):
        response = self.client.get(reverse("analytics"), {"report": "full"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Среднопретеглени цени")
        self.assertNotContains(response, "ЕКО колонка (€/л)")
        self.assertNotContains(response, "ЕКО → GTA (€/л)")
        self.assertNotContains(response, "GTA → клиент (€/л)")
        self.assertNotIn("grand_avg_eko_column_price", response.context)
        self.assertNotIn("grand_avg_eko_to_gta_price", response.context)
        self.assertNotIn("grand_avg_gta_client_price", response.context)

    def test_analytics_includes_only_report_products_from_unknown_group(self):
        Transaction.objects.create(
            plant="1",
            card_number="UNLINKED-1",
            card=None,
            material="DIESEL EKONOMY",
            date=date(2026, 9, 10),
            bill_qty="25",
            price="2.500",
            amount="62.50",
        )
        # The management Excel intentionally excludes products outside the
        # configured five fuels. Web Analytics must use the same scope.
        Transaction.objects.create(
            plant="1",
            card_number="UNLINKED-ADBLUE",
            card=None,
            material="ADBLUE",
            date=date(2026, 9, 10),
            bill_qty="198.470",
            price="1.980",
            amount="392.97",
        )

        response = self.client.get(reverse("analytics"), {"report": "full"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unknown")
        self.assertEqual(response.context["grand_total_qty"], Decimal("55.000000"))
        self.assertEqual(response.context["grand_total_gta"], Decimal("107.500"))


    def test_unknown_row_links_to_company_style_transaction_page(self):
        Transaction.objects.create(
            plant="1",
            card_number="UNLINKED-DETAIL",
            card=None,
            material="DIESEL EKONOMY",
            date=date(2026, 9, 10),
            bill_qty="12.500",
            price="2.000",
            amount="25.00",
        )
        analytics_response = self.client.get(reverse("analytics"), {"report": "full"})
        self.assertContains(
            analytics_response,
            f'href="{reverse("unknown_transactions")}?report=full"',
        )

        detail_response = self.client.get(reverse("unknown_transactions"), {"report": "full"})
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Unknown")
        self.assertContains(detail_response, "Несвързани транзакции")
        self.assertContains(detail_response, "UNLINKED-DETAIL")
        self.assertContains(detail_response, "DIESEL EKONOMY")
        self.assertContains(detail_response, "fuel-pill fuel-pill--diesel")
        self.assertContains(detail_response, "bi-truck-front-fill")
        self.assertContains(detail_response, 'class="company-transactions-table"')
        self.assertNotContains(detail_response, ">Цени</a>")
