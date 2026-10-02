from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Project, ProjectMember, Task


class ProjectAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('owner', password='test-pass')
        self.member = User.objects.create_user('member', password='test-pass')
        self.outsider = User.objects.create_user('outsider', password='test-pass')
        self.project = Project.objects.create(name='Операции', owner=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.owner)
        ProjectMember.objects.create(project=self.project, user=self.member)
        self.task = Task.objects.create(project=self.project, title='Проверка', creator=self.owner)

    def test_nonmember_cannot_read_or_change_project(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('tasks:board', args=[self.project.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('tasks:task_detail', args=[self.project.pk, self.task.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('tasks:task_move', args=[self.project.pk, self.task.pk]), {'status': 'done'}).status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'todo')

    def test_member_can_move_and_comment_but_cannot_manage_members(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('tasks:board', args=[self.project.pk])).status_code, 200)
        self.client.post(reverse('tasks:task_move', args=[self.project.pk, self.task.pk]), {'status': 'done'})
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'done')
        self.client.post(reverse('tasks:task_detail', args=[self.project.pk, self.task.pk]), {'action': 'comment', 'body': 'Готово'})
        self.assertEqual(self.task.comments.count(), 1)
        self.assertEqual(self.client.post(reverse('tasks:member_add', args=[self.project.pk]), {'account': 'outsider'}).status_code, 403)

    def test_owner_adds_member_and_removal_unassigns_tasks(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('tasks:member_add', args=[self.project.pk]), {'account': 'outsider'})
        self.assertTrue(ProjectMember.objects.filter(project=self.project, user=self.outsider).exists())
        self.task.assignee = self.outsider
        self.task.save()
        self.client.post(reverse('tasks:member_remove', args=[self.project.pk, self.outsider.pk]))
        self.task.refresh_from_db()
        self.assertIsNone(self.task.assignee)
        self.assertFalse(ProjectMember.objects.filter(project=self.project, user=self.outsider).exists())


    def test_owner_has_project_settings_actions_and_member_does_not(self):
        settings_url = reverse('tasks:settings', args=[self.project.pk])
        delete_url = reverse('tasks:project_delete', args=[self.project.pk])

        self.client.force_login(self.owner)
        response = self.client.get(reverse('tasks:projects'))
        self.assertContains(response, settings_url)
        self.assertContains(response, delete_url)
        self.assertContains(response, 'Настройки')

        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:projects'))
        self.assertNotContains(response, settings_url)
        self.assertNotContains(response, delete_url)

    def test_only_owner_can_delete_project_and_name_confirmation_is_required(self):
        delete_url = reverse('tasks:project_delete', args=[self.project.pk])

        self.client.force_login(self.member)
        self.assertEqual(self.client.get(delete_url).status_code, 403)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

        self.client.force_login(self.owner)
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Изтриване на проект')

        response = self.client.post(delete_url, {'project_name': 'грешно име'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertContains(response, 'Въведете точното име')

        response = self.client.post(delete_url, {'project_name': self.project.name}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertContains(response, 'е изтрит')

    def test_my_tasks_filters_only_assigned_and_accessible(self):
        Task.objects.create(project=self.project, title='Моя задача', assignee=self.member)
        Task.objects.create(project=self.project, title='Готова', assignee=self.member, status=Task.DONE)
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:my_tasks'))
        self.assertContains(response, 'Моя задача')
        self.assertNotContains(response, 'Готова')
        response = self.client.get(reverse('tasks:my_tasks') + '?view=completed')
        self.assertContains(response, 'Готова')
        self.assertNotContains(response, 'Моя задача')

    def test_member_edits_task_and_nonmember_cannot_download_attachment(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import Attachment
        self.client.force_login(self.member)
        response = self.client.post(reverse('tasks:task_detail', args=[self.project.pk, self.task.pk]), {
            'title': 'Нова версия', 'description': 'Описание', 'status': 'progress', 'priority': 'high', 'assignee': str(self.member.pk), 'due_date': '',
        })
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, 'Нова версия')
        upload = SimpleUploadedFile('sample.png', b'fake-image-content', content_type='image/png')
        response = self.client.post(reverse('tasks:attachment_upload', args=[self.project.pk]), {'task_id': self.task.pk, 'file': upload})
        self.assertEqual(response.status_code, 302)
        attachment = Attachment.objects.get(project=self.project)
        try:
            self.assertEqual(self.client.get(reverse('tasks:attachment_download', args=[self.project.pk, attachment.pk])).status_code, 200)
            self.client.force_login(self.outsider)
            self.assertEqual(self.client.get(reverse('tasks:attachment_download', args=[self.project.pk, attachment.pk])).status_code, 404)
        finally:
            attachment.file.delete(save=False)

    def test_invalid_project_dates(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('tasks:project_new'), {'name': 'План', 'start_date': '2026-10-10', 'target_date': '2026-10-01'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Крайният срок трябва да е след началната дата.')

    def test_board_and_list_views_keep_project_access(self):
        self.client.force_login(self.member)
        board = self.client.get(reverse('tasks:board', args=[self.project.pk]))
        self.assertContains(board, 'kanban-board')
        listing = self.client.get(reverse('tasks:board', args=[self.project.pk]) + '?view=list&q=Проверка')
        self.assertContains(listing, 'tasks-table')
        self.assertContains(listing, 'Проверка')
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('tasks:board', args=[self.project.pk]) + '?view=list').status_code, 404)

    def test_calendar_shows_deadlines_and_entries_only_for_members(self):
        from datetime import date
        from .models import CalendarEntry
        self.task.due_date = date(2026, 9, 18)
        self.task.save()
        entry = CalendarEntry.objects.create(project=self.project, title='Среща с екипа', date=date(2026, 9, 18), creator=self.owner)
        self.client.force_login(self.member)
        response = self.client.get(reverse('tasks:calendar') + '?month=2026-09&day=2026-09-18')
        self.assertContains(response, 'Среща с екипа')
        self.assertContains(response, 'Проверка')
        self.assertContains(response, 'calendar-grid')
        self.client.force_login(self.outsider)
        response = self.client.get(reverse('tasks:calendar') + '?month=2026-09&day=2026-09-18')
        self.assertNotContains(response, 'Среща с екипа')
        self.assertEqual(self.client.get(reverse('tasks:calendar_entry_edit', args=[entry.pk])).status_code, 404)

    def test_calendar_entry_creation_editing_and_project_membership(self):
        from .models import CalendarEntry
        self.client.force_login(self.member)
        url = reverse('tasks:calendar_entry_new')
        response = self.client.post(url, {'title': 'План', 'project': self.project.pk, 'date': '2026-10-04', 'start_time': '09:00', 'end_time': '10:00', 'description': 'Екипна среща'})
        self.assertEqual(response.status_code, 302)
        entry = CalendarEntry.objects.get(title='План')
        response = self.client.post(reverse('tasks:calendar_entry_edit', args=[entry.pk]), {'title': 'Обновен план', 'project': self.project.pk, 'date': '2026-10-05', 'start_time': '09:00', 'end_time': '10:00'})
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.title, 'Обновен план')
        self.client.force_login(self.outsider)
        response = self.client.post(reverse('tasks:calendar_entry_new'), {'title': 'Чужд запис', 'project': self.project.pk, 'date': '2026-10-05'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalendarEntry.objects.filter(title='Чужд запис').exists())
        self.assertEqual(self.client.post(reverse('tasks:calendar_entry_delete', args=[entry.pk])).status_code, 404)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(reverse('tasks:calendar_entry_delete', args=[entry.pk])).status_code, 302)
        self.assertFalse(CalendarEntry.objects.filter(pk=entry.pk).exists())

    def test_kanban_priority_requires_creator_and_valid_value(self):
        url = reverse('tasks:task_priority', args=[self.project.pk, self.task.pk])
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url, {'priority': 'urgent'}).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url, {'priority': 'invalid'}).status_code, 403)
        response = self.client.post(url, {'priority': 'urgent'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.priority, 'urgent')
        self.assertContains(response, 'tube-urgent')
        self.assertContains(response, 'Приоритетът на задачата е обновен.')
        self.project.archived = True
        self.project.save()
        self.assertEqual(self.client.post(url, {'priority': 'low'}).status_code, 403)

class ProjectStagesTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.owner = get_user_model().objects.create_user(username='stage_owner', password='pass')
        self.client.force_login(self.owner)

    def test_custom_steps_create_board_and_validate_moves(self):
        response = self.client.post(reverse('tasks:project_new'), {
            'name': 'Проект', 'stage_names': 'Планиране\nИзпълнение\nПроверка\nПриключено',
        })
        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(name='Проект')
        self.assertEqual([s['label'] for s in project.stages], ['Планиране', 'Изпълнение', 'Проверка', 'Приключено'])
        task = Task.objects.create(project=project, title='Задача', creator=self.owner)
        self.assertContains(self.client.get(reverse('tasks:board', args=[project.pk])), 'Проверка')
        key = project.stages[2]['key']
        self.client.post(reverse('tasks:task_move', args=[project.pk, task.pk]), {'status': key})
        task.refresh_from_db()
        self.assertEqual(task.get_status_display(), 'Проверка')
        self.assertEqual(self.client.post(reverse('tasks:task_move', args=[project.pk, task.pk]), {'status': 'invalid'}).status_code, 403)

    def test_settings_cannot_remove_stage_with_tasks(self):
        project = Project.objects.create(name='Проект', owner=self.owner)
        ProjectMember.objects.create(project=project, user=self.owner)
        Task.objects.create(project=project, title='Задача', status='review')
        response = self.client.post(reverse('tasks:settings', args=[project.pk]), {
            'name': project.name, 'stage_names': 'Начало\nРабота\nКрай',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Преместете задачите')
