from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('fuel-cards/', views.fuel_card_chains, name='fuel_card_chains'),
    path('fuel-cards/eko/', views.index, name='index'),
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('upload/', views.upload_files, name='upload'),
    path('companies/', views.company_list, name='company_list'),
    path('companies/suggestions/', views.company_search_suggestions, name='company_search_suggestions'),
    path('companies/<int:company_id>/', views.company_transactions, name='company_transactions'),
    path('companies/<int:company_id>/excel/', views.export_excel, name='export_excel'),
    path('companies/<int:company_id>/pdf/', views.export_pdf, name='export_pdf'),
    path('companies/<int:company_id>/prices/', views.company_prices, name='company_prices'),
    path('companies/<int:company_id>/zip/', views.export_company_zip_view, name='export_company_zip'),
    path('companies/export-all/', views.export_all_zip, name='export_all_zip'),
    path('analytics/', views.analytics, name='analytics'),
    
    # Company CRUD
    path('companies/add/', views.company_add, name='company_add'),
    path('companies/delete-all/', views.company_delete_all, name='company_delete_all'),
    path('companies/<int:company_id>/edit/', views.company_edit, name='company_edit'),
    path('companies/<int:company_id>/delete/', views.company_delete, name='company_delete'),
    
    # Card CRUD
    path('cards/', views.card_list, name='card_list'),
    path('cards/add/', views.card_add, name='card_add'),
    path('cards/delete-all/', views.card_delete_all, name='card_delete_all'),
    path('prices/', views.price_list, name='price_list'),
    path('prices/delete-all/', views.price_delete_all, name='price_delete_all'),
    path('transactions/delete-all/', views.transaction_delete_all, name='transaction_delete_all'),
    path('cards/<int:card_id>/edit/', views.card_edit, name='card_edit'),
    path('cards/<int:card_id>/delete/', views.card_delete, name='card_delete'),
    
    # Profile
    path('profile/', views.profile, name='profile'),
    path('profile/password/', views.change_password, name='change_password'),
    path('relink-data/', views.relink_data_view, name='relink_data'),
]
