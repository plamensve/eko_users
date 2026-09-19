from django import forms


MAX_UPLOAD_SIZE = 15 * 1024 * 1024
MAX_PRICE_FILES = 20


def validate_excel_file(upload):
    if not upload.name.lower().endswith((".xlsx", ".xls")):
        raise forms.ValidationError("Разрешени са само Excel файлове (.xlsx или .xls).")
    if upload.size > MAX_UPLOAD_SIZE:
        raise forms.ValidationError("Файлът е по-голям от допустимите 15 MB.")
    return upload

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
    cards_file = forms.FileField(required=False, label="Карти", validators=[validate_excel_file], widget=forms.FileInput(attrs={"accept": ".xlsx,.xls"}))
    prices_files = MultipleFileField(required=False, label="Ценови листи", validators=[validate_excel_file], widget=MultipleFileInput(attrs={"accept": ".xlsx,.xls"}))
    transactions_file = forms.FileField(required=False, label="Транзакции", validators=[validate_excel_file], widget=forms.FileInput(attrs={"accept": ".xlsx,.xls"}))

    def clean_prices_files(self):
        files = self.cleaned_data.get("prices_files")
        if not files:
            return files
        files = files if isinstance(files, list) else [files]
        if len(files) > MAX_PRICE_FILES:
            raise forms.ValidationError(f"Може да импортирате най-много {MAX_PRICE_FILES} ценови файла наведнъж.")
        return files

    def clean(self):
        cleaned = super().clean()
        if not any((cleaned.get("cards_file"), cleaned.get("prices_files"), cleaned.get("transactions_file"))):
            raise forms.ValidationError("Изберете поне един файл за импортиране.")
        return cleaned

from .models import Company, Card

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'eik', 'is_twice_monthly', 'note']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Наименование на фирмата'}),
            'eik': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ЕИК'}),
            'is_twice_monthly': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Забележка към отчетите'}),
        }

class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ['card_number', 'vehicle', 'company']
        widgets = {
            'card_number': forms.TextInput(attrs={'class': 'form-control'}),
            'vehicle': forms.TextInput(attrs={'class': 'form-control'}),
            'company': forms.Select(attrs={'class': 'form-select'}),
        }
