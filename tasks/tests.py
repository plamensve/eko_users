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
