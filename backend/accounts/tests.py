from django.test import TestCase
from accounts.models import User


class CreateSuperuserRoleTest(TestCase):

    def test_createsuperuser_sets_role_trainer(self):
        user = User.objects.create_superuser(username='root', email='root@example.com', password='pass')
        self.assertEqual(user.role, 'trainer')

    def test_create_user_still_defaults_to_student(self):
        user = User.objects.create_user(username='stu', password='pass')
        self.assertEqual(user.role, 'student')
