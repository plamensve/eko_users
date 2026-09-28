from django import forms
from django.contrib.auth import get_user_model
from .models import Project, Task, TaskComment


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


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
