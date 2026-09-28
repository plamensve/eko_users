from django.conf import settings
from django.db import models
from django.utils import timezone
from .attachments import PRIVATE_STORAGE, attachment_path, validate_attachment


class Project(models.Model):
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    objective = models.TextField(blank=True, verbose_name='Цел на проекта')
    deliverables = models.TextField(blank=True, verbose_name='Очаквани резултати')
    client = models.CharField(max_length=180, blank=True, verbose_name='Клиент / отдел')
    start_date = models.DateField(null=True, blank=True, verbose_name='Начална дата')
    target_date = models.DateField(null=True, blank=True, verbose_name='Краен срок')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='owned_projects')
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through='ProjectMember', related_name='task_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['archived', '-created_at']

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['project', 'user'], name='unique_task_project_member')]


class Task(models.Model):
    TODO = 'todo'
    PROGRESS = 'progress'
    REVIEW = 'review'
    DONE = 'done'
    STATUSES = [(TODO, 'За изпълнение'), (PROGRESS, 'В работа'), (REVIEW, 'За преглед'), (DONE, 'Готово')]
    PRIORITIES = [('low', 'Нисък'), ('normal', 'Нормален'), ('high', 'Висок'), ('urgent', 'Спешен')]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default=TODO)
    priority = models.CharField(max_length=10, choices=PRIORITIES, default='normal')
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_tasks')
    due_date = models.DateField(null=True, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'created_at']
        indexes = [models.Index(fields=['project', 'status', 'position'])]

    @property
    def overdue(self):
        return bool(self.due_date and self.status != self.DONE and self.due_date < timezone.localdate())

    def __str__(self):
        return self.title


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class Attachment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='attachments')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments', null=True, blank=True)
    file = models.FileField(storage=PRIVATE_STORAGE, upload_to=attachment_path, validators=[validate_attachment])
    original_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class CalendarEntry(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='calendar_entries')
    title = models.CharField(max_length=180, verbose_name='Заглавие')
    description = models.TextField(blank=True, verbose_name='Описание')
    date = models.DateField(db_index=True, verbose_name='Дата')
    start_time = models.TimeField(null=True, blank=True, verbose_name='Начален час')
    end_time = models.TimeField(null=True, blank=True, verbose_name='Краен час')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='calendar_entries')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'start_time', 'pk']

    def __str__(self):
        return self.title
