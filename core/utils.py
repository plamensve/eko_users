"""Import, reporting and export utilities for the EKO manager."""

from __future__ import annotations

import io
import os
import re
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from django.db import transaction as db_transaction
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Card, Company, Price, Transaction
from .services import ZERO, as_decimal, calculate_pricing, money2, quantity2


TWICE_MONTHLY_COMPANIES = {
    "БКС ДОЛНИ ЧИФЛИК ЕООД", "МЕРКУРИЙ ПРОИЗВОДСТВО И ПАКЕТАЖ АД", "СПЕДСТРОЙ ООД",
    "ФУУДС ТРЕЙД ЕООД", "СИЙД ЕКСПРЕС ЕООД", "ФЕНИКС ИМПОРТ М ЕООД",
    "ОП ДЕЗИНФЕКЦИЯ, ДЕЗИНСЕКЦИЯ, ДЕРАТИЗАЦИЯ", "ОП КОМПЛЕКС ЗА ДЕТСКО ХРАНЕНЕ",
    "КСУДПЛУ СВ. ЙОАН ЗЛАТОУСТ", "РАЙОН АСПАРУХОВО", "ОП ИНВЕСТИЦИОННА ПОЛИТИКА",
    "ОП ТАСРУД", "ОП ЗООПАРК-СЦ ВАРНА", "ОП СПОРТ-ВАРНА",
    "РАЙОН МЛАДОСТ - ОБЩИНА ВАРНА", "РАЙОН ВЛАДИСЛАВ ВАРНЕНЧИК - ОБЩИНА ВАРНА",
    "КСУБЛС", "КСУДС", "КМЕТСТВО КАМЕНАР", "КМЕТСТВО КОНСТАНТИНОВО", "КМЕТСТВО ТОПОЛИ",
    "КСУВХ ГЕРГАНА ДСХ И ДПЛФУ", "КСУДМ", "ОП УПРАВЛЕНИЕ НА ПРОЕКТИ И ОЗЕЛЕНЯВАНЕ",
    "ДОМАШЕН СОЦИАЛЕН ПАТРОНАЖ", "РАЙОН ПРИМОРСКИ – ОБЩИНА ВАРНА",
    "ОБЩИНА ВАРНА - ДИРЕКЦИЯ СПОРТ", "ОБЩИНА ВАРНА - КМЕТСТВО КАЗАШКО",
    "ОБЩИНА ВАРНА % 1 - АВТОПАРК", "ОБЩИНА ВАРНА % 2 - ОБЩИНСКА ПОЛИЦИЯ",
    "ОБЩИНА ВАРНА % 3 - РАЗХОД ПО ПРОЕКТ ОИЦ ВАРНА", "ОБЩИНА ВАРНА % 4 - УЧИЛИЩЕН АВТОБУС",
    "КМЕТСТВО ЗВЕЗДИЦА", "ОП ОБЩИНСКИ ПАРКИНГИ И СИНЯ ЗОНА",
    "ОБЩИНА ВАРНА % 5 - ПДГ", "ОБЩИНА ВАРНА % 5 - ДИРЕКЦИЯ КУЛТУРА",
    "ОБЩИНА ВАРНА % 6 - УА", "РАЙОН ОДЕСОС",
}

COMPANY_NOTES = {
    "ОБЩИНА ВАРНА % 5 - ПДГ": (
        "Разходът е по проект №BG05SFPR002-2.012-0094-СО1 „Иновативни здравно-социални услуги "
        "в домашна среда“, Програма „Развитие на човешките ресурси“ 2021–2027."
    )
}


@dataclass(frozen=True)
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0

    @property
    def processed(self):
        return self.created + self.updated


def normalize_text(value):
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"\s+", " ", text).strip().upper()
    if "ОБЩИНА ВАРНА" in text and "%" not in text:
        text = re.sub(r"(ОБЩИНА ВАРНА)\s+(\d+)", r"\1 % \2", text)
    return text.translate(str.maketrans("OEAPCMTBHKX", "ОЕАРСМТВНКХ"))


def _clean_identifier(value):
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def _decimal(value, default=ZERO):
    if value is None or pd.isna(value) or str(value).strip() == "":
        return default
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _require_columns(frame, required, label):
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"Файлът за {label} няма задължителните колони: {', '.join(missing)}")


def get_transaction_data_period():
    dates = Transaction.objects.order_by("date").values_list("date", flat=True)
    return dates.first(), dates.last()


def get_invoice_period(period="full"):
    data_start, data_end = get_transaction_data_period()
    if not data_start or not data_end:
        return None, None
    if period == "full":
        return data_start, data_end
    if period == "first" or (period == "auto" and data_end.day <= 15):
        return data_end.replace(day=1), data_end.replace(day=15)
    if period == "second" or period == "auto":
        next_month = (data_end.replace(day=28) + timedelta(days=4)).replace(day=1)
        return data_end.replace(day=16), next_month - timedelta(days=1)
    return data_start, data_end


def _price_index(company):
    result = defaultdict(list)
    for item in company.prices.order_by("product", "date", "id"):
        result[normalize_text(item.product)].append(item)
    return result


def _historical_price(index, product, transaction_date):
    for item in reversed(index.get(normalize_text(product), [])):
        if item.date <= transaction_date:
            return item
    return None


def get_company_report_data(company, period="billing"):
    selected = "auto" if period == "billing" and company.is_twice_monthly else "full" if period == "billing" else period
    start_date, end_date = get_invoice_period(selected)
    transactions = Transaction.objects.filter(card__company=company).select_related("card").order_by("date", "id")
    transactions = transactions.filter(date__range=(start_date, end_date)) if start_date and end_date else transactions.none()
    prices = _price_index(company)
    rows, totals = [], {"qty": ZERO, "eko": ZERO, "gta": ZERO, "profit": ZERO}
    for item in transactions:
        price_record = _historical_price(prices, item.material, item.date)
        calc = calculate_pricing(quantity=item.bill_qty, transaction_price=item.price, product=item.material, price_record=price_record)
        qty = quantity2(item.bill_qty)
        rows.append({
            "date": item.date, "plant": item.plant, "card": item.card_number,
            "vehicle": item.card.vehicle if item.card else "", "material": item.material, "qty": qty,
            "qty_type": item.bill_qty2 or "", "eko_base_price": calc.eko_base_price,
            "gta_price": calc.gta_price, "discount": calc.discount, "margin": calc.margin,
            "profit": calc.profit, "gta_total": calc.gta_total, "eko_price": as_decimal(item.price),
            "eko_total": calc.eko_total, "auth_time": item.auth_time, "km_stand": item.km_stand,
            "billing_doc": item.billing_document or "", "has_price": price_record is not None,
        })
        totals["qty"] += qty
        totals["eko"] += calc.eko_total
        totals["gta"] += calc.gta_total
        totals["profit"] += calc.profit
    return rows, quantity2(totals["qty"]), money2(totals["eko"]), money2(totals["gta"]), money2(totals["profit"])


def _safe_name(value):
    return re.sub(r"[\\/*?:\"<>|]", "_", str(value)).strip(" .") or "report"


def _report_frame(data):
    columns = ["Дата", "Станция", "Име", "Номер на карта", "Име на артикул", "Литри", "Тип количество",
               "GTA цена", "Сума по GTA цена", "ЕКО цена", "Сума по ЕКО цена", "Час", "Километри", "Billing Document"]
    records = [[r["date"], r["plant"], r["vehicle"], r["card"], r["material"], float(r["qty"]), r["qty_type"],
                float(r["gta_price"]), float(r["gta_total"]), float(r["eko_price"]), float(r["eko_total"]),
                r["auth_time"], r["km_stand"], r["billing_doc"]] for r in data]
    return pd.DataFrame(records, columns=columns)


def _summary(data):
    grouped = defaultdict(lambda: {"qty": ZERO, "gta": ZERO, "eko": ZERO})
    for row in data:
        grouped[row["material"]]["qty"] += row["qty"]
        grouped[row["material"]]["gta"] += row["gta_total"]
        grouped[row["material"]]["eko"] += row["eko_total"]
    result = []
    for product, values in sorted(grouped.items(), key=lambda pair: pair[1]["qty"], reverse=True):
        weighted = values["gta"] / values["qty"] if values["qty"] else ZERO
        result.append((product, quantity2(values["qty"]), weighted.quantize(Decimal("0.00001")), money2(values["gta"]), money2(values["eko"])))
    return result


def export_company_excel(company, period="billing"):
    data, total_qty, total_eko, total_gta, _ = get_company_report_data(company, period)
    frame, output = _report_frame(data), io.BytesIO()
    start_row = 3 if company.note else 1
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="dd.mm.yyyy") as writer:
        sheet_name = _safe_name(company.name)[:31]
        frame.to_excel(writer, index=False, sheet_name=sheet_name, startrow=start_row)
        workbook, worksheet = writer.book, writer.sheets[sheet_name]
        title = workbook.add_format({"bold": True, "font_size": 15, "font_color": "#17324d"})
        header = workbook.add_format({"bold": True, "bg_color": "#17324d", "font_color": "white", "border": 1, "align": "center"})
        text = workbook.add_format({"border": 1})
        qty_fmt = workbook.add_format({"border": 1, "num_format": "0.00"})
        price_fmt = workbook.add_format({"border": 1, "num_format": "0.000"})
        avg_fmt = workbook.add_format({"border": 1, "num_format": "0.00000"})
        amount_fmt = workbook.add_format({"border": 1, "num_format": "0.00"})
        total_fmt = workbook.add_format({"bold": True, "bg_color": "#fff1b8", "border": 1, "num_format": "0.00"})
        worksheet.write(0, 0, company.name, title)
        if company.note:
            worksheet.merge_range(1, 0, 1, 13, f"Забележка: {company.note}", workbook.add_format({"italic": True, "font_color": "#8a4b08", "text_wrap": True}))
        for col, value in enumerate(frame.columns):
            worksheet.write(start_row, col, value, header)
        for index, width in enumerate([12, 18, 16, 18, 25, 11, 14, 12, 16, 12, 16, 10, 12, 18]):
            worksheet.set_column(index, index, width)
        worksheet.freeze_panes(start_row + 1, 0)
        worksheet.autofilter(start_row, 0, start_row + len(frame), len(frame.columns) - 1)
        for row_index, (_, row) in enumerate(frame.iterrows(), start=start_row + 1):
            for col_index, value in enumerate(row):
                fmt = price_fmt if col_index in (7, 9) else amount_fmt if col_index in (8, 10) else qty_fmt if col_index == 5 else text
                worksheet.write(row_index, col_index, "" if pd.isna(value) else value, fmt)
        summary_row = start_row + len(frame) + 3
        worksheet.write(summary_row, 0, "Обобщение по продукти", title)
        for col, value in enumerate(["Продукт", "Общо литри", "Средна претеглена GTA цена", "Сума GTA", "Сума ЕКО"]):
            worksheet.write(summary_row + 1, col, value, header)
        summary = _summary(data)
        for offset, row in enumerate(summary, start=summary_row + 2):
            worksheet.write(offset, 0, row[0], text)
            worksheet.write_number(offset, 1, float(row[1]), qty_fmt)
            worksheet.write_number(offset, 2, float(row[2]), avg_fmt)
            worksheet.write_number(offset, 3, float(row[3]), amount_fmt)
            worksheet.write_number(offset, 4, float(row[4]), amount_fmt)
        total_row = summary_row + 2 + len(summary)
        worksheet.write(total_row, 0, "ОБЩО", total_fmt)
        worksheet.write_number(total_row, 1, float(total_qty), total_fmt)
        worksheet.write(total_row, 2, "", total_fmt)
        worksheet.write_number(total_row, 3, float(total_gta), total_fmt)
        worksheet.write_number(total_row, 4, float(total_eko), total_fmt)
    output.seek(0)
    return output


def _register_pdf_font():
    candidates = [Path(os.environ.get("EKO_PDF_FONT", "")), Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    for path in candidates:
        if path.is_file():
            try:
                pdfmetrics.registerFont(TTFont("EKOUnicode", str(path)))
                return "EKOUnicode"
            except Exception:
                continue
    return "Helvetica"


def export_company_pdf(company, period="billing"):
    data, total_qty, total_eko, total_gta, _ = get_company_report_data(company, period)
    output, font = io.BytesIO(), _register_pdf_font()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("EkoTitle", parent=styles["Title"], fontName=font, textColor=colors.HexColor("#17324d"), alignment=TA_LEFT)
    body_style = ParagraphStyle("EkoBody", parent=styles["BodyText"], fontName=font, fontSize=8, leading=10)
    elements = [Paragraph(company.name, title_style)]
    if company.note:
        elements.extend([Paragraph(f"Забележка: {company.note}", body_style), Spacer(1, 8)])
    table_rows = [["Дата", "Карта / МПС", "Продукт", "Литри", "GTA цена", "Сума GTA", "ЕКО цена", "Сума ЕКО"]]
    for row in data:
        table_rows.append([row["date"].strftime("%d.%m.%Y"), f'{row["card"]} / {row["vehicle"]}', row["material"],
                           f'{row["qty"]:.2f}', f'{row["gta_price"]:.3f}', f'{row["gta_total"]:.2f}',
                           f'{row["eko_price"]:.3f}', f'{row["eko_total"]:.2f}'])
    table_rows.append(["ОБЩО", "", "", f"{total_qty:.2f}", "", f"{total_gta:.2f}", "", f"{total_eko:.2f}"])
    table = Table(table_rows, repeatRows=1, colWidths=[58, 128, 150, 54, 62, 68, 62, 68])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff1b8")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8c2cc")),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f6f8fa")]),
    ]))
    elements.append(table)
    summary = _summary(data)
    if summary:
        elements.extend([Spacer(1, 14), Paragraph("Обобщение по продукти", title_style)])
        summary_rows = [["Продукт", "Общо литри", "Средна GTA цена", "Сума GTA", "Сума ЕКО"]]
        summary_rows += [[r[0], f"{r[1]:.2f}", f"{r[2]:.5f}", f"{r[3]:.2f}", f"{r[4]:.2f}"] for r in summary]
        summary_table = Table(summary_rows, repeatRows=1, colWidths=[220, 90, 110, 90, 90])
        summary_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey), ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ]))
        elements.append(summary_table)
    doc.build(elements)
    output.seek(0)
    return output


def export_all_companies_zip(period="billing"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for company in Company.objects.order_by("name"):
            safe = _safe_name(company.name)
            archive.writestr(f"{safe}/{safe}.xlsx", export_company_excel(company, period).getvalue())
            archive.writestr(f"{safe}/{safe}.pdf", export_company_pdf(company, period).getvalue())
    output.seek(0)
    return output


def export_single_company_zip(company, period="billing"):
    output, safe = io.BytesIO(), _safe_name(company.name)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{safe}.xlsx", export_company_excel(company, period).getvalue())
        archive.writestr(f"{safe}.pdf", export_company_pdf(company, period).getvalue())
    output.seek(0)
    return output


def import_cards(file_path):
    frame = pd.read_excel(file_path, dtype={"Number": str})
    frame = frame.loc[:, ~frame.columns.astype(str).str.contains(r"^Unnamed")]
    frame.columns = frame.columns.astype(str).str.strip()
    _require_columns(frame, ["Company", "Name", "Number", "EIK"], "карти")
    created = updated = skipped = 0
    with db_transaction.atomic():
        for _, row in frame.iterrows():
            name = normalize_text(row["Company"])
            eik = _clean_identifier(row["EIK"])
            card_number = re.sub(r"\D", "", _clean_identifier(row["Number"]))
            if not name or not card_number:
                skipped += 1
                continue
            company, _ = Company.objects.get_or_create(name=name, defaults={"eik": eik})
            company.eik = eik
            company.is_twice_monthly = name in TWICE_MONTHLY_COMPANIES
            company.note = COMPANY_NOTES.get(name, company.note or "")
            company.save()
            _, was_created = Card.objects.update_or_create(card_number=card_number, defaults={
                "company": company, "vehicle": "" if pd.isna(row["Name"]) else str(row["Name"]).strip(),
            })
            created += int(was_created)
            updated += int(not was_created)
        relink_data()
    return ImportResult(created, updated, skipped)


def import_prices(file_path):
    frame = pd.read_excel(file_path)
    frame.columns = frame.columns.astype(str).str.strip()
    mapping = {"ДАТА": "date", "Date": "date", "ФИРМА": "company", "Company": "company", "ЕИК": "eik", "EIK": "eik",
               "ПРОДУКТ": "product", "Product": "product", "ЕКО_ЦЕНА": "eko_price", "EKO Price": "eko_price", "EKO_Price": "eko_price",
               "МАРЖ": "margin", "Margin": "margin", "КРАЙНА_ЦЕНА": "final_price", "Final Price": "final_price",
               "Final_Price": "final_price", "ОТСТЪПКА": "discount", "Discount": "discount"}
    frame.rename(columns={column: mapping[column] for column in frame.columns if column in mapping}, inplace=True)
    _require_columns(frame, ["date", "company", "eik", "product", "final_price"], "цени")
    created = updated = skipped = 0
    with db_transaction.atomic():
        for _, row in frame.iterrows():
            parsed = pd.to_datetime(row["date"], dayfirst=True, errors="coerce")
            name, eik, product = normalize_text(row["company"]), _clean_identifier(row["eik"]), normalize_text(row["product"])
            if pd.isna(parsed) or not name or not product or pd.isna(row["final_price"]):
                skipped += 1
                continue
            companies = list(Company.objects.filter(eik=eik)) if eik else []
            if not companies:
                company, _ = Company.objects.get_or_create(name=name, defaults={"eik": eik})
                companies = [company]
            for company in companies:
                _, was_created = Price.objects.update_or_create(date=parsed.date(), company=company, product=product, defaults={
                    "final_price": _decimal(row["final_price"]), "eko_price": _decimal(row.get("eko_price")),
                    "margin": _decimal(row.get("margin")), "discount": _decimal(row.get("discount")),
                    "company_name_tmp": name, "company_eik_tmp": eik,
                })
                created += int(was_created)
                updated += int(not was_created)
    return ImportResult(created, updated, skipped)


def _parse_time(value):
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.time()


def import_transactions(file_path, replace=True):
    frame = pd.read_excel(file_path, dtype={"Number": str})
    frame.columns = frame.columns.astype(str).str.strip()
    _require_columns(frame, ["Plant", "Name", "Number", "Material", "Date", "Bill.qty", "FinPr", "Tot Amount"], "транзакции")
    cards, records, skipped = {card.card_number: card for card in Card.objects.all()}, [], 0
    for _, row in frame.iterrows():
        parsed_date = pd.to_datetime(row["Date"], dayfirst=True, errors="coerce")
        card_number = re.sub(r"\D", "", _clean_identifier(row["Number"]))
        qty = _decimal(row["Bill.qty"], None)
        material = normalize_text(re.sub(r"^\d{6,}\s*", "", str(row["Material"])))
        if pd.isna(parsed_date) or not card_number or qty is None or qty <= ZERO or not material:
            skipped += 1
            continue
        km = _decimal(row.get("Km stand"), None)
        records.append(Transaction(
            plant="" if pd.isna(row["Plant"]) else str(row["Plant"]).strip(), card_number=card_number,
            card=cards.get(card_number), material=material, date=parsed_date.date(), bill_qty=qty,
            bill_qty2="" if pd.isna(row.get("Bill.qty.1")) else str(row.get("Bill.qty.1")).strip(),
            price=_decimal(row["FinPr"]), amount=_decimal(row["Tot Amount"]), auth_time=_parse_time(row.get("Auth.time")),
            km_stand=int(km) if km is not None else None,
            billing_document="" if pd.isna(row.get("Billing Document")) else str(row.get("Billing Document")).strip(),
        ))
    with db_transaction.atomic():
        if replace:
            Transaction.objects.all().delete()
        Transaction.objects.bulk_create(records, batch_size=500)
    return ImportResult(len(records), 0, skipped)


def relink_data():
    cards = {item.card_number: item for item in Card.objects.all()}
    transactions = []
    for item in Transaction.objects.filter(card__isnull=True):
        if item.card_number in cards:
            item.card = cards[item.card_number]
            transactions.append(item)
    if transactions:
        Transaction.objects.bulk_update(transactions, ["card"], batch_size=500)
    companies_eik = {item.eik: item for item in Company.objects.exclude(eik="")}
    companies_name = {item.name: item for item in Company.objects.all()}
    prices = []
    for item in Price.objects.filter(company__isnull=True):
        company = companies_eik.get(item.company_eik_tmp) or companies_name.get(item.company_name_tmp)
        if company:
            item.company = company
            prices.append(item)
    if prices:
        Price.objects.bulk_update(prices, ["company"], batch_size=500)
    return len(transactions), len(prices)
