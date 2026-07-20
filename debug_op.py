import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eko_users.settings')
django.setup()

from core.utils import get_company_report_data
from core.models import Company

company = Company.objects.get(name='ОП УПРАВЛЕНИЕ НА ПРОЕКТИ И ОЗЕЛЕНЯВАНЕ')
data, t_qty, t_eko, t_gta, t_profit = get_company_report_data(company)
for item in data:
    if item['date'].isoformat() == '2026-07-15' and '95' in item['material']:
        print(f"Qty: {item['qty']}")
        print(f"GTA_Price: {item['gta_price']}")
        print(f"EKO_Price: {item['eko_price']}")
        print(f"Discount: {item['discount']}")
        print(f"Profit: {item['profit']}")
