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
