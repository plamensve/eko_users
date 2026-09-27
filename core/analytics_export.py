"""Management Excel workbook based on the supplied five-sheet report generator.

Source data comes from the same pricing calculations as the application analytics.
"""

import io
import re

import pandas as pd

from .models import Company
from .services import normalize_product_key
from .utils import get_company_report_data

# ============================================================
# SETTINGS
# ============================================================

# Input Excel file containing one sheet per company.
INPUT_FILE = "../A_FINAL_RESULT/eko_transactions.xlsx"

# The output file is saved in the current Jupyter working directory.

# The source workbook has its column headers on Excel row 3.
# In pandas, rows are zero-based, therefore header=2.
EXCEL_HEADER_ROW = 2

PRODUCT_COLUMN = "Име на артикул"
LITERS_COLUMN = "Литри"
AMOUNT_COLUMN = "Сума по GTA цена"
BASE_PRICE_COLUMN = "Базова ЕКО цена"
EKO_PRICE_COLUMN = "ЕКО цена"
DISCOUNT_COLUMN = "Отстъпка"
MARGIN_COLUMN = "Марж"
PROFIT_COLUMN = "Печалба"
DATE_COLUMNS = ["Дата", "Date"]

SUMMARY_SHEET_NAME = "Summary"
DASHBOARD_SHEET_NAME = "Dashboard"
TOTAL_SHEET_NAME = "Total"
TOP_CLIENTS_SHEET_NAME = "Top Clients"
ANALYSIS_DATASET_SHEET_NAME = "Analysis Dataset"

TOP_CLIENTS_COUNT = 10


# ============================================================
# PRODUCTS INCLUDED IN THE FINAL REPORT
# ============================================================

PRODUCTS = [
    {
        "output_name": "Diesel EKONOMY",
        "feature_prefix": "diesel_ekonomy",
        "aliases": {
            "DIESEL EKONOMY",
        },
    },
    {
        "output_name": "95 EKONOMY Unleaded",
        "feature_prefix": "unleaded_95_ekonomy",
        "aliases": {
            "95 EKONOMY UNLEADED",
        },
    },
    {
        "output_name": "Diesel Double Filtered",
        "feature_prefix": "diesel_double_filtered",
        "aliases": {
            "DIESEL DOUBLE FILTERED",
        },
    },
    {
        "output_name": "EKO Racing 100",
        "feature_prefix": "eko_racing_100",
        "aliases": {
            "EKO RACING 100",
        },
    },
    {
        "output_name": "E Gas LPG",
        "feature_prefix": "e_gas_lpg",
        "aliases": {
            "E GAS LPG",
        },
    },
]


# ============================================================
# BULGARIAN MONTH NAMES
# ============================================================

BULGARIAN_MONTHS = {
    1: "Януари",
    2: "Февруари",
    3: "Март",
    4: "Април",
    5: "Май",
    6: "Юни",
    7: "Юли",
    8: "Август",
    9: "Септември",
    10: "Октомври",
    11: "Ноември",
    12: "Декември",
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def normalize_text(value):
    """Normalize text for reliable comparisons."""

    if pd.isna(value):
        return ""

    text = normalize_product_key(value)
    text = re.sub(r"\s+", " ", text)

    return text


def filter_configured_products(df):
    """Keep only products configured in PRODUCTS for the final report."""

    configured_aliases = {
        normalize_text(alias)
        for product in PRODUCTS
        for alias in product["aliases"]
    }

    return df[
        df[PRODUCT_COLUMN]
        .map(normalize_text)
        .isin(configured_aliases)
    ].copy()


def get_existing_date_column(df):
    """Return the first available date column, or None."""

    for column in DATE_COLUMNS:
        if column in df.columns:
            return column

    return None


def get_company_name_from_sheet(input_path, sheet_name):
    """
    Read the full company name from the first three rows of a sheet.

    If the company name cannot be found, return the sheet name.
    """

    preview_df = pd.read_excel(
        input_path,
        sheet_name=sheet_name,
        header=None,
        nrows=3,
    )

    for row_index in range(len(preview_df)):
        for value in preview_df.iloc[row_index].dropna():
            text = str(value).strip()

            if "Наименование на дружеството" in text:
                company_name = (
                    text
                    .replace("Наименование на дружеството:", "")
                    .replace("Наименование на дружеството", "")
                    .replace(":", "")
                    .strip()
                )

                if company_name:
                    return company_name

    return sheet_name


def validate_required_columns(df, sheet_name):
    """Validate only the core columns required for the final summary."""

    required_columns = [
        PRODUCT_COLUMN,
        LITERS_COLUMN,
        AMOUNT_COLUMN,
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing columns in sheet '{sheet_name}': {missing_columns}. "
            f"Available columns: {df.columns.tolist()}"
        )


def extract_valid_dates(df):
    """Extract all valid transaction dates from one company sheet."""

    date_column = get_existing_date_column(df)

    if date_column is None:
        return []

    parsed_dates = pd.to_datetime(
        df[date_column],
        errors="coerce",
        format="mixed",
    ).dropna()

    return parsed_dates.tolist()


def create_period_title(all_dates):
    """
    Create the report period from the dates found in all sheets.

    Expected result for a single month:
        Юли 2026
    """

    if not all_dates:
        return "Месечна справка"

    normalized_dates = pd.to_datetime(
        pd.Series(all_dates),
        errors="coerce",
    ).dropna()

    if normalized_dates.empty:
        return "Месечна справка"

    periods = sorted(
        {
            (timestamp.year, timestamp.month)
            for timestamp in normalized_dates
        }
    )

    if len(periods) == 1:
        year, month = periods[0]
        return f"{BULGARIAN_MONTHS[month]} {year}"

    first_year, first_month = periods[0]
    last_year, last_month = periods[-1]

    return (
        f"{BULGARIAN_MONTHS[first_month]} {first_year} – "
        f"{BULGARIAN_MONTHS[last_month]} {last_year}"
    )



def create_period_metadata(all_dates):
    """
    Create stable period fields for the analysis dataset.

    The dataset is designed to be appended month after month, therefore
    period_start, period_end and period_id are stored explicitly.
    """

    normalized_dates = pd.to_datetime(
        pd.Series(all_dates),
        errors="coerce",
    ).dropna()

    if normalized_dates.empty:
        return {
            "period_id": "",
            "period_start": None,
            "period_end": None,
            "period_year": None,
            "period_month": None,
        }

    period_start = normalized_dates.min().normalize()
    period_end = normalized_dates.max().normalize()

    unique_months = sorted(
        {
            (timestamp.year, timestamp.month)
            for timestamp in normalized_dates
        }
    )

    if len(unique_months) == 1:
        period_year, period_month = unique_months[0]
        period_id = f"{period_year:04d}-{period_month:02d}"
    else:
        period_year = None
        period_month = None
        period_id = (
            f"{period_start.strftime('%Y-%m-%d')}_"
            f"{period_end.strftime('%Y-%m-%d')}"
        )

    return {
        "period_id": period_id,
        "period_start": period_start,
        "period_end": period_end,
        "period_year": period_year,
        "period_month": period_month,
    }


def safe_divide(numerator, denominator):
    """Return numerator / denominator, or zero when denominator is zero."""

    if denominator == 0:
        return 0.0

    return float(numerator) / float(denominator)


def calculate_company_values(df):
    """
    Calculate liters, client amounts, base-price amounts, average prices,
    weighted average base prices, discounts, margins, profits and
    transaction counts for every configured product.
    """

    working_df = df.copy()

    # Financial columns are optional because some companies do not have
    # configured price data. Missing financial values are treated as zero.
    optional_financial_columns = [
        BASE_PRICE_COLUMN,
        EKO_PRICE_COLUMN,
        DISCOUNT_COLUMN,
        MARGIN_COLUMN,
        PROFIT_COLUMN,
    ]

    for column in optional_financial_columns:
        if column not in working_df.columns:
            working_df[column] = 0.0

    working_df["_normalized_product"] = (
        working_df[PRODUCT_COLUMN]
        .map(normalize_text)
    )

    numeric_columns = [
        LITERS_COLUMN,
        AMOUNT_COLUMN,
        BASE_PRICE_COLUMN,
        EKO_PRICE_COLUMN,
        DISCOUNT_COLUMN,
        MARGIN_COLUMN,
        PROFIT_COLUMN,
    ]

    for column in numeric_columns:
        working_df[column] = pd.to_numeric(
            working_df[column],
            errors="coerce",
        ).fillna(0.0)

    liters_values = []
    amount_values = []
    base_amount_values = []
    average_price_values = []
    average_base_price_values = []
    average_discount_values = []
    average_margin_values = []
    profit_values = []
    average_profit_per_liter_values = []
    transaction_values = []

    for product in PRODUCTS:
        normalized_aliases = {
            normalize_text(alias)
            for alias in product["aliases"]
        }

        product_rows = working_df[
            working_df["_normalized_product"].isin(normalized_aliases)
        ]

        total_liters = float(product_rows[LITERS_COLUMN].sum())
        total_amount = float(product_rows[AMOUNT_COLUMN].sum())
        # Base amount logic:
        # - E GAS LPG: (EKO price - 0.015) * liters
        # - All other products: base EKO price * liters
        if product["output_name"] == "E Gas LPG":
            total_base_amount = float(
                (
                    (product_rows[EKO_PRICE_COLUMN] - 0.015)
                    * product_rows[LITERS_COLUMN]
                ).sum()
            )
        else:
            total_base_amount = float(
                (
                    product_rows[BASE_PRICE_COLUMN]
                    * product_rows[LITERS_COLUMN]
                ).sum()
            )
        total_profit = float(product_rows[PROFIT_COLUMN].sum())
        average_profit_per_liter = safe_divide(total_profit, total_liters)
        transaction_count = int(len(product_rows))

        # Weighted averages use liters as weights.
        average_price = safe_divide(total_amount, total_liters)
        average_base_price = safe_divide(total_base_amount, total_liters)

        discount_weighted_sum = float(
            (
                product_rows[DISCOUNT_COLUMN]
                * product_rows[LITERS_COLUMN]
            ).sum()
        )
        average_discount = safe_divide(
            discount_weighted_sum,
            total_liters,
        )

        margin_weighted_sum = float(
            (
                product_rows[MARGIN_COLUMN]
                * product_rows[LITERS_COLUMN]
            ).sum()
        )
        average_margin = safe_divide(
            margin_weighted_sum,
            total_liters,
        )

        liters_values.append(total_liters)
        amount_values.append(total_amount)
        base_amount_values.append(total_base_amount)
        average_price_values.append(average_price)
        average_base_price_values.append(average_base_price)
        average_discount_values.append(average_discount)
        average_margin_values.append(average_margin)
        profit_values.append(total_profit)
        average_profit_per_liter_values.append(average_profit_per_liter)
        transaction_values.append(transaction_count)

    total_liters = float(sum(liters_values))
    total_amount = float(sum(amount_values))
    total_base_amount = float(sum(base_amount_values))
    total_profit = float(sum(profit_values))
    total_average_profit_per_liter = safe_divide(total_profit, total_liters)
    total_transactions = int(sum(transaction_values))

    total_average_price = safe_divide(
        total_amount,
        total_liters,
    )

    total_average_base_price = safe_divide(
        total_base_amount,
        total_liters,
    )

    total_discount_weighted_sum = sum(
        average_discount_values[index] * liters_values[index]
        for index in range(len(PRODUCTS))
    )
    total_average_discount = safe_divide(
        total_discount_weighted_sum,
        total_liters,
    )

    total_margin_weighted_sum = sum(
        average_margin_values[index] * liters_values[index]
        for index in range(len(PRODUCTS))
    )
    total_average_margin = safe_divide(
        total_margin_weighted_sum,
        total_liters,
    )

    return {
        "liters_values": liters_values,
        "amount_values": amount_values,
        "base_amount_values": base_amount_values,
        "average_price_values": average_price_values,
        "average_base_price_values": average_base_price_values,
        "average_discount_values": average_discount_values,
        "average_margin_values": average_margin_values,
        "profit_values": profit_values,
        "average_profit_per_liter_values": average_profit_per_liter_values,
        "transaction_values": transaction_values,
        "total_liters": total_liters,
        "total_amount": total_amount,
        "total_base_amount": total_base_amount,
        "total_average_price": total_average_price,
        "total_average_base_price": total_average_base_price,
        "total_average_discount": total_average_discount,
        "total_average_margin": total_average_margin,
        "total_profit": total_profit,
        "total_average_profit_per_liter": total_average_profit_per_liter,
        "total_transactions": total_transactions,
    }



def build_analysis_dataset_rows(company_results, period_metadata):
    """
    Convert company-level results into a flat analysis-ready dataset.

    Grain:
        one row = one company for one reporting period

    This structure is intentionally stable so future monthly outputs can be
    appended with pandas.concat() and joined with other company-level datasets.
    """

    dataset_rows = []

    for result in company_results:
        active_products_count = sum(
            1
            for liters in result["liters_values"]
            if float(liters) > 0
        )

        row = {
            "period_id": period_metadata["period_id"],
            "period_start": period_metadata["period_start"],
            "period_end": period_metadata["period_end"],
            "period_year": period_metadata["period_year"],
            "period_month": period_metadata["period_month"],
            "company_name": result["company_name"],
            "source_sheet": result["sheet_name"],
            "active_products_count": active_products_count,
            "total_liters": result["total_liters"],
            "total_amount_gta_client": result["total_amount"],
            "total_amount_eko_gta": result["total_base_amount"],
            "avg_price": result["total_average_price"],
            "avg_base_price": result["total_average_base_price"],
            "avg_discount": result["total_average_discount"],
            "avg_margin": result["total_average_margin"],
            "total_profit": result["total_profit"],
            "avg_profit_per_liter": result["total_average_profit_per_liter"],
            "transactions": result["total_transactions"],
            "avg_liters_per_transaction": safe_divide(
                result["total_liters"],
                result["total_transactions"],
            ),
            "avg_amount_per_transaction": safe_divide(
                result["total_amount"],
                result["total_transactions"],
            ),
            "avg_profit_per_transaction": safe_divide(
                result["total_profit"],
                result["total_transactions"],
            ),
            "share_total_liters": result["share_of_total_liters"],
        }

        for product_index, product in enumerate(PRODUCTS):
            prefix = product["feature_prefix"]

            product_liters = result["liters_values"][product_index]
            product_transactions = result["transaction_values"][product_index]

            row[f"{prefix}_liters"] = product_liters
            row[f"{prefix}_amount_gta_client"] = result["amount_values"][product_index]
            row[f"{prefix}_amount_eko_gta"] = result["base_amount_values"][product_index]
            row[f"{prefix}_avg_price"] = result["average_price_values"][product_index]
            row[f"{prefix}_avg_base_price"] = result["average_base_price_values"][product_index]
            row[f"{prefix}_avg_discount"] = result["average_discount_values"][product_index]
            row[f"{prefix}_avg_margin"] = result["average_margin_values"][product_index]
            row[f"{prefix}_profit"] = result["profit_values"][product_index]
            row[f"{prefix}_avg_profit_per_liter"] = (
                result["average_profit_per_liter_values"][product_index]
            )
            row[f"{prefix}_transactions"] = product_transactions
            row[f"{prefix}_share_company_liters"] = safe_divide(
                product_liters,
                result["total_liters"],
            )
            row[f"{prefix}_avg_liters_per_transaction"] = safe_divide(
                product_liters,
                product_transactions,
            )

        dataset_rows.append(row)

    return dataset_rows


# ============================================================
# OUTPUT EXCEL FUNCTION
# ============================================================

def write_output_workbook(
    company_results,
    output_path,
    period_title,
    period_metadata,
):
    """
    Create a professional monthly management report with five sheets:

    1. Summary
       Detailed company-level liters, amounts, average prices, margins and profits.

    2. Dashboard
       KPI cards and management charts.

    3. Total
       Consolidated totals by product for all companies.

    4. Top Clients
       Ranked company table by total liters.

    5. Analysis Dataset
       Flat company-level feature table for data analysis and future joins.
    """

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        workbook = writer.book

        summary_ws = workbook.add_worksheet(SUMMARY_SHEET_NAME)
        dashboard_ws = workbook.add_worksheet(DASHBOARD_SHEET_NAME)
        total_ws = workbook.add_worksheet(TOTAL_SHEET_NAME)
        top_clients_ws = workbook.add_worksheet(TOP_CLIENTS_SHEET_NAME)
        analysis_dataset_ws = workbook.add_worksheet(ANALYSIS_DATASET_SHEET_NAME)

        writer.sheets[SUMMARY_SHEET_NAME] = summary_ws
        writer.sheets[DASHBOARD_SHEET_NAME] = dashboard_ws
        writer.sheets[TOTAL_SHEET_NAME] = total_ws
        writer.sheets[TOP_CLIENTS_SHEET_NAME] = top_clients_ws
        writer.sheets[ANALYSIS_DATASET_SHEET_NAME] = analysis_dataset_ws

        # ====================================================
        # SHARED FORMATS
        # ====================================================

        title_format = workbook.add_format({
            "bold": True,
            "font_size": 16,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#17365D",
            "font_color": "#FFFFFF",
            "border": 1,
        })

        subtitle_format = workbook.add_format({
            "bold": True,
            "font_size": 12,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#DCE6F1",
            "font_color": "#1F1F1F",
            "border": 1,
        })

        header_format = workbook.add_format({
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
            "bg_color": "#2F75B5",
            "font_color": "#FFFFFF",
            "border": 1,
        })

        number_format = workbook.add_format({
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#DCE6F1",
            "border": 1,
        })

        company_merged_format = workbook.add_format({
            "bold": True,
            "align": "left",
            "valign": "vcenter",
            "text_wrap": True,
            "bg_color": "#F7F9FC",
            "border": 1,
        })

        metric_label_format = workbook.add_format({
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#EAF2F8",
            "border": 1,
        })

        zero_value_format = workbook.add_format({
            "bg_color": "#C00000",
            "font_color": "#FFFFFF",
            "bold": True,
            "align": "right",
            "valign": "vcenter",
        })

        liters_format = workbook.add_format({
            "num_format": "#,##0.000",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        amount_format = workbook.add_format({
            "num_format": "#,##0.00",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        average_price_format = workbook.add_format({
            "num_format": "#,##0.000000",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        average_margin_format = workbook.add_format({
            "num_format": "#,##0.000000",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        profit_format = workbook.add_format({
            "num_format": "#,##0.00",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        integer_format = workbook.add_format({
            "num_format": "#,##0",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        percent_format = workbook.add_format({
            "num_format": "0.00%",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        total_liters_format = workbook.add_format({
            "bold": True,
            "num_format": "#,##0.000",
            "align": "right",
            "valign": "vcenter",
            "bg_color": "#FFF2CC",
            "border": 1,
        })

        total_amount_format = workbook.add_format({
            "bold": True,
            "num_format": "#,##0.00",
            "align": "right",
            "valign": "vcenter",
            "bg_color": "#FFF2CC",
            "border": 1,
        })

        total_average_format = workbook.add_format({
            "bold": True,
            "num_format": "#,##0.000000",
            "align": "right",
            "valign": "vcenter",
            "bg_color": "#FFF2CC",
            "border": 1,
        })

        total_margin_format = workbook.add_format({
            "bold": True,
            "num_format": "#,##0.000000",
            "align": "right",
            "valign": "vcenter",
            "bg_color": "#FFF2CC",
            "border": 1,
        })

        total_profit_format = workbook.add_format({
            "bold": True,
            "num_format": "#,##0.00",
            "align": "right",
            "valign": "vcenter",
            "bg_color": "#FFF2CC",
            "border": 1,
        })

        total_integer_format = workbook.add_format({
            "bold": True,
            "num_format": "#,##0",
            "align": "right",
            "valign": "vcenter",
            "bg_color": "#FFF2CC",
            "border": 1,
        })

        total_percent_format = workbook.add_format({
            "bold": True,
            "num_format": "0.00%",
            "align": "right",
            "valign": "vcenter",
            "bg_color": "#FFF2CC",
            "border": 1,
        })

        spacer_format = workbook.add_format({
            "bg_color": "#E7E6E6",
        })

        total_label_format = workbook.add_format({
            "bold": True,
            "align": "left",
            "valign": "vcenter",
            "bg_color": "#EAF2F8",
            "border": 1,
        })

        kpi_title_format = workbook.add_format({
            "bold": True,
            "font_size": 11,
            "align": "center",
            "valign": "vcenter",
            "font_color": "#FFFFFF",
            "bg_color": "#4472C4",
            "border": 1,
        })

        kpi_value_number_format = workbook.add_format({
            "bold": True,
            "font_size": 18,
            "align": "center",
            "valign": "vcenter",
            "num_format": "#,##0",
            "bg_color": "#DCE6F1",
            "border": 1,
        })

        kpi_value_liters_format = workbook.add_format({
            "bold": True,
            "font_size": 18,
            "align": "center",
            "valign": "vcenter",
            "num_format": "#,##0.000",
            "bg_color": "#DCE6F1",
            "border": 1,
        })

        kpi_value_amount_format = workbook.add_format({
            "bold": True,
            "font_size": 18,
            "align": "center",
            "valign": "vcenter",
            "num_format": "#,##0.00",
            "bg_color": "#DCE6F1",
            "border": 1,
        })

        kpi_value_price_format = workbook.add_format({
            "bold": True,
            "font_size": 18,
            "align": "center",
            "valign": "vcenter",
            "num_format": "#,##0.000000",
            "bg_color": "#DCE6F1",
            "border": 1,
        })

        # ====================================================
        # GLOBAL TOTALS
        # ====================================================

        total_liters_by_product = [
            sum(result["liters_values"][index] for result in company_results)
            for index in range(len(PRODUCTS))
        ]

        total_amounts_by_product = [
            sum(result["amount_values"][index] for result in company_results)
            for index in range(len(PRODUCTS))
        ]

        total_base_amounts_by_product = [
            sum(result["base_amount_values"][index] for result in company_results)
            for index in range(len(PRODUCTS))
        ]

        total_profits_by_product = [
            sum(result["profit_values"][index] for result in company_results)
            for index in range(len(PRODUCTS))
        ]

        average_profit_per_liter_by_product = [
            safe_divide(
                total_profits_by_product[index],
                total_liters_by_product[index],
            )
            for index in range(len(PRODUCTS))
        ]

        total_transactions_by_product = [
            sum(result["transaction_values"][index] for result in company_results)
            for index in range(len(PRODUCTS))
        ]

        average_prices_by_product = [
            safe_divide(
                total_amounts_by_product[index],
                total_liters_by_product[index],
            )
            for index in range(len(PRODUCTS))
        ]

        average_base_prices_by_product = [
            safe_divide(
                sum(
                    result["average_base_price_values"][index]
                    * result["liters_values"][index]
                    for result in company_results
                ),
                total_liters_by_product[index],
            )
            for index in range(len(PRODUCTS))
        ]

        average_discounts_by_product = [
            safe_divide(
                sum(
                    result["average_discount_values"][index]
                    * result["liters_values"][index]
                    for result in company_results
                ),
                total_liters_by_product[index],
            )
            for index in range(len(PRODUCTS))
        ]

        average_margins_by_product = [
            safe_divide(
                sum(
                    result["average_margin_values"][index]
                    * result["liters_values"][index]
                    for result in company_results
                ),
                total_liters_by_product[index],
            )
            for index in range(len(PRODUCTS))
        ]

        grand_total_liters = float(sum(total_liters_by_product))
        grand_total_amount = float(sum(total_amounts_by_product))
        grand_total_base_amount = float(sum(total_base_amounts_by_product))
        grand_total_profit = float(sum(total_profits_by_product))
        grand_average_profit_per_liter = safe_divide(
            grand_total_profit,
            grand_total_liters,
        )
        grand_total_transactions = int(sum(total_transactions_by_product))

        grand_average_price = safe_divide(
            grand_total_amount,
            grand_total_liters,
        )

        grand_average_base_price = safe_divide(
            sum(
                result["total_average_base_price"] * result["total_liters"]
                for result in company_results
            ),
            grand_total_liters,
        )

        grand_average_discount = safe_divide(
            sum(
                result["total_average_discount"] * result["total_liters"]
                for result in company_results
            ),
            grand_total_liters,
        )

        grand_average_margin = safe_divide(
            sum(
                result["total_average_margin"] * result["total_liters"]
                for result in company_results
            ),
            grand_total_liters,
        )

        for result in company_results:
            result["share_of_total_liters"] = safe_divide(
                result["total_liters"],
                grand_total_liters,
            )

        # SHEET 1: SUMMARY
        # ====================================================

        # Professional worksheet view.
        summary_ws.hide_gridlines(2)
        summary_ws.set_zoom(90)

        summary_headers = [
            "№",
            "ФИРМА",
            "ПОКАЗАТЕЛ",
            *[product["output_name"] for product in PRODUCTS],
            "TOTAL",
            "ТРАНЗАКЦИИ",
            "% ОБЩО",
        ]

        summary_last_col = len(summary_headers) - 1

        summary_ws.merge_range(
            0,
            0,
            0,
            summary_last_col,
            period_title,
            title_format,
        )

        summary_ws.merge_range(
            1,
            0,
            1,
            summary_last_col,
            "МЕСЕЧНА СПРАВКА ПО ФИРМИ",
            subtitle_format,
        )

        for column_index, header in enumerate(summary_headers):
            summary_ws.write(2, column_index, header, header_format)

        current_row = 3

        for company_number, result in enumerate(company_results, start=1):
            liters_row = current_row
            client_amount_row = current_row + 1
            base_amount_row = current_row + 2
            average_row = current_row + 3
            base_price_row = current_row + 4
            discount_row = current_row + 5
            margin_row = current_row + 6
            average_profit_per_liter_row = current_row + 7
            profit_row = current_row + 8
            separator_row = current_row + 9

            summary_ws.merge_range(
                liters_row,
                0,
                profit_row,
                0,
                company_number,
                number_format,
            )

            summary_ws.merge_range(
                liters_row,
                1,
                profit_row,
                1,
                result["company_name"],
                company_merged_format,
            )

            summary_ws.write(liters_row, 2, "ЛИТРИ", metric_label_format)
            summary_ws.write(client_amount_row, 2, "СУМА GTA - КЛИЕНТ", metric_label_format)
            summary_ws.write(base_amount_row, 2, "СУМА ЕКО - GTA", metric_label_format)
            summary_ws.write(average_row, 2, "СРЕДНА ЦЕНА", metric_label_format)
            summary_ws.write(base_price_row, 2, "СРЕДНА БАЗОВА ЦЕНА", metric_label_format)
            summary_ws.write(discount_row, 2, "СРЕДНА ОТСТЪПКА", metric_label_format)
            summary_ws.write(margin_row, 2, "СРЕДЕН МАРЖ", metric_label_format)
            summary_ws.write(
                average_profit_per_liter_row,
                2,
                "СРЕДНА ПЕЧАЛБА / Л",
                metric_label_format,
            )
            summary_ws.write(profit_row, 2, "ПЕЧАЛБА", metric_label_format)

            for product_index in range(len(PRODUCTS)):
                column_index = 3 + product_index

                summary_ws.write(
                    liters_row,
                    column_index,
                    result["liters_values"][product_index],
                    liters_format,
                )

                summary_ws.write(
                    client_amount_row,
                    column_index,
                    result["amount_values"][product_index],
                    amount_format,
                )

                summary_ws.write(
                    base_amount_row,
                    column_index,
                    result["base_amount_values"][product_index],
                    amount_format,
                )

                summary_ws.write(
                    average_row,
                    column_index,
                    result["average_price_values"][product_index],
                    average_price_format,
                )

                summary_ws.write(
                    base_price_row,
                    column_index,
                    result["average_base_price_values"][product_index],
                    average_price_format,
                )

                summary_ws.write(
                    discount_row,
                    column_index,
                    result["average_discount_values"][product_index],
                    average_margin_format,
                )

                summary_ws.write(
                    margin_row,
                    column_index,
                    result["average_margin_values"][product_index],
                    average_margin_format,
                )

                summary_ws.write(
                    profit_row,
                    column_index,
                    result["profit_values"][product_index],
                    profit_format,
                )

                summary_ws.write(
                    average_profit_per_liter_row,
                    column_index,
                    result["average_profit_per_liter_values"][product_index],
                    average_margin_format,
                )

            total_column = 3 + len(PRODUCTS)
            transactions_column = total_column + 1
            share_column = transactions_column + 1

            summary_ws.write(
                liters_row,
                total_column,
                result["total_liters"],
                total_liters_format,
            )
            summary_ws.write(
                client_amount_row,
                total_column,
                result["total_amount"],
                total_amount_format,
            )
            summary_ws.write(
                base_amount_row,
                total_column,
                result["total_base_amount"],
                total_amount_format,
            )
            summary_ws.write(
                average_row,
                total_column,
                result["total_average_price"],
                total_average_format,
            )
            summary_ws.write(
                base_price_row,
                total_column,
                result["total_average_base_price"],
                total_average_format,
            )
            summary_ws.write(
                discount_row,
                total_column,
                result["total_average_discount"],
                total_margin_format,
            )
            summary_ws.write(
                margin_row,
                total_column,
                result["total_average_margin"],
                total_margin_format,
            )
            summary_ws.write(
                profit_row,
                total_column,
                result["total_profit"],
                total_profit_format,
            )
            summary_ws.write(
                average_profit_per_liter_row,
                total_column,
                result["total_average_profit_per_liter"],
                total_margin_format,
            )

            # ----------------------------------------------------
            # SUMMARY CONDITIONAL FORMATTING
            # ----------------------------------------------------
            # Zero values are highlighted in red. Non-zero values use
            # dynamic data bars. For additive metrics the full bar is
            # the company TOTAL. For average metrics the full bar is the
            # largest value in that row, preventing weighted averages from
            # distorting the visual comparison.
            first_value_column = 3
            last_value_column = total_column

            summary_metric_rows = [
                liters_row,
                client_amount_row,
                base_amount_row,
                average_row,
                base_price_row,
                discount_row,
                margin_row,
                profit_row,
                average_profit_per_liter_row,
            ]

            # Highlight exact zero values across product and TOTAL cells.
            for metric_row in summary_metric_rows:
                summary_ws.conditional_format(
                    metric_row,
                    first_value_column,
                    metric_row,
                    last_value_column,
                    {
                        "type": "cell",
                        "criteria": "==",
                        "value": 0,
                        "format": zero_value_format,
                    },
                )

            additive_bar_rows = [
                (liters_row, result["total_liters"]),
                (client_amount_row, result["total_amount"]),
                (base_amount_row, result["total_base_amount"]),
                (profit_row, result["total_profit"]),
            ]

            for metric_row, total_value in additive_bar_rows:
                if total_value > 0:
                    summary_ws.conditional_format(
                        metric_row,
                        first_value_column,
                        metric_row,
                        last_value_column,
                        {
                            "type": "data_bar",
                            "min_type": "num",
                            "min_value": 0,
                            "max_type": "num",
                            "max_value": total_value,
                            "bar_color": "#2F75B5",
                            "bar_solid": False,
                            "bar_only": False,
                        },
                    )

            average_bar_rows = [
                (
                    average_row,
                    result["average_price_values"],
                    result["total_average_price"],
                ),
                (
                    base_price_row,
                    result["average_base_price_values"],
                    result["total_average_base_price"],
                ),
                (
                    discount_row,
                    result["average_discount_values"],
                    result["total_average_discount"],
                ),
                (
                    margin_row,
                    result["average_margin_values"],
                    result["total_average_margin"],
                ),
                (
                    average_profit_per_liter_row,
                    result["average_profit_per_liter_values"],
                    result["total_average_profit_per_liter"],
                ),
            ]

            for metric_row, product_values, total_value in average_bar_rows:
                row_max = max(
                    [0.0, float(total_value)]
                    + [float(value) for value in product_values]
                )

                if row_max > 0:
                    summary_ws.conditional_format(
                        metric_row,
                        first_value_column,
                        metric_row,
                        last_value_column,
                        {
                            "type": "data_bar",
                            "min_type": "num",
                            "min_value": 0,
                            "max_type": "num",
                            "max_value": row_max,
                            "bar_color": "#2F75B5",
                            "bar_solid": False,
                            "bar_only": False,
                        },
                    )

            summary_ws.write(
                liters_row,
                transactions_column,
                result["total_transactions"],
                total_integer_format,
            )

            for row in [
                client_amount_row,
                base_amount_row,
                average_row,
                base_price_row,
                discount_row,
                margin_row,
                profit_row,
                average_profit_per_liter_row,
            ]:
                summary_ws.write_blank(row, transactions_column, None, integer_format)

            summary_ws.write(
                liters_row,
                share_column,
                result["share_of_total_liters"],
                total_percent_format,
            )

            for row in [
                client_amount_row,
                base_amount_row,
                average_row,
                base_price_row,
                discount_row,
                margin_row,
                profit_row,
                average_profit_per_liter_row,
            ]:
                summary_ws.write_blank(row, share_column, None, percent_format)

            summary_ws.merge_range(
                separator_row,
                0,
                separator_row,
                summary_last_col,
                "",
                spacer_format,
            )

            current_row += 10

        summary_ws.set_column("A:A", 7)
        summary_ws.set_column("B:B", 40)
        summary_ws.set_column("C:C", 23)
        summary_ws.set_column("D:D", 17)
        summary_ws.set_column("E:E", 22)
        summary_ws.set_column("F:F", 21)
        summary_ws.set_column("G:G", 16)
        summary_ws.set_column("H:H", 13)
        summary_ws.set_column("I:I", 16)
        summary_ws.set_column("J:J", 15)
        summary_ws.set_column("K:K", 12)

        summary_ws.set_row(0, 32)
        summary_ws.set_row(1, 26)
        summary_ws.set_row(2, 38)
        summary_ws.freeze_panes(3, 0)

        summary_ws.autofilter(
            2,
            0,
            max(current_row - 1, 3),
            summary_last_col,
        )

        summary_ws.set_landscape()
        summary_ws.fit_to_pages(1, 0)
        summary_ws.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.5)
        summary_ws.set_header(f"&C&\"Arial,Bold\"{period_title}")
        summary_ws.set_footer("&CСтраница &P от &N")

        # ====================================================
        # SHEET 2: DASHBOARD
        # ====================================================

        dashboard_ws.hide_gridlines(2)
        dashboard_ws.set_zoom(90)

        dashboard_ws.merge_range("A1:L2", period_title, title_format)
        dashboard_ws.merge_range(
            "A3:L3",
            "УПРАВЛЕНСКИ DASHBOARD",
            subtitle_format,
        )

        # -------------------------
        # KPI ROW 1
        # -------------------------
        dashboard_ws.merge_range("A5:B5", "БРОЙ ФИРМИ", kpi_title_format)
        dashboard_ws.merge_range("A6:B8", len(company_results), kpi_value_number_format)

        dashboard_ws.merge_range("D5:E5", "ОБЩО ЛИТРИ", kpi_title_format)
        dashboard_ws.merge_range("D6:E8", grand_total_liters, kpi_value_liters_format)

        dashboard_ws.merge_range("G5:H5", "СУМА GTA - КЛИЕНТ", kpi_title_format)
        dashboard_ws.merge_range("G6:H8", grand_total_amount, kpi_value_amount_format)

        dashboard_ws.merge_range("J5:K5", "СУМА ЕКО - GTA", kpi_title_format)
        dashboard_ws.merge_range("J6:K8", grand_total_base_amount, kpi_value_amount_format)

        # -------------------------
        # KPI ROW 2
        # -------------------------
        dashboard_ws.merge_range("A10:B10", "СРЕДНА ЦЕНА", kpi_title_format)
        dashboard_ws.merge_range("A11:B13", grand_average_price, kpi_value_price_format)

        dashboard_ws.merge_range("D10:E10", "СРЕДНА БАЗОВА ЦЕНА", kpi_title_format)
        dashboard_ws.merge_range("D11:E13", grand_average_base_price, kpi_value_price_format)

        dashboard_ws.merge_range("G10:H10", "СРЕДНА ОТСТЪПКА", kpi_title_format)
        dashboard_ws.merge_range("G11:H13", grand_average_discount, kpi_value_price_format)

        dashboard_ws.merge_range("J10:K10", "СРЕДЕН МАРЖ", kpi_title_format)
        dashboard_ws.merge_range("J11:K13", grand_average_margin, kpi_value_price_format)

        # -------------------------
        # KPI ROW 3
        # -------------------------
        dashboard_ws.merge_range("A15:B15", "ТРАНЗАКЦИИ", kpi_title_format)
        dashboard_ws.merge_range("A16:B18", grand_total_transactions, kpi_value_number_format)

        dashboard_ws.merge_range("D15:E15", "ОБЩА ПЕЧАЛБА", kpi_title_format)
        dashboard_ws.merge_range("D16:E18", grand_total_profit, kpi_value_amount_format)

        largest_company = max(company_results, key=lambda item: item["total_liters"])
        largest_company_format = workbook.add_format({
            "bold": True,
            "font_size": 12,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
            "bg_color": "#DCE6F1",
            "border": 1,
        })

        dashboard_ws.merge_range("G15:H15", "НАЙ-ГОЛЯМ КЛИЕНТ", kpi_title_format)
        dashboard_ws.merge_range(
            "G16:H18",
            largest_company["company_name"],
            largest_company_format,
        )

        dashboard_share_format = workbook.add_format({
            "bold": True,
            "font_size": 18,
            "align": "center",
            "valign": "vcenter",
            "num_format": "0.00%",
            "bg_color": "#DCE6F1",
            "border": 1,
        })

        dashboard_ws.merge_range("J15:K15", "ДЯЛ НА ТОП КЛИЕНТА", kpi_title_format)
        dashboard_ws.merge_range(
            "J16:K18",
            largest_company["share_of_total_liters"],
            dashboard_share_format,
        )

        dashboard_ws.merge_range("A20:B20", "СРЕДНА ПЕЧАЛБА / Л", kpi_title_format)
        dashboard_ws.merge_range(
            "A21:B23",
            grand_average_profit_per_liter,
            kpi_value_price_format,
        )

        # Hidden/support table used by the charts.
        support_start_row = 60
        dashboard_ws.write(support_start_row, 0, "Продукт", header_format)
        dashboard_ws.write(support_start_row, 1, "Литри", header_format)
        dashboard_ws.write(support_start_row, 2, "Сума GTA - Клиент", header_format)
        dashboard_ws.write(support_start_row, 3, "Сума ЕКО - GTA", header_format)
        dashboard_ws.write(support_start_row, 4, "Печалба", header_format)

        for index, product in enumerate(PRODUCTS, start=1):
            dashboard_ws.write(support_start_row + index, 0, product["output_name"])
            dashboard_ws.write(
                support_start_row + index,
                1,
                total_liters_by_product[index - 1],
                liters_format,
            )
            dashboard_ws.write(
                support_start_row + index,
                2,
                total_amounts_by_product[index - 1],
                amount_format,
            )
            dashboard_ws.write(
                support_start_row + index,
                3,
                total_base_amounts_by_product[index - 1],
                amount_format,
            )
            dashboard_ws.write(
                support_start_row + index,
                4,
                total_profits_by_product[index - 1],
                profit_format,
            )

        ranked_companies = sorted(
            company_results,
            key=lambda item: item["total_liters"],
            reverse=True,
        )

        top_chart_count = min(TOP_CLIENTS_COUNT, len(ranked_companies))
        company_support_col = 6

        dashboard_ws.write(support_start_row, company_support_col, "Фирма", header_format)
        dashboard_ws.write(support_start_row, company_support_col + 1, "Литри", header_format)
        dashboard_ws.write(support_start_row, company_support_col + 2, "Печалба", header_format)

        for index, result in enumerate(ranked_companies[:top_chart_count], start=1):
            dashboard_ws.write(
                support_start_row + index,
                company_support_col,
                result["company_name"],
            )
            dashboard_ws.write(
                support_start_row + index,
                company_support_col + 1,
                result["total_liters"],
                liters_format,
            )
            dashboard_ws.write(
                support_start_row + index,
                company_support_col + 2,
                result["total_profit"],
                profit_format,
            )

        # Chart 1: liters by product.
        product_bar_chart = workbook.add_chart({"type": "column"})
        product_bar_chart.add_series({
            "name": "Общо литри",
            "categories": [
                DASHBOARD_SHEET_NAME,
                support_start_row + 1,
                0,
                support_start_row + len(PRODUCTS),
                0,
            ],
            "values": [
                DASHBOARD_SHEET_NAME,
                support_start_row + 1,
                1,
                support_start_row + len(PRODUCTS),
                1,
            ],
            "data_labels": {"value": True},
        })
        product_bar_chart.set_title({"name": "Литри по продукти"})
        product_bar_chart.set_x_axis({"name": "Продукт"})
        product_bar_chart.set_y_axis({"name": "Литри", "major_gridlines": {"visible": True}})
        product_bar_chart.set_legend({"none": True})
        product_bar_chart.set_style(11)
        product_bar_chart.set_size({"width": 540, "height": 330})
        dashboard_ws.insert_chart("A25", product_bar_chart)

        # Chart 2: profit by product.
        profit_chart = workbook.add_chart({"type": "column"})
        profit_chart.add_series({
            "name": "Печалба",
            "categories": [
                DASHBOARD_SHEET_NAME,
                support_start_row + 1,
                0,
                support_start_row + len(PRODUCTS),
                0,
            ],
            "values": [
                DASHBOARD_SHEET_NAME,
                support_start_row + 1,
                4,
                support_start_row + len(PRODUCTS),
                4,
            ],
            "data_labels": {"value": True},
        })
        profit_chart.set_title({"name": "Печалба по продукти"})
        profit_chart.set_x_axis({"name": "Продукт"})
        profit_chart.set_y_axis({"name": "Печалба", "major_gridlines": {"visible": True}})
        profit_chart.set_legend({"none": True})
        profit_chart.set_style(12)
        profit_chart.set_size({"width": 540, "height": 330})
        dashboard_ws.insert_chart("G25", profit_chart)

        # Chart 3: top clients by liters.
        top_clients_chart = workbook.add_chart({"type": "bar"})
        top_clients_chart.add_series({
            "name": "Общо литри",
            "categories": [
                DASHBOARD_SHEET_NAME,
                support_start_row + 1,
                company_support_col,
                support_start_row + top_chart_count,
                company_support_col,
            ],
            "values": [
                DASHBOARD_SHEET_NAME,
                support_start_row + 1,
                company_support_col + 1,
                support_start_row + top_chart_count,
                company_support_col + 1,
            ],
            "data_labels": {"value": True},
        })
        top_clients_chart.set_title({"name": f"Top {top_chart_count} фирми по литри"})
        top_clients_chart.set_x_axis({"name": "Литри"})
        top_clients_chart.set_y_axis({"name": "Фирма"})
        top_clients_chart.set_legend({"none": True})
        top_clients_chart.set_style(10)
        top_clients_chart.set_size({"width": 1080, "height": 390})
        dashboard_ws.insert_chart("A42", top_clients_chart)

        dashboard_ws.set_column("A:L", 12)
        dashboard_ws.set_row(0, 24)
        dashboard_ws.set_row(1, 24)
        dashboard_ws.set_row(2, 24)
        dashboard_ws.set_landscape()
        dashboard_ws.fit_to_pages(1, 1)
        dashboard_ws.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.5)
        dashboard_ws.set_header(f'&C&"Arial,Bold"{period_title}')
        dashboard_ws.set_footer("&CСтраница &P от &N")

        # Hide support rows from the normal dashboard view.
        max_support_rows = max(len(PRODUCTS), top_chart_count)
        dashboard_ws.set_row(support_start_row, None, None, {"hidden": True})
        for row in range(support_start_row + 1, support_start_row + max_support_rows + 1):
            dashboard_ws.set_row(row, None, None, {"hidden": True})

        # SHEET 3: TOTAL BY PRODUCT
        # ====================================================

        total_ws.hide_gridlines(2)
        total_ws.set_zoom(90)

        total_headers = [
            "Продукт",
            "Общо литри",
            "Сума GTA - Клиент",
            "Сума ЕКО - GTA",
            "Средна цена",
            "Средна базова цена",
            "Средна отстъпка",
            "Среден марж",
            "Печалба",
            "Средна печалба / л",
            "Транзакции",
            "% от общите литри",
        ]

        total_last_col = len(total_headers) - 1

        total_ws.merge_range(0, 0, 0, total_last_col, period_title, title_format)
        total_ws.merge_range(
            1,
            0,
            1,
            total_last_col,
            "ОБЩО ЗА ВСИЧКИ ФИРМИ ПО ПРОДУКТИ",
            subtitle_format,
        )

        for column_index, header in enumerate(total_headers):
            total_ws.write(2, column_index, header, header_format)

        first_product_row = 3

        for product_index, product in enumerate(PRODUCTS):
            row = first_product_row + product_index

            total_ws.write(row, 0, product["output_name"], company_merged_format)
            total_ws.write(row, 1, total_liters_by_product[product_index], liters_format)
            total_ws.write(row, 2, total_amounts_by_product[product_index], amount_format)
            total_ws.write(row, 3, total_base_amounts_by_product[product_index], amount_format)
            total_ws.write(row, 4, average_prices_by_product[product_index], average_price_format)
            total_ws.write(row, 5, average_base_prices_by_product[product_index], average_price_format)
            total_ws.write(row, 6, average_discounts_by_product[product_index], average_margin_format)
            total_ws.write(row, 7, average_margins_by_product[product_index], average_margin_format)
            total_ws.write(row, 8, total_profits_by_product[product_index], profit_format)
            total_ws.write(
                row,
                9,
                average_profit_per_liter_by_product[product_index],
                average_margin_format,
            )
            total_ws.write(row, 10, total_transactions_by_product[product_index], integer_format)
            total_ws.write(
                row,
                11,
                safe_divide(total_liters_by_product[product_index], grand_total_liters),
                percent_format,
            )

        total_row = first_product_row + len(PRODUCTS)

        total_ws.write(total_row, 0, "TOTAL", total_label_format)
        total_ws.write(total_row, 1, grand_total_liters, total_liters_format)
        total_ws.write(total_row, 2, grand_total_amount, total_amount_format)
        total_ws.write(total_row, 3, grand_total_base_amount, total_amount_format)
        total_ws.write(total_row, 4, grand_average_price, total_average_format)
        total_ws.write(total_row, 5, grand_average_base_price, total_average_format)
        total_ws.write(total_row, 6, grand_average_discount, total_margin_format)
        total_ws.write(total_row, 7, grand_average_margin, total_margin_format)
        total_ws.write(total_row, 8, grand_total_profit, total_profit_format)
        total_ws.write(
            total_row,
            9,
            grand_average_profit_per_liter,
            total_margin_format,
        )
        total_ws.write(total_row, 10, grand_total_transactions, total_integer_format)
        total_ws.write(
            total_row,
            11,
            1 if grand_total_liters != 0 else 0,
            total_percent_format,
        )

        # Red highlight for zero values in the financial/quantity area.
        total_ws.conditional_format(
            first_product_row,
            1,
            total_row,
            10,
            {
                "type": "cell",
                "criteria": "==",
                "value": 0,
                "format": zero_value_format,
            },
        )

        # Gradient data bars for additive metrics.
        for col in [1, 2, 3, 8]:
            total_ws.conditional_format(
                first_product_row,
                col,
                total_row - 1,
                col,
                {
                    "type": "data_bar",
                    "bar_color": "#2F75B5",
                    "bar_solid": False,
                    "bar_only": False,
                },
            )

        # Distribution bar for share of liters.
        total_ws.conditional_format(
            first_product_row,
            11,
            total_row - 1,
            11,
            {
                "type": "data_bar",
                "bar_color": "#70AD47",
                "bar_solid": False,
                "bar_only": False,
            },
        )

        # Pie chart remains focused on product mix by liters.
        total_pie_chart = workbook.add_chart({"type": "pie"})
        total_pie_chart.add_series({
            "name": "Разпределение на литрите по продукти",
            "categories": [
                TOTAL_SHEET_NAME,
                first_product_row,
                0,
                total_row - 1,
                0,
            ],
            "values": [
                TOTAL_SHEET_NAME,
                first_product_row,
                1,
                total_row - 1,
                1,
            ],
            "data_labels": {
                "percentage": True,
                "category": True,
                "leader_lines": True,
            },
        })
        total_pie_chart.set_title({"name": "Разпределение на общите литри"})
        total_pie_chart.set_legend({"position": "bottom"})
        total_pie_chart.set_style(10)
        total_pie_chart.set_size({"width": 650, "height": 380})
        total_ws.insert_chart("M3", total_pie_chart)

        total_ws.set_column("A:A", 29)
        total_ws.set_column("B:D", 18)
        total_ws.set_column("E:H", 19)
        total_ws.set_column("I:I", 16)
        total_ws.set_column("J:J", 20)
        total_ws.set_column("K:K", 15)
        total_ws.set_column("L:L", 21)
        total_ws.set_row(0, 30)
        total_ws.set_row(1, 24)
        total_ws.set_row(2, 36)
        total_ws.freeze_panes(3, 0)
        total_ws.autofilter(2, 0, total_row, total_last_col)
        total_ws.set_landscape()
        total_ws.fit_to_pages(1, 1)
        total_ws.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.5)
        total_ws.set_header(f'&C&"Arial,Bold"{period_title}')
        total_ws.set_footer("&CСтраница &P от &N")

        # SHEET 4: TOP CLIENTS
        # ====================================================

        top_clients_ws.hide_gridlines(2)
        top_clients_ws.set_zoom(85)

        top_headers = [
            "№",
            "Фирма",
            "Общо литри",
            "Сума GTA - Клиент",
            "Сума ЕКО - GTA",
            "Средна цена",
            "Средна базова цена",
            "Средна отстъпка",
            "Среден марж",
            "Печалба",
            "Средна печалба / л",
            "Транзакции",
            "% от общите литри",
        ]

        top_last_col = len(top_headers) - 1

        top_clients_ws.merge_range(0, 0, 0, top_last_col, period_title, title_format)
        top_clients_ws.merge_range(
            1,
            0,
            1,
            top_last_col,
            "КЛАСАЦИЯ НА ФИРМИТЕ ПО ОБЩО КОЛИЧЕСТВО",
            subtitle_format,
        )

        for column_index, header in enumerate(top_headers):
            top_clients_ws.write(2, column_index, header, header_format)

        for rank, result in enumerate(ranked_companies, start=1):
            row = rank + 2

            top_clients_ws.write(row, 0, rank, number_format)
            top_clients_ws.write(row, 1, result["company_name"], company_merged_format)
            top_clients_ws.write(row, 2, result["total_liters"], liters_format)
            top_clients_ws.write(row, 3, result["total_amount"], amount_format)
            top_clients_ws.write(row, 4, result["total_base_amount"], amount_format)
            top_clients_ws.write(row, 5, result["total_average_price"], average_price_format)
            top_clients_ws.write(row, 6, result["total_average_base_price"], average_price_format)
            top_clients_ws.write(row, 7, result["total_average_discount"], average_margin_format)
            top_clients_ws.write(row, 8, result["total_average_margin"], average_margin_format)
            top_clients_ws.write(row, 9, result["total_profit"], profit_format)
            top_clients_ws.write(
                row,
                10,
                result["total_average_profit_per_liter"],
                average_margin_format,
            )
            top_clients_ws.write(row, 11, result["total_transactions"], integer_format)
            top_clients_ws.write(row, 12, result["share_of_total_liters"], percent_format)

        last_top_row = len(ranked_companies) + 2

        # Highlight missing/zero financial values clearly.
        top_clients_ws.conditional_format(
            3,
            2,
            last_top_row,
            11,
            {
                "type": "cell",
                "criteria": "==",
                "value": 0,
                "format": zero_value_format,
            },
        )

        # Gradient bars for additive metrics.
        for col in [2, 3, 4, 9]:
            top_clients_ws.conditional_format(
                3,
                col,
                last_top_row,
                col,
                {
                    "type": "data_bar",
                    "bar_color": "#2F75B5",
                    "bar_solid": False,
                    "bar_only": False,
                },
            )

        top_clients_ws.conditional_format(
            3,
            12,
            last_top_row,
            12,
            {
                "type": "data_bar",
                "bar_color": "#70AD47",
                "bar_solid": False,
                "bar_only": False,
            },
        )

        top_clients_ws.autofilter(2, 0, last_top_row, top_last_col)
        top_clients_ws.freeze_panes(3, 0)

        top_clients_ws.set_column("A:A", 7)
        top_clients_ws.set_column("B:B", 42)
        top_clients_ws.set_column("C:E", 18)
        top_clients_ws.set_column("F:I", 19)
        top_clients_ws.set_column("J:J", 16)
        top_clients_ws.set_column("K:K", 20)
        top_clients_ws.set_column("L:L", 15)
        top_clients_ws.set_column("M:M", 21)
        top_clients_ws.set_row(0, 30)
        top_clients_ws.set_row(1, 24)
        top_clients_ws.set_row(2, 36)
        top_clients_ws.set_landscape()
        top_clients_ws.fit_to_pages(1, 0)
        top_clients_ws.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.5)
        top_clients_ws.set_header(f'&C&"Arial,Bold"{period_title}')
        top_clients_ws.set_footer("&CСтраница &P от &N")


        # ====================================================
        # SHEET 5: ANALYSIS DATASET
        # ====================================================

        # This sheet is intentionally different from the management sheets:
        # - one row = one company for one reporting period
        # - one header row
        # - no merged cells
        # - no subtotal or TOTAL rows
        # - stable snake_case feature names
        # This makes it directly suitable for pandas, EDA, ML and future joins.
        analysis_dataset_ws.hide_gridlines(2)
        analysis_dataset_ws.set_zoom(85)

        analysis_rows = build_analysis_dataset_rows(
            company_results=company_results,
            period_metadata=period_metadata,
        )

        analysis_df = pd.DataFrame(analysis_rows)

        # Keep identifier and main company features first.
        identifier_columns = [
            "period_id",
            "period_start",
            "period_end",
            "period_year",
            "period_month",
            "company_name",
            "source_sheet",
        ]

        company_feature_columns = [
            "active_products_count",
            "total_liters",
            "total_amount_gta_client",
            "total_amount_eko_gta",
            "avg_price",
            "avg_base_price",
            "avg_discount",
            "avg_margin",
            "total_profit",
            "avg_profit_per_liter",
            "transactions",
            "avg_liters_per_transaction",
            "avg_amount_per_transaction",
            "avg_profit_per_transaction",
            "share_total_liters",
        ]

        product_feature_columns = []
        for product in PRODUCTS:
            prefix = product["feature_prefix"]
            product_feature_columns.extend([
                f"{prefix}_liters",
                f"{prefix}_amount_gta_client",
                f"{prefix}_amount_eko_gta",
                f"{prefix}_avg_price",
                f"{prefix}_avg_base_price",
                f"{prefix}_avg_discount",
                f"{prefix}_avg_margin",
                f"{prefix}_profit",
                f"{prefix}_avg_profit_per_liter",
                f"{prefix}_transactions",
                f"{prefix}_share_company_liters",
                f"{prefix}_avg_liters_per_transaction",
            ])

        analysis_columns = (
            identifier_columns
            + company_feature_columns
            + product_feature_columns
        )

        analysis_df = analysis_df.reindex(columns=analysis_columns)

        dataset_header_format = workbook.add_format({
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
            "bg_color": "#1F4E78",
            "font_color": "#FFFFFF",
            "border": 1,
        })

        dataset_text_format = workbook.add_format({
            "align": "left",
            "valign": "vcenter",
            "border": 1,
        })

        dataset_date_format = workbook.add_format({
            "num_format": "yyyy-mm-dd",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
        })

        dataset_integer_format = workbook.add_format({
            "num_format": "0",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        dataset_liters_format = workbook.add_format({
            "num_format": "#,##0.000",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        dataset_amount_format = workbook.add_format({
            "num_format": "#,##0.00",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        dataset_decimal_format = workbook.add_format({
            "num_format": "#,##0.000000",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        dataset_percent_format = workbook.add_format({
            "num_format": "0.000000",
            "align": "right",
            "valign": "vcenter",
            "border": 1,
        })

        for column_index, column_name in enumerate(analysis_df.columns):
            analysis_dataset_ws.write(
                0,
                column_index,
                column_name,
                dataset_header_format,
            )

        for row_offset, row_values in enumerate(
            analysis_df.itertuples(index=False, name=None),
            start=1,
        ):
            for column_index, value in enumerate(row_values):
                column_name = analysis_df.columns[column_index]

                if pd.isna(value):
                    analysis_dataset_ws.write_blank(
                        row_offset,
                        column_index,
                        None,
                        dataset_text_format,
                    )
                    continue

                if column_name in {"period_start", "period_end"}:
                    analysis_dataset_ws.write_datetime(
                        row_offset,
                        column_index,
                        pd.Timestamp(value).to_pydatetime(),
                        dataset_date_format,
                    )
                elif column_name in {
                    "company_name",
                    "source_sheet",
                    "period_id",
                }:
                    analysis_dataset_ws.write(
                        row_offset,
                        column_index,
                        value,
                        dataset_text_format,
                    )
                elif (
                    column_name in {
                        "period_year",
                        "period_month",
                        "active_products_count",
                        "transactions",
                    }
                    or column_name.endswith("_transactions")
                ):
                    analysis_dataset_ws.write_number(
                        row_offset,
                        column_index,
                        float(value),
                        dataset_integer_format,
                    )
                elif (
                    column_name == "total_liters"
                    or column_name == "avg_liters_per_transaction"
                    or column_name.endswith("_liters")
                    or column_name.endswith("_avg_liters_per_transaction")
                ):
                    analysis_dataset_ws.write_number(
                        row_offset,
                        column_index,
                        float(value),
                        dataset_liters_format,
                    )
                elif (
                    "amount" in column_name
                    or column_name == "total_profit"
                    or column_name.endswith("_profit")
                    or column_name == "avg_profit_per_transaction"
                ):
                    analysis_dataset_ws.write_number(
                        row_offset,
                        column_index,
                        float(value),
                        dataset_amount_format,
                    )
                elif (
                    column_name == "share_total_liters"
                    or column_name.endswith("_share_company_liters")
                ):
                    # Store shares as raw decimal ratios (0-1), not formatted
                    # percentages, which is more convenient for analysis.
                    analysis_dataset_ws.write_number(
                        row_offset,
                        column_index,
                        float(value),
                        dataset_percent_format,
                    )
                else:
                    analysis_dataset_ws.write_number(
                        row_offset,
                        column_index,
                        float(value),
                        dataset_decimal_format,
                    )

        dataset_last_row = len(analysis_df)
        dataset_last_col = len(analysis_df.columns) - 1

        # Add an Excel table so filters and structured selection work
        # immediately while preserving a clean tabular dataset.
        if dataset_last_row >= 1:
            analysis_dataset_ws.add_table(
                0,
                0,
                dataset_last_row,
                dataset_last_col,
                {
                    "name": "AnalysisDataset",
                    "style": "Table Style Medium 2",
                    "columns": [
                        {"header": column}
                        for column in analysis_df.columns
                    ],
                },
            )

        analysis_dataset_ws.freeze_panes(1, 0)

        # Identifier columns.
        analysis_dataset_ws.set_column("A:A", 13)
        analysis_dataset_ws.set_column("B:C", 13)
        analysis_dataset_ws.set_column("D:E", 11)
        analysis_dataset_ws.set_column("F:F", 42)
        analysis_dataset_ws.set_column("G:G", 25)

        # Numeric feature columns. Keep them compact because this is a
        # machine-oriented dataset rather than a presentation sheet.
        if dataset_last_col >= 7:
            analysis_dataset_ws.set_column(7, dataset_last_col, 19)

        analysis_dataset_ws.set_row(0, 42)
        analysis_dataset_ws.set_landscape()
        analysis_dataset_ws.fit_to_pages(1, 0)
        analysis_dataset_ws.set_margins(
            left=0.25,
            right=0.25,
            top=0.4,
            bottom=0.4,
        )
        analysis_dataset_ws.set_header(
            f'&C&"Arial,Bold"{period_title} - Analysis Dataset'
        )
        analysis_dataset_ws.set_footer("&CСтраница &P от &N")




def generate_analytics_workbook(period="full"):
    """Build the five-sheet report from the selected Analytics period."""
    if period not in ("first", "second", "full"):
        raise ValueError("Невалиден отчетен период.")

    company_results = []
    all_dates = []
    for company in Company.objects.order_by("name"):
        rows, *_ = get_company_report_data(company, period=period)
        if not rows:
            continue
        records = [{
            PRODUCT_COLUMN: row["material"],
            LITERS_COLUMN: float(row["qty"]),
            AMOUNT_COLUMN: float(row["gta_total"]),
            BASE_PRICE_COLUMN: float(row["eko_base_price"]),
            EKO_PRICE_COLUMN: float(row["eko_price"]),
            DISCOUNT_COLUMN: float(row["discount"]),
            MARGIN_COLUMN: float(row["margin"]),
            PROFIT_COLUMN: float(row["profit"]),
        } for row in rows]
        frame = filter_configured_products(pd.DataFrame.from_records(records))
        if frame.empty:
            continue
        all_dates.extend(row["date"] for row in rows if normalize_text(row["material"]) in {
            normalize_text(alias) for product in PRODUCTS for alias in product["aliases"]
        })
        company_results.append({
            "company_name": company.name,
            "sheet_name": company.name[:31],
            **calculate_company_values(frame),
        })

    if not company_results:
        raise ValueError("Няма транзакции от включените продукти за избрания период.")

    output = io.BytesIO()
    write_output_workbook(company_results, output, create_period_title(all_dates), create_period_metadata(all_dates))
    output.seek(0)
    return output
