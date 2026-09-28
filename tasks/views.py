from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from django.http import HttpResponseForbidden, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils.http import content_disposition_header
import mimetypes
import calendar as calendar_module
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .forms import AttachmentForm, CalendarEntryForm, CommentForm, MemberForm, ProjectForm, TaskForm
from .models import Attachment, CalendarEntry, Project, ProjectMember, Task


def render_tasks(request, template, context):
    visible = Project.objects.filter(memberships__user=request.user)
    context['sidebar_projects'] = visible.filter(archived=False).order_by('name')[:10]
    context['sidebar_open_count'] = Task.objects.filter(project__in=visible, assignee=request.user).exclude(status=Task.DONE).count()
    context['sidebar_overdue_count'] = Task.objects.filter(project__in=visible, assignee=request.user, due_date__lt=timezone.localdate()).exclude(status=Task.DONE).count()
    return render(request, template, context)


def accessible_project(user, project_id):
    return get_object_or_404(Project.objects.filter(memberships__user=user), pk=project_id)


@login_required

def projects(request):
    items = Project.objects.filter(memberships__user=request.user).annotate(total=Count('tasks', distinct=True), completed=Count('tasks', filter=Q(tasks__status=Task.DONE), distinct=True))
    return render_tasks(request, 'tasks/projects.html', {'projects': items})


@login_required
def my_tasks(request):
    scope = request.GET.get('view', 'open')
    if scope not in ('open', 'overdue', 'completed'):
        scope = 'open'
    query = Task.objects.filter(project__memberships__user=request.user, assignee=request.user).select_related('project').distinct()
    if scope == 'completed':
        query = query.filter(status=Task.DONE)
    else:
        query = query.exclude(status=Task.DONE)
        if scope == 'overdue':
            query = query.filter(due_date__lt=timezone.localdate())
    query = query.order_by('due_date', '-priority', 'created_at')
    return render_tasks(request, 'tasks/my_tasks.html', {'tasks': query, 'view': scope})


@login_required

def project_new(request):
    form = ProjectForm(request.POST or None)
    upload_form = AttachmentForm(request.POST, request.FILES) if request.FILES else None
    if request.method == 'POST' and form.is_valid() and (upload_form is None or upload_form.is_valid()):
        project = form.save(commit=False)
        project.owner = request.user
        project.save()
        ProjectMember.objects.create(project=project, user=request.user)
        if upload_form:
            upload = upload_form.cleaned_data['file']
            Attachment.objects.create(project=project, file=upload, original_name=Path(upload.name).name[:255], uploaded_by=request.user)
        return redirect('tasks:board', project_id=project.pk)
    return render_tasks(request, 'tasks/form.html', {'form': form, 'upload_form': upload_form, 'heading': 'Нов проект', 'back_url': '/tasks/'})


@login_required

def board(request, project_id):
    project = accessible_project(request.user, project_id)
    query = project.tasks.select_related('assignee')
    search = request.GET.get('q', '').strip()[:100]
    if search:
        query = query.filter(Q(title__icontains=search) | Q(description__icontains=search))
    assignee = request.GET.get('assignee', '')
    if assignee == 'mine':
        query = query.filter(assignee=request.user)
    elif assignee == 'unassigned':
        query = query.filter(assignee__isnull=True)
    priority = request.GET.get('priority', '')
    if priority in dict(Task.PRIORITIES):
        query = query.filter(priority=priority)
    view = request.GET.get('view', 'board')
    if view not in ('board', 'list'):
        view = 'board'
    columns = [(key, label, list(query.filter(status=key))) for key, label in [(stage["key"], stage["label"]) for stage in project.stages]] if view == 'board' else []
    list_tasks = query.order_by('due_date', 'position', 'created_at') if view == 'list' else []
    return render_tasks(request, 'tasks/board.html', {'project': project, 'view': view, 'columns': columns, 'list_tasks': list_tasks, 'search': search, 'assignee_filter': assignee, 'priority_filter': priority, 'priorities': Task.PRIORITIES, 'stages': project.stages, 'total_tasks': project.tasks.count(), 'done_tasks': project.tasks.filter(status=Task.DONE).count(), 'overdue_tasks': project.tasks.filter(due_date__lt=timezone.localdate()).exclude(status=Task.DONE).count(), 'member_count': project.memberships.count(), 'attachments': project.attachments.filter(task__isnull=True)})


@login_required

def project_settings(request, project_id):
    project = accessible_project(request.user, project_id)
    if project.owner_id != request.user.pk:
        return HttpResponseForbidden('Само собственикът може да управлява проекта.')
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Проектът е обновен.')
        return redirect('tasks:settings', project_id=project.pk)
    return render_tasks(request, 'tasks/settings.html', {'project': project, 'form': form, 'member_form': MemberForm(), 'members': project.memberships.select_related('user')})


@login_required
@require_POST
def member_add(request, project_id):
    project = accessible_project(request.user, project_id)
    if project.owner_id != request.user.pk:
        return HttpResponseForbidden('Само собственикът може да добавя участници.')
    form = MemberForm(request.POST)
    if form.is_valid():
        _, created = ProjectMember.objects.get_or_create(project=project, user=form.user)
        messages.success(request, 'Участникът е добавен.' if created else 'Този потребител вече участва.')
    else:
        messages.error(request, ' '.join(str(e) for errors in form.errors.values() for e in errors))
    return redirect('tasks:settings', project_id=project.pk)


@login_required
@require_POST
def member_remove(request, project_id, user_id):
    project = accessible_project(request.user, project_id)
    if project.owner_id != request.user.pk:
        return HttpResponseForbidden('Само собственикът може да премахва участници.')
    if user_id == project.owner_id:
        return HttpResponseForbidden('Собственикът не може да бъде премахнат.')
    membership = get_object_or_404(ProjectMember, project=project, user_id=user_id)
    project.tasks.filter(assignee_id=user_id).update(assignee=None)
    membership.delete()
    messages.success(request, 'Участникът е премахнат.')
    return redirect('tasks:settings', project_id=project.pk)


@login_required

def task_new(request, project_id):
    project = accessible_project(request.user, project_id)
    if project.archived:
        return HttpResponseForbidden('Проектът е архивиран.')
    form = TaskForm(request.POST or None, project=project)
    if request.method == 'POST' and form.is_valid():
        task = form.save(commit=False)
        task.project = project
        task.creator = request.user
        task.position = (project.tasks.order_by('-position').values_list('position', flat=True).first() or 0) + 1
        task.save()
        return redirect('tasks:board', project_id=project.pk)
    return render_tasks(request, 'tasks/form.html', {'project': project, 'form': form, 'heading': 'Нова задача', 'back_url': project.get_board_url if hasattr(project, 'get_board_url') else f'/tasks/{project.pk}/'})


@login_required

def task_detail(request, project_id, task_id):
    project = accessible_project(request.user, project_id)
    task = get_object_or_404(project.tasks.select_related('assignee', 'creator'), pk=task_id)
    form = TaskForm(request.POST or None, instance=task, project=project)
    comment_form = CommentForm(request.POST if request.POST.get('action') == 'comment' else None)
    if request.method == 'POST':
        if project.archived:
            return HttpResponseForbidden('Проектът е архивиран.')
        if request.POST.get('action') == 'comment':
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.task = task
                comment.author = request.user
                comment.save()
                return redirect('tasks:task_detail', project_id=project.pk, task_id=task.pk)
        elif form.is_valid():
            form.save()
            messages.success(request, 'Задачата е обновена.')
            return redirect('tasks:task_detail', project_id=project.pk, task_id=task.pk)
    return render_tasks(request, 'tasks/detail.html', {'project': project, 'task': task, 'form': form, 'comment_form': comment_form, 'comments': task.comments.select_related('author'), 'attachments': task.attachments.all()})


@login_required
@require_POST
def task_move(request, project_id, task_id):
    project = accessible_project(request.user, project_id)
    if project.archived:
        return HttpResponseForbidden('Проектът е архивиран.')
    task = get_object_or_404(project.tasks, pk=task_id)
    status = request.POST.get('status')
    if status not in {stage["key"] for stage in project.stages}:
        return HttpResponseForbidden('Невалиден статус.')
    task.status = status
    task.save(update_fields=['status', 'updated_at'])
    return redirect('tasks:board', project_id=project.pk)


@login_required
@require_POST
def task_delete(request, project_id, task_id):
    project = accessible_project(request.user, project_id)
    if project.archived:
        return HttpResponseForbidden('Проектът е архивиран.')
    task = get_object_or_404(project.tasks, pk=task_id)
    if request.user.pk not in (project.owner_id, task.creator_id):
        return HttpResponseForbidden('Нямате право да изтриете задачата.')
    task.delete()
    messages.success(request, 'Задачата е изтрита.')
    return redirect('tasks:board', project_id=project.pk)


@login_required
@require_POST
def attachment_upload(request, project_id):
    project = accessible_project(request.user, project_id)
    if project.archived:
        return HttpResponseForbidden('Проектът е архивиран.')
    task_id = request.POST.get('task_id')
    task = get_object_or_404(project.tasks, pk=task_id) if task_id else None
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        upload = form.cleaned_data['file']
        Attachment.objects.create(project=project, task=task, file=upload, original_name=Path(upload.name).name[:255], uploaded_by=request.user)
        messages.success(request, 'Файлът е прикачен.')
    else:
        messages.error(request, ' '.join(str(error) for errors in form.errors.values() for error in errors))
    return redirect('tasks:task_detail', project_id=project.pk, task_id=task.pk) if task else redirect('tasks:board', project_id=project.pk)


@login_required
def attachment_download(request, project_id, attachment_id):
    project = accessible_project(request.user, project_id)
    attachment = get_object_or_404(project.attachments, pk=attachment_id)
    mime = mimetypes.guess_type(attachment.original_name)[0] or 'application/octet-stream'
    inline = mime.startswith('image/') and mime in ('image/png', 'image/jpeg', 'image/webp', 'image/gif')
    response = FileResponse(attachment.file.open('rb'), content_type=mime)
    response['Content-Disposition'] = content_disposition_header(as_attachment=not inline, filename=attachment.original_name)
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_POST
def attachment_delete(request, project_id, attachment_id):
    project = accessible_project(request.user, project_id)
    attachment = get_object_or_404(project.attachments.select_related('task'), pk=attachment_id)
    if request.user.pk not in (project.owner_id, attachment.uploaded_by_id):
        return HttpResponseForbidden('Нямате право да премахнете файла.')
    task_id = attachment.task_id
    attachment.file.delete(save=False)
    attachment.delete()
    messages.success(request, 'Файлът е премахнат.')
    return redirect('tasks:task_detail', project_id=project.pk, task_id=task_id) if task_id else redirect('tasks:board', project_id=project.pk)


def _calendar_date(value, fallback):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


@login_required
def calendar_view(request):
    today = timezone.localdate()
    month_value = request.GET.get('month', '')
    try:
        year, month = map(int, month_value.split('-'))
        first = date(year, month, 1)
    except (ValueError, TypeError):
        first = today.replace(day=1)
    weeks = calendar_module.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
    start, end = weeks[0][0], weeks[-1][-1]
    previous_month = first - timedelta(days=1)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    selected = _calendar_date(request.GET.get('day'), today if today.month == first.month and today.year == first.year else first)
    if selected.month != first.month or selected.year != first.year:
        selected = first
    visible_projects = Project.objects.filter(memberships__user=request.user)
    entries = CalendarEntry.objects.filter(project__in=visible_projects, date__range=(start, end)).select_related('project', 'creator').distinct()
    deadlines = Task.objects.filter(project__in=visible_projects, due_date__range=(start, end)).select_related('project').distinct()
    by_date = defaultdict(list)
    for entry in entries:
        by_date[entry.date].append({'kind': 'entry', 'item': entry})
    for task in deadlines:
        by_date[task.due_date].append({'kind': 'task', 'item': task})
    rows = [{'days': [{'date': day, 'in_month': day.month == first.month, 'is_today': day == today, 'selected': day == selected, 'items': by_date[day][:3], 'extra': max(0, len(by_date[day]) - 3)} for day in week]} for week in weeks]
    return render_tasks(request, 'tasks/calendar.html', {'rows': rows, 'current_month': first, 'previous_month': previous_month, 'next_month': next_month, 'selected_day': selected, 'selected_items': by_date[selected], 'visible_projects': visible_projects.filter(archived=False)})


@login_required
def calendar_entry_new(request):
    initial = {'date': _calendar_date(request.GET.get('date'), timezone.localdate())}
    project_id = request.GET.get('project')
    if project_id and project_id.isdigit():
        initial['project'] = Project.objects.filter(pk=project_id, memberships__user=request.user, archived=False).first()
    form = CalendarEntryForm(request.POST or None, user=request.user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        entry = form.save(commit=False)
        entry.creator = request.user
        entry.save()
        messages.success(request, 'Записът е добавен в календара.')
        return redirect(f"/tasks/calendar/?month={entry.date:%Y-%m}&day={entry.date:%Y-%m-%d}")
    return render_tasks(request, 'tasks/calendar_form.html', {'form': form, 'heading': 'Нов запис в календара'})


@login_required
def calendar_entry_edit(request, entry_id):
    entry = get_object_or_404(CalendarEntry.objects.filter(project__memberships__user=request.user).select_related('project'), pk=entry_id)
    if entry.project.archived:
        return HttpResponseForbidden('Проектът е архивиран.')
    form = CalendarEntryForm(request.POST or None, instance=entry, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Записът е обновен.')
        return redirect(f"/tasks/calendar/?month={entry.date:%Y-%m}&day={entry.date:%Y-%m-%d}")
    return render_tasks(request, 'tasks/calendar_form.html', {'form': form, 'heading': 'Редактиране на запис', 'entry': entry})


@login_required
@require_POST
def calendar_entry_delete(request, entry_id):
    entry = get_object_or_404(CalendarEntry.objects.filter(project__memberships__user=request.user).select_related('project'), pk=entry_id)
    if request.user.pk not in (entry.creator_id, entry.project.owner_id):
        return HttpResponseForbidden('Нямате право да изтриете записа.')
    day = entry.date
    entry.delete()
    messages.success(request, 'Записът е изтрит.')
    return redirect(f"/tasks/calendar/?month={day:%Y-%m}&day={day:%Y-%m-%d}")


@login_required
@require_POST
def task_priority(request, project_id, task_id):
    project = accessible_project(request.user, project_id)
    task = get_object_or_404(project.tasks, pk=task_id)
    if project.archived or task.creator_id != request.user.pk:
        return HttpResponseForbidden('Само създателят може да променя приоритета от таблото.')
    priority = request.POST.get('priority')
    if priority not in dict(Task.PRIORITIES):
        return HttpResponseForbidden('Невалиден приоритет.')
    task.priority = priority
    task.save(update_fields=['priority', 'updated_at'])
    messages.success(request, 'Приоритетът на задачата е обновен.')
    return redirect('tasks:board', project_id=project.pk)
