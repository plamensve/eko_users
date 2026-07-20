from django import forms

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result

class UploadFileForm(forms.Form):
    cards_file = forms.FileField(required=False, label="Файл с карти (cards.xlsx)")
    prices_files = MultipleFileField(required=False, label="Файл(ове) с цени (prices.xlsx)")
    transactions_file = forms.FileField(required=False, label="Файл с транзакции (eko_transactions.xlsx)")

from .models import Company, Card

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'eik', 'is_twice_monthly', 'note']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'eik': forms.TextInput(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ['card_number', 'vehicle', 'company']
        widgets = {
            'card_number': forms.TextInput(attrs={'class': 'form-control'}),
            'vehicle': forms.TextInput(attrs={'class': 'form-control'}),
            'company': forms.Select(attrs={'class': 'form-control'}),
        }
