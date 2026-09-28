from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CommentForm, MemberForm, ProjectForm, TaskForm
from .models import Project, ProjectMember, Task


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
    if request.method == 'POST' and form.is_valid():
        project = form.save(commit=False)
        project.owner = request.user
        project.save()
        ProjectMember.objects.create(project=project, user=request.user)
        return redirect('tasks:board', project_id=project.pk)
    return render_tasks(request, 'tasks/form.html', {'form': form, 'heading': 'Нов проект', 'back_url': '/tasks/'})


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
    columns = [(key, label, list(query.filter(status=key))) for key, label in Task.STATUSES]
    return render_tasks(request, 'tasks/board.html', {'project': project, 'columns': columns, 'search': search, 'assignee_filter': assignee, 'priority_filter': priority, 'priorities': Task.PRIORITIES, 'total_tasks': project.tasks.count(), 'done_tasks': project.tasks.filter(status=Task.DONE).count(), 'overdue_tasks': project.tasks.filter(due_date__lt=timezone.localdate()).exclude(status=Task.DONE).count(), 'member_count': project.memberships.count()})


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
    return render_tasks(request, 'tasks/detail.html', {'project': project, 'task': task, 'form': form, 'comment_form': comment_form, 'comments': task.comments.select_related('author')})


@login_required
@require_POST
def task_move(request, project_id, task_id):
    project = accessible_project(request.user, project_id)
    if project.archived:
        return HttpResponseForbidden('Проектът е архивиран.')
    task = get_object_or_404(project.tasks, pk=task_id)
    status = request.POST.get('status')
    if status not in dict(Task.STATUSES):
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
