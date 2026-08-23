import pandas as pd
import re
import io
import os
import zipfile
import numpy as np
from datetime import datetime, date, timedelta
from .models import Company, Card, Price, Transaction
from django.db import transaction as db_transaction
from django.conf import settings
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Път до Arial шрифт за PDF
PDF_FONT_PATH = "C:/Windows/Fonts/arial.ttf"
PDF_FONT_NAME = "Arial"


def register_pdf_font():
    """Регистрира Unicode font за PDF, за да се показва кирилица правилно."""
    if os.path.exists(PDF_FONT_PATH):
        try:
            pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, PDF_FONT_PATH))
            return True
        except:
            return False
    return False


HAS_UNICODE_FONT = register_pdf_font()

TWICE_MONTHLY_COMPANIES = [
    "БКС ДОЛНИ ЧИФЛИК ЕООД",
    "МЕРКУРИЙ ПРОИЗВОДСТВО И ПАКЕТАЖ АД",
    "СПЕДСТРОЙ ООД",
    "ФУУДС ТРЕЙД ЕООД",
    "СИЙД ЕКСПРЕС ЕООД",
    "ФЕНИКС ИМПОРТ М ЕООД",
    "ОП ДЕЗИНФЕКЦИЯ, ДЕЗИНСЕКЦИЯ, ДЕРАТИЗАЦИЯ",
    "ОП КОМПЛЕКС ЗА ДЕТСКО ХРАНЕНЕ",
    "КСУДПЛУ СВ. ЙОАН ЗЛАТОУСТ",
    "РАЙОН АСПАРУХОВО",
    "ОП ИНВЕСТИЦИОННА ПОЛИТИКА",
    "OП ТАСРУД",
    "ОП ЗООПАРК-СЦ ВАРНА",
    "ОП СПОРТ-ВАРНА",
    "РАЙОН МЛАДОСТ - ОБЩИНА ВАРНА",
    "РАЙОН ВЛАДИСЛАВ ВАРНЕНЧИК - ОБЩИНА ВАРНА",
    "КСУБЛС",
    "КСУДС",
    "КМЕТСТВО КАМЕНАР",
    "КМЕТСТВО КОНСТАНТИНОВО",
    "КМЕТСТВО ТОПОЛИ",
    "КСУВХ ГЕРГАНА ДСХ И ДПЛФУ",
    "КСУДМ",
    "ОП УПРАВЛЕНИЕ НА ПРОЕКТИ И ОЗЕЛЕНЯВАНЕ",
    "ДОМАШЕН СОЦИАЛЕН ПАТРОНАЖ",
    "РАЙОН ПРИМОРСКИ – ОБЩИНА ВАРНА",
    "ОБЩИНА ВАРНА - ДИРЕКЦИЯ СПОРТ",
    "ОБЩИНА ВАРНА - КМЕТСТВО КАЗАШКО",
    "ОБЩИНА ВАРНА % 1 - АВТОПАРК",
    "ОБЩИНА ВАРНА % 2 - ОБЩИНСКА ПОЛИЦИЯ",
    "ОБЩИНА ВАРНА % 3 - РАЗХОД ПО ПРОЕКТ ОИЦ ВАРНА",
    "ОБЩИНА ВАРНА % 4 - УЧИЛИЩЕН АВТОБУС",
    "КМЕТСТВО ЗВЕЗДИЦА",
    "ОП ОБЩИНСКИ ПАРКИНГИ И СИНЯ ЗОНА",
    "ОБЩИНА ВАРНА % 5 - ПДГ",
    "ОБЩИНА ВАРНА % 5 - ДИРЕКЦИЯ КУЛТУРА",
    "ОБЩИНА ВАРНА % 6 - УА",
    "РАЙОН ОДЕСОС",
]

COMPANY_NOTES = {
    "ОБЩИНА ВАРНА % 5 - ПДГ": "Разходът е по проект №BG05SFPR002-2.012-0094-СО1 „Иновативни здравно-социални услуги в домашна среда“ по процедура BG05SFPR002-2.012 „Иновативни здравно-социални услуги“, Програма „Развитие на човешките ресурси” 2021-2027",
}


def get_transaction_data_period():
    """
    Връща най-ранната и най-късната дата от текущо заредените транзакции.

    Така отчетният период се определя от качения transaction файл,
    а не от днешната дата.
    """
    dates = Transaction.objects.exclude(date__isnull=True).order_by('date').values_list('date', flat=True)

    start_date = dates.first()
    end_date = dates.last()

    return start_date, end_date


def get_invoice_period(period='full'):
    """
    Връща отчетния период според текущо заредените транзакции.

    period:
        'first'   -> 01-15 за месеца на последната транзакция
        'second'  -> 16-края на месеца на последната транзакция
        'full'    -> целият наличен период от transaction файла
        'auto'    -> автоматично избира първа или втора половина
                     според последната дата в transaction файла

    Периодът се определя от данните в Transaction, а не от date.today().
    """
    data_start, data_end = get_transaction_data_period()

    if data_start is None or data_end is None:
        return None, None

    if period not in ('first', 'second', 'full', 'auto'):
        period = 'full'

    if period == 'full':
        return data_start, data_end

    report_date = data_end

    if period == 'first':
        start_date = report_date.replace(day=1)
        end_date = report_date.replace(day=15)
        return start_date, end_date

    if period == 'second':
        start_date = report_date.replace(day=16)
        first_day_next_month = (report_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = first_day_next_month - timedelta(days=1)
        return start_date, end_date

    # AUTO:
    # Ако последната дата във файла е до 15-то число -> 01-15.
    # Ако е след 15-то число -> 16-края на месеца.
    if report_date.day <= 15:
        start_date = report_date.replace(day=1)
        end_date = report_date.replace(day=15)
    else:
        start_date = report_date.replace(day=16)
        first_day_next_month = (report_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = first_day_next_month - timedelta(days=1)

    return start_date, end_date


from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


# Опит за зареждане на кирилски шрифт (ако е наличен в системата)
# Обикновено в Windows има Arial, но за PDF трябва .ttf файл.
# За целите на прототипа ще използваме стандартни шрифтове, но кирилицата може да е проблем без външен шрифт.

def get_company_report_data(company, period='billing'):
    """
    Връща транзакциите и обобщенията за фирмата.

    period:
        'billing' -> режим за фактуриране:
                     - месечните фирми -> целият наличен период
                     - фирмите с is_twice_monthly=True -> автоматично
                       първа или втора половина според качения файл
        'first'   -> 01-15 за всички фирми
        'second'  -> 16-края на месеца за всички фирми
        'full'    -> целият наличен период за всички фирми
    """
    transactions = Transaction.objects.filter(card__company=company).order_by('date')

    if period == 'billing':
        if company.is_twice_monthly:
            start_date, end_date = get_invoice_period('auto')
        else:
            start_date, end_date = get_invoice_period('full')
    else:
        start_date, end_date = get_invoice_period(period)

    if start_date is None or end_date is None:
        transactions = transactions.none()
    else:
        transactions = transactions.filter(date__range=(start_date, end_date))

    data = []
    total_eko = 0
    total_gta = 0
    total_qty = 0
    total_profit = 0

    for t in transactions:
        price_obj = Price.objects.filter(
            company=company,
            product__iexact=t.material,
            date__lte=t.date
        ).order_by('-date', '-id').first()

        final_price = t.price
        base_price = None
        cost_price = None
        discount = 0
        margin = 0

        if price_obj:
            discount = price_obj.discount
            base_price = price_obj.final_price
            cost_price = price_obj.eko_price
            margin = price_obj.margin

            if discount > 0:
                final_price = round(max(0, float(t.price) - float(discount)), 2)
            elif base_price is not None:
                final_price = round(float(base_price), 2)
            else:
                final_price = round(float(t.price), 2)
        else:
            final_price = round(float(t.price), 2)

        eko_total = round(round(float(t.bill_qty), 2) * round(float(t.price), 2), 2)
        gta_total = round(round(float(t.bill_qty), 2) * float(final_price), 2)

        # Печалба се изчислява според правилата:
        # 1. Фирми с МАРЖ: количество * марж
        # 2. Фирми с ОТСТЪПКА: количество * (Цена_от_транзакция - ЕКО_ЦЕНА_от_файл_цени - Отстъпка)
        # 3. Специално за E GAS: печалбата е загуба равна на отстъпката (Количество * -Отстъпка)

        material_norm = normalize_text(t.material)
        if 'Е GАS' in material_norm:
            profit = round(float(t.bill_qty), 2) * (float(discount) * -1)
        elif margin > 0:
            profit = round(float(t.bill_qty), 2) * float(margin)
        elif discount > 0:
            # Отстъпка: Количество * ( (Цена от транзакция - Отстъпка) - ЕКО Цена от ценова листа )
            if cost_price and float(cost_price) > 0:
                profit = round(float(t.bill_qty), 2) * ((float(t.price) - float(discount)) - float(cost_price))
            else:
                # Ако нямаме ЕКО цена в ценовата листа, не можем да сметнем печалбата правилно по тази формула
                # Връщаме 0 или старата логика като fallback
                profit = 0
        elif cost_price and float(cost_price) > 0:
            # Fallback ако няма нито марж, нито отстъпка, но има ЕКО цена
            profit = (float(final_price) - float(cost_price)) * round(float(t.bill_qty), 2)
        elif base_price is not None:
            profit = (float(final_price) - float(base_price)) * round(float(t.bill_qty), 2)
        else:
            profit = 0

        profit = round(profit, 2)

        data.append({
            'date': t.date,
            'plant': t.plant,
            'card': t.card_number,
            'vehicle': t.card.vehicle if t.card else "",
            'material': t.material,
            'qty': round(float(t.bill_qty), 2),
            'qty_type': t.bill_qty2,
            'gta_price': final_price,
            'discount': discount,
            'margin': margin,
            'profit': profit,
            'gta_total': gta_total,
            'eko_price': round(float(t.price), 2),
            'eko_total': eko_total,
            'auth_time': t.auth_time,
            'km_stand': t.km_stand,
            'billing_doc': t.billing_document
        })

        total_eko += eko_total
        total_gta += gta_total
        total_qty += round(float(t.bill_qty), 2)
        total_profit += profit

    return data, round(total_qty, 2), round(total_eko, 2), round(total_gta, 2), round(total_profit, 2)


def export_company_pdf(company, period='billing'):
    data, t_qty, t_eko, t_gta, t_profit = get_company_report_data(company, period)
    output = io.BytesIO()

    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30,
                            bottomMargin=30)
    styles = getSampleStyleSheet()

    if HAS_UNICODE_FONT:
        styles['Title'].fontName = PDF_FONT_NAME
        styles['Normal'].fontName = PDF_FONT_NAME
        font_to_use = PDF_FONT_NAME
    else:
        font_to_use = 'Helvetica'

    elements = []

    # Title
    elements.append(Paragraph(f"<b>{company.name}</b>", styles['Title']))
    if company.note:
        elements.append(Paragraph(f"Забележка: {company.note}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Table data
    if data:
        table_data = [['Дата', 'Карта', 'Материал', 'Литри', 'GTA цена', 'Сума GTA', 'ЕКО цена', 'Сума ЕКО']]
        for r in data:
            table_data.append([
                str(r['date']),
                r['card'],
                r['material'][:20],  # Режем дълги имена
                f"{r['qty']:.2f}",
                f"{r['gta_price']:.2f}",
                f"{r['gta_total']:.2f}",
                f"{r['eko_price']:.2f}",
                f"{r['eko_total']:.2f}"
            ])

        table_data.append(['ОБЩО', '', '', f"{t_qty:.2f}", '', f"{t_gta:.2f}", '', f"{t_eko:.2f}"])

        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.yellow),
            ('FONTNAME', (0, 0), (-1, -1), font_to_use),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Няма данни за избрания период.", styles['Normal']))

    doc.build(elements)
    output.seek(0)
    return output


def export_company_excel(company, period='billing'):
    data, t_qty, t_eko, t_gta, t_profit = get_company_report_data(company, period)
    output = io.BytesIO()

    df = pd.DataFrame(data)
    if not df.empty:
        # Първоначални колони от get_company_report_data
        # ['date', 'plant', 'card', 'vehicle', 'material', 'qty', 'qty_type', 'gta_price', 'discount', 'margin', 'profit', 'gta_total', 'eko_price', 'eko_total', 'auth_time', 'km_stand', 'billing_doc']

        # Реорганизираме колоните: GTA преди EKO
        df = df[[
            'date', 'plant', 'card', 'vehicle', 'material', 'qty', 'qty_type',
            'gta_price', 'discount', 'margin', 'profit', 'gta_total', 'eko_price', 'eko_total',
            'auth_time', 'km_stand', 'billing_doc'
        ]]

        df.columns = [
            'Дата', 'Станция', 'Име', 'Номер на карта', 'Име на артикул', 'Литри', 'Тип количество',
            'GTA цена', 'Отстъпка', 'Марж', 'Печалба', 'Сума по GTA цена', 'ЕКО цена', 'Сума по ЕКО цена',
            'Час', 'Километри', 'Billing Document'
        ]
        # Премахваме колоните, които не трябва да се виждат от клиентите
        df_for_excel = df.drop(columns=['Отстъпка', 'Марж', 'Печалба'])
    else:
        df_for_excel = df

    # Summary by product
    summary = []
    if not df_for_excel.empty:
        summary_df = df_for_excel.groupby('Име на артикул').agg({
            'Литри': 'sum',
            'Сума по GTA цена': 'sum',
            'Сума по ЕКО цена': 'sum'
        }).reset_index()

        # Sort by liters descending to match Jupyter
        summary_df = summary_df.sort_values(by='Литри', ascending=False)

        for _, row in summary_df.iterrows():
            avg_gta = float(row['Сума по GTA цена']) / float(row['Литри']) if float(row['Литри']) != 0 else 0
            summary.append({
                'Продукт': row['Име на артикул'],
                'Общо литри': round(float(row['Литри']), 2),
                'Средна GTA цена': round(avg_gta, 4),
                'Сума GTA': round(float(row['Сума по GTA цена']), 2),
                'Сума ЕКО': round(float(row['Сума по ЕКО цена']), 2)
            })

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        sheet_name = company.name[:31]
        df_for_excel.to_excel(writer, index=False, sheet_name=sheet_name, startrow=3 if company.note else 0)
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        header_format = workbook.add_format({'bold': True, 'bg_color': '#D9EAF7', 'border': 1, 'align': 'center'})
        num_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        price_format = workbook.add_format({'num_format': '#,##0.0000', 'border': 1})
        amount_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        text_format = workbook.add_format({'border': 1})

        if company.note:
            worksheet.write(0, 0, f"Забележка: {company.note}",
                            workbook.add_format({'bold': True, 'font_color': 'red'}))
            start_row = 3
        else:
            start_row = 0

        # Настройка на ширина на колоните
        worksheet.set_column('A:A', 12)  # Дата
        worksheet.set_column('B:B', 20)  # Станция
        worksheet.set_column('C:C', 15)  # Име
        worksheet.set_column('D:D', 18)  # Номер на карта
        worksheet.set_column('E:E', 25)  # Име на артикул
        worksheet.set_column('F:F', 12)  # Литри
        worksheet.set_column('G:G', 15)  # Тип количество
        worksheet.set_column('H:H', 15)  # GTA цена
        worksheet.set_column('I:I', 15)  # Сума GTA
        worksheet.set_column('J:J', 15)  # ЕКО цена
        worksheet.set_column('K:K', 15)  # Сума ЕКО
        worksheet.set_column('L:N', 12)  # Час, Километри, Billing Document

        for col_num, value in enumerate(df_for_excel.columns.values):
            worksheet.write(start_row, col_num, value, header_format)

        # Прилагане на бордове за всички клетки с данни в главната таблица
        for r_idx, row_data in df_for_excel.iterrows():
            r = start_row + 1 + r_idx
            worksheet.write(r, 0, str(row_data['Дата']), text_format)
            worksheet.write(r, 1, str(row_data['Станция']), text_format)
            worksheet.write(r, 2, str(row_data['Име']), text_format)
            worksheet.write(r, 3, str(row_data['Номер на карта']), text_format)
            worksheet.write(r, 4, str(row_data['Име на артикул']), text_format)
            worksheet.write_number(r, 5, float(row_data['Литри']), num_format)
            worksheet.write(r, 6, str(row_data['Тип количество']), text_format)
            worksheet.write_number(r, 7, float(row_data['GTA цена']), price_format)
            worksheet.write_number(r, 8, float(row_data['Сума по GTA цена']), amount_format)
            worksheet.write_number(r, 9, float(row_data['ЕКО цена']), price_format)
            worksheet.write_number(r, 10, float(row_data['Сума по ЕКО цена']), amount_format)
            worksheet.write(r, 11, str(row_data['Час'] or ""), text_format)
            km_value = row_data.get('Километри')

            if pd.isna(km_value):
                km_value = ""

            worksheet.write(r, 12, km_value, text_format)
            worksheet.write(r, 13, str(row_data['Billing Document']), text_format)

        # Write summary
        summary_start_row = len(df_for_excel) + start_row + 2
        worksheet.write(summary_start_row, 0, f"Общи литри по продукт / {company.name}",
                        workbook.add_format({'bold': True, 'font_size': 14}))

        summary_headers = ['Продукт', 'Общо литри', 'Средна GTA цена (€)', 'Сума GTA (€)', 'Сума ЕКО (€)']
        for i, h in enumerate(summary_headers):
            worksheet.write(summary_start_row + 1, i, h, header_format)

        for i, s_row in enumerate(summary):
            worksheet.write(summary_start_row + 2 + i, 0, s_row['Продукт'], text_format)
            worksheet.write(summary_start_row + 2 + i, 1, s_row['Общо литри'], num_format)
            worksheet.write(summary_start_row + 2 + i, 2, s_row['Средна GTA цена'], price_format)
            worksheet.write(summary_start_row + 2 + i, 3, s_row['Сума GTA'], amount_format)
            worksheet.write(summary_start_row + 2 + i, 4, s_row['Сума ЕКО'], amount_format)

        # Total row in summary
        last_s_row = summary_start_row + 2 + len(summary)
        total_format_amount = workbook.add_format(
            {'bold': True, 'bg_color': '#FFFF66', 'border': 1, 'num_format': '#,##0.00'})
        total_format_qty = workbook.add_format(
            {'bold': True, 'bg_color': '#FFFF66', 'border': 1, 'num_format': '#,##0.00'})
        worksheet.write(last_s_row, 0, 'Общо', total_format_amount)
        worksheet.write(last_s_row, 1, round(t_qty, 2), total_format_qty)
        worksheet.write(last_s_row, 2, "", total_format_amount)
        worksheet.write(last_s_row, 3, round(t_gta, 2), total_format_amount)
        worksheet.write(last_s_row, 4, round(t_eko, 2), total_format_amount)

    output.seek(0)
    return output


def export_all_companies_zip(period='billing'):
    companies = Company.objects.all()
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for company in companies:
            # Премахваме невалидни символи от името на фирмата за име на папка
            safe_name = re.sub(r'[\\/*?:"<>|]', "_", company.name)

            # Excel
            excel_data = export_company_excel(company, period)
            excel_filename = f"{safe_name}/{safe_name}.xlsx"
            zip_file.writestr(excel_filename, excel_data.getvalue())

            # PDF
            pdf_data = export_company_pdf(company, period)
            pdf_filename = f"{safe_name}/{safe_name}.pdf"
            zip_file.writestr(pdf_filename, pdf_data.getvalue())

    zip_buffer.seek(0)
    return zip_buffer


def export_single_company_zip(company, period='billing'):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Премахваме невалидни символи от името на фирмата за име на папка
        safe_name = re.sub(r'[\\/*?:"<>|]', "_", company.name)

        # Excel
        excel_data = export_company_excel(company, period)
        excel_filename = f"{safe_name}.xlsx"
        zip_file.writestr(excel_filename, excel_data.getvalue())

        # PDF
        pdf_data = export_company_pdf(company, period)
        pdf_filename = f"{safe_name}.pdf"
        zip_file.writestr(pdf_filename, pdf_data.getvalue())

    zip_buffer.seek(0)
    return zip_buffer


def normalize_text(text):
    if not text:
        return text
    # Премахваме излишните интервали
    text = re.sub(r"\s+", " ", text).strip()

    # Нормализиране на специфични случаи за Община Варна (премахване на % ако липсва в единия вариант)
    # Ако има "ОБЩИНА ВАРНА %", го превръщаме в "ОБЩИНА ВАРНА", за да съвпадат
    # Но потребителят иска първият запис (с %) да е валиден.
    # Затова ще превръщаме вариантите без % във варианти с %.
    if "ОБЩИНА ВАРНА" in text.upper() and "%" not in text:
        text = re.sub(r"(ОБЩИНА ВАРНА)\s+(\d+)", r"\1 % \2", text, flags=re.IGNORECASE)

    # Списък за замяна на латински символи, които изглеждат като кирилски, и обратно
    # Нормализираме всичко към КИРИЛИЦА
    replacements = {
        'O': 'О',  # Latin O to Cyrillic O
        'E': 'Е',  # Latin E to Cyrillic E
        'A': 'А',  # Latin A to Cyrillic A
        'P': 'Р',  # Latin P to Cyrillic P
        'C': 'С',  # Latin C to Cyrillic C
        'M': 'М',  # Latin M to Cyrillic M
        'T': 'Т',  # Latin T to Cyrillic T
        'B': 'В',  # Latin B to Cyrillic B
        'H': 'Н',  # Latin H to Cyrillic H
        'K': 'К',  # Latin K to Cyrillic K
        'X': 'Х',  # Latin X to Cyrillic X
        # Добавяме и малки латински към големи кирилски за всеки случай
        'o': 'О', 'e': 'Е', 'a': 'А', 'p': 'Р', 'c': 'С', 'm': 'М', 't': 'Т', 'b': 'В', 'h': 'Н', 'k': 'К', 'x': 'Х'
    }
    # Нормализираме до големи букви
    text = text.upper()
    for lat, cyr in replacements.items():
        text = text.replace(lat, cyr)
    return text.strip()


def import_cards(file_path):
    df = pd.read_excel(file_path, dtype={"Number": str})
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df.columns = df.columns.str.strip()

    with db_transaction.atomic():
        for _, row in df.iterrows():
            company_name = normalize_text(str(row['Company']))
            eik = str(row['EIK']).strip().replace(".0", "")
            card_number = str(row['Number']).strip().replace(".0", "")
            vehicle = str(row['Name']).strip() if pd.notna(row['Name']) else ""

            is_twice = company_name in TWICE_MONTHLY_COMPANIES
            note = COMPANY_NOTES.get(company_name, "")

            company, created = Company.objects.get_or_create(
                name=company_name,
                defaults={'eik': eik, 'is_twice_monthly': is_twice, 'note': note}
            )
            if not created:
                # Обновяваме ЕИК и настройките ако фирмата вече съществува
                company.eik = eik
                company.is_twice_monthly = is_twice
                company.note = note
                company.save()

            Card.objects.update_or_create(
                card_number=card_number,
                defaults={'company': company, 'vehicle': vehicle if vehicle.lower() != 'nan' else ""}
            )

        # Автоматично свързване на данни след импорт на карти
        relink_data()


def relink_data():
    """Свързва транзакциите с картите и цените с фирмите, ако са били разкачени."""
    cards_map = {c.card_number: c for c in Card.objects.all()}

    # Релинк на транзакции
    transactions_to_update = Transaction.objects.filter(card__isnull=True)
    count_t = 0
    for t in transactions_to_update:
        if t.card_number in cards_map:
            t.card = cards_map[t.card_number]
            t.save()
            count_t += 1

    # Релинк на цени
    prices_to_relink = Price.objects.filter(company__isnull=True)
    count_p = 0

    # Вземаме всички фирми в паметта за по-бързо търсене
    companies_by_eik = {c.eik: c for c in Company.objects.all() if c.eik}
    companies_by_name = {c.name: c for c in Company.objects.all()}

    for p in prices_to_relink:
        company = None
        if p.company_eik_tmp and p.company_eik_tmp in companies_by_eik:
            company = companies_by_eik[p.company_eik_tmp]
        if not company and p.company_name_tmp and p.company_name_tmp in companies_by_name:
            company = companies_by_name[p.company_name_tmp]

        if company:
            p.company = company
            p.save()
            count_p += 1

    return count_t, count_p


def import_prices(file_path):
    df = pd.read_excel(file_path)
    df.columns = df.columns.str.strip()

    # Mapping known columns to support both Bulgarian and English headers
    column_mapping = {
        'ДАТА': 'date', 'Date': 'date',
        'ФИРМА': 'company', 'Company': 'company',
        'ЕИК': 'eik', 'EIK': 'eik',
        'ПРОДУКТ': 'product', 'Product': 'product',
        'МАРЖ': 'margin', 'Margin': 'margin',
        'КРАЙНА_ЦЕНА': 'final_price', 'Final Price': 'final_price', 'Final_Price': 'final_price',
        'ЕКО_ЦЕНА': 'eko_price', 'EKO Price': 'eko_price', 'EKO_Price': 'eko_price',
        'ОТСТЪПКА': 'discount', 'Discount': 'discount'
    }

    # Rename columns based on mapping if they exist
    new_columns = {}
    for col in df.columns:
        if col in column_mapping:
            new_columns[col] = column_mapping[col]
    df.rename(columns=new_columns, inplace=True)

    with db_transaction.atomic():
        for _, row in df.iterrows():
            if pd.isna(row.get('date')) or pd.isna(row.get('final_price')):
                # Try fallback if rename didn't catch it
                if pd.isna(row.get('ДАТА')) or pd.isna(row.get('КРАЙНА_ЦЕНА')):
                    continue
                else:
                    date_val = row.get('ДАТА')
                    final_price_val = row.get('КРАЙНА_ЦЕНА')
            else:
                date_val = row.get('date')
                final_price_val = row.get('final_price')

            date = pd.to_datetime(date_val).date()

            company_name_val = row.get('company', row.get('ФИРМА'))
            company_name = normalize_text(str(company_name_val))

            eik_val = row.get('eik', row.get('ЕИК', ''))
            eik = str(eik_val).strip().replace(".0", "")

            product_val = row.get('product', row.get('ПРОДУКТ'))
            product = normalize_text(str(product_val))

            try:
                margin = float(row.get('margin', row.get('МАРЖ', 0)))
                if np.isnan(margin):
                    margin = 0
            except (ValueError, TypeError):
                margin = 0

            try:
                final_price = float(final_price_val)
                if np.isnan(final_price):
                    continue
            except (ValueError, TypeError):
                continue

            try:
                eko_price = float(row.get('eko_price', row.get('ЕКО_ЦЕНА', 0)))
                if np.isnan(eko_price):
                    eko_price = 0
            except (ValueError, TypeError):
                eko_price = 0

            try:
                discount = float(row.get('discount', row.get('ОТСТЪПКА', 0)))
                if np.isnan(discount):
                    discount = 0
            except (ValueError, TypeError):
                discount = 0

            # Намираме всички фирми, които имат този ЕИК
            target_companies = Company.objects.filter(eik=eik)

            # Ако няма намерени фирми по ЕИК, може би фирмата е нова или ЕИК е грешен
            # В такъв случай създаваме/вземаме основната фирма по име
            if not target_companies.exists():
                company, _ = Company.objects.get_or_create(name=company_name, defaults={'eik': eik})
                target_companies = [company]

            for company in target_companies:
                Price.objects.update_or_create(
                    date=date,
                    company=company,
                    product=product,
                    defaults={
                        'final_price': final_price,
                        'eko_price': eko_price,
                        'margin': margin,
                        'discount': discount,
                        'company_name_tmp': company_name,
                        'company_eik_tmp': eik
                    }
                )


def import_transactions(file_path):
    df = pd.read_excel(file_path, dtype={"Number": str})
    df.columns = df.columns.str.strip()

    # Предварителна обработка на колоните за дата и час за целия DataFrame
    if 'Date' in df.columns:
        df['Date_parsed'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
    else:
        df['Date_parsed'] = pd.NaT

    if 'Auth.time' in df.columns:
        # Опит за парсване на час. Ако е вече datetime (от Excel), вземаме само часа.
        def parse_time(val):
            if pd.isna(val): return None
            try:
                dt = pd.to_datetime(val, errors='coerce')
                return dt.time() if pd.notna(dt) else None
            except:
                return None

        df['Time_parsed'] = df['Auth.time'].apply(parse_time)
    else:
        df['Time_parsed'] = None

    with db_transaction.atomic():
        for _, row in df.iterrows():
            # Задължителни полета
            material_raw = row.get('Material')
            number_raw = row.get('Number')
            qty_raw = row.get('Bill.qty')
            date_parsed = row.get('Date_parsed')

            if pd.isna(material_raw) or pd.isna(number_raw) or pd.isna(qty_raw) or pd.isna(date_parsed):
                continue

            # Базово почистване по логиката от ноутбука
            material = normalize_text(re.sub(r'^\d{6,}\s*', '', str(material_raw)))
            card_number = re.sub(r"\D", "", str(number_raw))

            try:
                qty = float(qty_raw)
                if np.isnan(qty) or qty <= 0:
                    continue
            except (ValueError, TypeError):
                continue

            if not card_number:
                continue

            auth_time = row.get('Time_parsed')

            try:
                km_stand_raw = row.get('Km stand')
                if pd.notna(km_stand_raw) and str(km_stand_raw).lower() != 'nan':
                    km_stand = int(float(km_stand_raw))
                else:
                    km_stand = None
            except:
                km_stand = None

            card = Card.objects.filter(card_number=card_number).first()

            try:
                price = float(row.get('FinPr', 0))
                if np.isnan(price): price = 0

                amount = float(row.get('Tot Amount', 0))
                if np.isnan(amount): amount = 0
            except (ValueError, TypeError):
                price = 0
                amount = 0

            Transaction.objects.create(
                plant=str(row.get('Plant', "")).strip() if pd.notna(row.get('Plant')) and str(
                    row.get('Plant')).lower() != 'nan' else "",
                card_number=card_number,
                card=card,
                material=material,
                date=date_parsed.date(),
                bill_qty=qty,
                bill_qty2=str(row.get('Bill.qty.1', "")).strip() if pd.notna(row.get('Bill.qty.1')) and str(
                    row.get('Bill.qty.1')).lower() != 'nan' else "",
                price=price,
                amount=amount,
                auth_time=auth_time,
                km_stand=km_stand,
                billing_document=str(row.get('Billing Document', "")).strip() if pd.notna(
                    row.get('Billing Document')) and str(row.get('Billing Document')).lower() != 'nan' else ""
            )