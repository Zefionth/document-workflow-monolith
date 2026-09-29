"""
Небольшой набор связанных интеграционных тестов.
АНТИПАТТЕРН: тесты не могут быть unit — God-класс ходит в БД напрямую, DI отсутствует,
поэтому каждый тест поднимает реальную базу.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from .models import ArchiveRecord, Document, History, User
from .services import DocumentService


class ApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user(username="employee", password="pass", role="employee")
        self.manager = User.objects.create_user(username="manager", password="pass", role="manager")
        self.lawyer = User.objects.create_user(username="lawyer", password="pass", role="lawyer")
        self.cfo = User.objects.create_user(username="cfo", password="pass", role="cfo")
        self.service = DocumentService()

    def create_and_submit(self, amount):
        document = self.service.create_document(self.employee, {
            "title": "Тестовый документ",
            "document_type": "contract",
            "amount": Decimal(amount),
            "content": "Содержимое",
        })
        return self.service.submit_document(document, self.employee)

    def test_small_document_needs_manager_only(self):
        document = self.create_and_submit("999.99")
        self.service.approve_document(document, self.manager)
        document.refresh_from_db()
        self.assertEqual(document.status, "approved")

    def test_boundary_1000_needs_lawyer(self):
        document = self.create_and_submit("1000")
        self.service.approve_document(document, self.manager)
        self.assertEqual(document.status, "pending_lawyer")
        self.service.approve_document(document, self.lawyer)
        document.refresh_from_db()
        self.assertEqual(document.status, "approved")

    def test_large_document_needs_cfo(self):
        document = self.create_and_submit("10000.01")
        self.service.approve_document(document, self.manager)
        self.service.approve_document(document, self.lawyer)
        self.service.approve_document(document, self.cfo)
        document.refresh_from_db()
        self.assertEqual(document.status, "approved")
        self.assertEqual(History.objects.filter(document=document).count(), 5)

    def test_rejection_requires_comment(self):
        document = self.create_and_submit("500")
        with self.assertRaises(ValueError):
            self.service.reject_document(document, self.manager, "")

    def test_wrong_role_cannot_approve(self):
        document = self.create_and_submit("500")
        with self.assertRaises(PermissionError):
            self.service.approve_document(document, self.lawyer)

    def test_archive_after_approval(self):
        document = self.create_and_submit("500")
        self.service.approve_document(document, self.manager)
        archive = self.service.archive_document(document, self.manager)
        document.refresh_from_db()
        self.assertEqual(document.status, "archived")
        self.assertTrue(archive.archive_number.startswith("ARC-"))
        self.assertEqual(ArchiveRecord.objects.count(), 1)


class KnownVulnerabilityTests(TestCase):
    """Фиксируют намеренные уязвимости. После рефакторинга эти тесты должны быть
    инвертированы (ожидать, что дыра закрыта)."""

    def setUp(self):
        self.client = APIClient()
        self.alice = User.objects.create_user(username="alice", password="pass", role="employee")
        self.bob = User.objects.create_user(username="bob", password="pass", role="employee")
        self.service = DocumentService()

    def test_registration_uses_unsalted_md5(self):
        user = self.service.register_user({"username": "md5user", "password": "secret"})
        self.assertEqual(user.password, "md5$$5ebe2294ecd0e0f08eab7690d2a6ee69")
        self.assertTrue(user.check_password("secret"))  # логин через JWT будет работать

    def test_client_can_choose_role(self):
        response = self.client.post("/api/register/", {"username": "evil", "password": "1", "role": "cfo"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(username="evil").role, "cfo")

    def test_idor_read_other_users_document(self):
        doc = self.service.create_document(self.alice, {"title": "секрет", "amount": 10})
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get(f"/api/documents/{doc.id}/").status_code, 200)
        self.assertNotIn(doc.id, [d["id"] for d in self.client.get("/api/documents/").json()])

    def test_status_can_be_set_directly_via_put(self):
        doc = self.service.create_document(self.alice, {"title": "x", "amount": 99999})
        self.client.force_authenticate(self.alice)
        self.client.put(f"/api/documents/{doc.id}/", {"status": "approved"}, format="json")
        doc.refresh_from_db()
        self.assertEqual(doc.status, "approved")

    def test_raw_search_is_injectable(self):
        self.service.create_document(self.alice, {"title": "alice doc", "amount": 1})
        self.service.create_document(self.bob, {"title": "bob doc", "amount": 1})
        self.client.force_authenticate(self.bob)
        # Обычный поиск: bob видит только свой документ.
        self.assertEqual(len(self.client.get("/api/documents/search-raw/", {"search": "doc"}).json()), 1)
        # Инъекция: комментарий "--" отрезает фильтр по author_id.
        payload = "%' OR 1=1 --"
        self.assertEqual(len(self.client.get("/api/documents/search-raw/", {"search": payload}).json()), 2)
