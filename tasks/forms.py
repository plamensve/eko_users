from django import forms
from django.contrib.auth import get_user_model
from .models import CalendarEntry, Project, Task, TaskComment
from .attachments import validate_attachment


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description', 'objective', 'deliverables', 'client', 'start_date', 'target_date']
        labels = {'name': 'Име на проекта', 'description': 'Описание'}
        widgets = {'description': forms.Textarea(attrs={'rows': 3}), 'objective': forms.Textarea(attrs={'rows': 3}), 'deliverables': forms.Textarea(attrs={'rows': 3}), 'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'), 'target_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ('start_date', 'target_date'):
            self.fields[field].input_formats = ['%Y-%m-%d']

    def clean(self):
        data = super().clean()
        if data.get('start_date') and data.get('target_date') and data['target_date'] < data['start_date']:
            self.add_error('target_date', 'Крайният срок трябва да е след началната дата.')
        return data


class MemberForm(forms.Form):
    account = forms.CharField(label='Потребителско име или имейл', max_length=254)

    def clean_account(self):
        value = self.cleaned_data['account'].strip()
        users = get_user_model().objects.filter(username__iexact=value)
        if not users.exists():
            users = get_user_model().objects.filter(email__iexact=value)
        if users.count() != 1 or not users.first().is_active:
            raise forms.ValidationError('Не е намерен еднозначен активен потребителски акаунт.')
        self.user = users.first()
        return value


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'status', 'priority', 'assignee', 'due_date']
        labels = {'title': 'Заглавие', 'description': 'Описание', 'status': 'Статус', 'priority': 'Приоритет', 'assignee': 'Отговорник', 'due_date': 'Краен срок'}
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'due_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = get_user_model().objects.filter(project_memberships__project=project).distinct().order_by('username')
        self.fields['assignee'].empty_label = 'Без отговорник'
        self.fields['due_date'].input_formats = ['%Y-%m-%d']


class CommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ['body']
        labels = {'body': 'Коментар'}
        widgets = {'body': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Добави коментар…'})}


class AttachmentForm(forms.Form):
    file = forms.FileField(label='Файл или снимка', validators=[validate_attachment], widget=forms.FileInput(attrs={'accept': '.png,.jpg,.jpeg,.webp,.gif,.pdf,.txt,.csv,.xlsx,.xls,.docx,.pptx,.zip'}))


class CalendarEntryForm(forms.ModelForm):
    class Meta:
        model = CalendarEntry
        fields = ['title', 'project', 'date', 'start_time', 'end_time', 'description']
        labels = {'project': 'Проект'}
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'start_time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'end_time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = Project.objects.filter(memberships__user=user, archived=False).distinct().order_by('name')
        self.fields['date'].input_formats = ['%Y-%m-%d']
        self.fields['start_time'].input_formats = ['%H:%M']
        self.fields['end_time'].input_formats = ['%H:%M']
        if self.instance.pk and self.instance.project.archived:
            self.fields['project'].queryset = self.fields['project'].queryset | Project.objects.filter(pk=self.instance.project_id, memberships__user=user)

    def clean(self):
        data = super().clean()
        if data.get('end_time') and not data.get('start_time'):
            self.add_error('start_time', 'Въведете начален час.')
        if data.get('start_time') and data.get('end_time') and data['end_time'] <= data['start_time']:
            self.add_error('end_time', 'Крайният час трябва да е след началния.')
        return data
