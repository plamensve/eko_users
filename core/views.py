from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UploadFileForm, CompanyForm, CardForm
from .utils import import_cards, import_prices, import_transactions, export_all_companies_zip, get_company_report_data, \
    export_single_company_zip, normalize_text, relink_data
from .models import Transaction, Company, Price, Card
import os
import tempfile
from django.db.models import Count, Max, Min, Q
from django.views.decorators.http import require_POST
from django.urls import reverse


@login_required
def index(request):
    period = Transaction.objects.aggregate(start=Min('date'), end=Max('date'))
    return render(request, 'core/index.html', {
        'company_count': Company.objects.count(),
        'card_count': Card.objects.count(),
        'transaction_count': Transaction.objects.count(),
        'price_count': Price.objects.count(),
        'unlinked_transactions': Transaction.objects.filter(card__isnull=True).count(),
        'period_start': period['start'],
        'period_end': period['end'],
    })


@login_required
def upload_files(request):
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            def process_upload(upload, importer):
                suffix = os.path.splitext(upload.name)[1].lower()
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                    for chunk in upload.chunks():
                        temporary.write(chunk)
                    path = temporary.name
                try:
                    return importer(path)
                finally:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

            try:
                if request.FILES.get('cards_file'):
                    result = process_upload(request.FILES['cards_file'], import_cards)
                    messages.success(request, f"Карти: {result.created} нови, {result.updated} обновени, {result.skipped} пропуснати.")
                price_files = request.FILES.getlist('prices_files')
                if price_files:
                    totals = [process_upload(upload, import_prices) for upload in price_files]
                    messages.success(
                        request,
                        f"Цените са импортирани успешно. Обработени файлове: {len(price_files)}; "
                        f"нови записи: {sum(r.created for r in totals)}; "
                        f"обновени: {sum(r.updated for r in totals)}; "
                        f"пропуснати: {sum(r.skipped for r in totals)}."
                    )
                if request.FILES.get('transactions_file'):
                    result = process_upload(request.FILES['transactions_file'], import_transactions)
                    messages.success(request, f"Транзакции: {result.created} импортирани, {result.skipped} пропуснати. Предишният отчетен период е заменен.")
            except (ValueError, KeyError, OSError) as exc:
                messages.error(request, f"Импортът беше прекратен: {exc}")
                return render(request, 'core/upload.html', {'form': form})
            return redirect('upload')
    else:
        form = UploadFileForm()
    return render(request, 'core/upload.html', {'form': form})


@login_required
def company_list(request):
    search_query = request.GET.get('search', '')
    companies = Company.objects.annotate(card_total=Count('cards')).order_by('name')

    return render(request, 'core/company_list.html', {
        'companies': companies,
        'search_query': search_query
    })


from django.http import HttpResponse, JsonResponse
from .utils import import_cards, import_prices, import_transactions, export_company_excel, export_company_pdf
import urllib.parse


@login_required
def company_search_suggestions(request):
    query = request.GET.get('term', '').strip()
    if query:
        normalized_query = normalize_text(query)
        companies = Company.objects.filter(
            Q(name__startswith=normalized_query) | Q(eik__startswith=query)
        ).order_by('name')[:20]
        results = [
            {
                'id': company.id,
                'name': company.name,
                'eik': company.eik,
                'url': reverse('company_transactions', args=[company.id]),
            }
            for company in companies
        ]
        return JsonResponse(results, safe=False)
    return JsonResponse([], safe=False)


@login_required
def export_pdf(request, company_id):
    company = Company.objects.get(id=company_id)

    report_type = request.GET.get('report', 'billing')

    if report_type not in ('billing', 'first', 'second', 'full'):
        report_type = 'billing'

    output = export_company_pdf(
        company,
        period=report_type
    )

    filename = f"Report_{company.name}.pdf"
    filename_quoted = urllib.parse.quote(filename)

    response = HttpResponse(
        output,
        content_type='application/pdf'
    )

    response['Content-Disposition'] = (
        f"attachment; filename*=UTF-8''{filename_quoted}"
    )

    return response


@login_required
def company_transactions(request, company_id):
    company = Company.objects.get(id=company_id)

    report_type = request.GET.get('report', 'billing')

    if report_type not in ('billing', 'first', 'second', 'full'):
        report_type = 'billing'

    data, t_qty, t_eko, t_gta, t_profit = get_company_report_data(
        company,
        period=report_type
    )

    return render(request, 'core/company_transactions.html', {
        'company': company,
        'transactions': data,
        'total_qty': t_qty,
        'total_eko': t_eko,
        'total_gta': t_gta,
        'total_profit': t_profit,
        'report_type': report_type
    })


@login_required
def export_excel(request, company_id):
    company = Company.objects.get(id=company_id)

    report_type = request.GET.get('report', 'billing')

    if report_type not in ('billing', 'first', 'second', 'full'):
        report_type = 'billing'

    output = export_company_excel(
        company,
        period=report_type
    )

    filename = f"Report_{company.name}.xlsx"
    filename_quoted = urllib.parse.quote(filename)

    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    response['Content-Disposition'] = (
        f"attachment; filename*=UTF-8''{filename_quoted}"
    )

    return response


@login_required
def export_all_zip(request):
    report_type = request.GET.get('report', 'billing')

    if report_type not in ('billing', 'first', 'second', 'full'):
        report_type = 'billing'

    zip_buffer = export_all_companies_zip(
        period=report_type
    )

    response = HttpResponse(
        zip_buffer.getvalue(),
        content_type='application/x-zip-compressed'
    )

    response['Content-Disposition'] = (
        'attachment; filename="All_Company_Reports.zip"'
    )

    return response


@login_required
def export_company_zip_view(request, company_id):
    company = get_object_or_404(Company, id=company_id)

    report_type = request.GET.get('report', 'billing')

    if report_type not in ('billing', 'first', 'second', 'full'):
        report_type = 'billing'

    zip_buffer = export_single_company_zip(
        company,
        period=report_type
    )

    filename = f"Report_{company.name}.zip"
    filename_quoted = urllib.parse.quote(filename)

    response = HttpResponse(
        zip_buffer.getvalue(),
        content_type='application/x-zip-compressed'
    )

    response['Content-Disposition'] = (
        f"attachment; filename*=UTF-8''{filename_quoted}"
    )

    return response


@login_required
def company_add(request):
    if request.method == 'POST':
        form = CompanyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Фирмата беше добавена успешно.")
            return redirect('company_list')
    else:
        form = CompanyForm()
    return render(request, 'core/company_form.html', {'form': form, 'title': 'Добавяне на фирма'})


@login_required
def company_edit(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST':
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Фирмата беше обновена успешно.")
            return redirect('company_list')
    else:
        form = CompanyForm(instance=company)
    return render(request, 'core/company_form.html', {'form': form, 'title': 'Редактиране на фирма'})


@login_required
def company_delete(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST':
        company.delete()
        messages.success(request, "Фирмата беше изтрита успешно.")
        return redirect('company_list')
    return render(request, 'core/confirm_delete.html', {'object': company, 'type': 'фирма'})


@login_required
def company_delete_all(request):
    if request.method == 'POST':
        count = Company.objects.count()
        Company.objects.all().delete()
        messages.success(request, f"Всички {count} фирми бяха изтрити успешно.")
        return redirect('company_list')
    return render(request, 'core/confirm_delete.html', {'object': "всички фирми", 'type': 'всички фирми'})


@login_required
def card_list(request):
    cards = Card.objects.all().order_by('company__name', 'card_number')
    return render(request, 'core/card_list.html', {'cards': cards})


@login_required
def card_add(request):
    if request.method == 'POST':
        form = CardForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Картата беше добавена успешно.")
            return redirect('card_list')
    else:
        form = CardForm()
    return render(request, 'core/card_form.html', {'form': form, 'title': 'Добавяне на карта'})


@login_required
def card_edit(request, card_id):
    card = get_object_or_404(Card, id=card_id)
    if request.method == 'POST':
        form = CardForm(request.POST, instance=card)
        if form.is_valid():
            form.save()
            messages.success(request, "Картата беше обновена успешно.")
            return redirect('card_list')
    else:
        form = CardForm(instance=card)
    return render(request, 'core/card_form.html', {'form': form, 'title': 'Редактиране на карта'})


@login_required
def card_delete(request, card_id):
    card = get_object_or_404(Card, id=card_id)
    if request.method == 'POST':
        card.delete()
        messages.success(request, "Картата беше изтрита успешно.")
        return redirect('card_list')
    return render(request, 'core/confirm_delete.html', {'object': card, 'type': 'карта'})


@login_required
def card_delete_all(request):
    if request.method == 'POST':
        count = Card.objects.count()
        Card.objects.all().delete()
        messages.success(request, f"Всички {count} карти бяха изтрити успешно.")
        return redirect('card_list')
    return render(request, 'core/confirm_delete.html', {'object': "всички карти", 'type': 'всички карти'})


@login_required
def price_delete_all(request):
    if request.method == 'POST':
        count = Price.objects.count()
        Price.objects.all().delete()
        messages.success(request, f"Всички {count} цени бяха изтрити успешно.")
        return redirect('upload')
    return render(request, 'core/confirm_delete.html', {'object': "всички цени", 'type': 'всички цени'})


@login_required
def transaction_delete_all(request):
    if request.method == 'POST':
        count = Transaction.objects.count()
        Transaction.objects.all().delete()
        messages.success(request, f"Всички {count} транзакции бяха изтрити успешно.")
        return redirect('upload')
    return render(request, 'core/confirm_delete.html', {'object': "всички транзакции", 'type': 'всички транзакции'})


from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, UserChangeForm


@login_required
def profile(request):
    if request.method == 'POST':
        user_form = UserChangeForm(request.POST, instance=request.user)
        # Опростен вариант за UserChangeForm (Django-вският е малко сложен за крайни потребители)
        # Ще използваме наш вариант за промяна на основни данни
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')

        request.user.email = email
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save()
        messages.success(request, "Профилът беше обновен.")
        return redirect('profile')
    return render(request, 'core/profile.html')


@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Паролата беше променена успешно.")
            return redirect('profile')
        else:
            messages.error(request, "Моля, коригирайте грешките по-долу.")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'core/change_password.html', {'form': form})


@login_required
@require_POST
def relink_data_view(request):
    count_t, count_p = relink_data()
    messages.success(request, f"Успешно свързани: {count_t} транзакции и {count_p} цени.")
    return redirect('upload')


@login_required
def analytics(request):
    companies = Company.objects.all().order_by('name')
    analytics_data = []

    grand_total_qty = 0
    grand_total_profit = 0
    grand_total_gta = 0

    report_type = request.GET.get('report', 'full')

    if report_type not in ('first', 'second', 'full'):
        report_type = 'full'

    for company in companies:
        data, t_qty, t_eko, t_gta, t_profit = get_company_report_data(
            company,
            period=report_type
        )

        if t_qty > 0:
            analytics_data.append({
                'company': company,
                'total_qty': t_qty,
                'total_gta': t_gta,
                'total_profit': t_profit
            })

            grand_total_qty += t_qty
            grand_total_profit += t_profit
            grand_total_gta += t_gta

    return render(request, 'core/analytics.html', {
        'analytics_data': analytics_data,
        'grand_total_qty': grand_total_qty,
        'grand_total_profit': grand_total_profit,
        'grand_total_gta': grand_total_gta,
        'report_type': report_type
    })


@login_required
def company_prices(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    prices = Price.objects.filter(company=company).order_by('-date', '-id')
    return render(request, 'core/company_prices.html', {
        'company': company,
        'prices': prices
    })
