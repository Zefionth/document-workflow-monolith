from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Roles(models.TextChoices):
        EMPLOYEE = "employee", "Сотрудник"
        MANAGER = "manager", "Руководитель"
        LAWYER = "lawyer", "Юрист"
        CFO = "cfo", "Финансовый директор"

    role = models.CharField(max_length=20, choices=Roles.choices, default=Roles.EMPLOYEE)
    department = models.CharField(max_length=120, blank=True)


class Document(models.Model):
    class Types(models.TextChoices):
        CONTRACT = "contract", "Договор"
        MEMO = "memo", "Служебная записка"
        INVOICE = "invoice", "Счет"

    class Statuses(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PENDING_MANAGER = "pending_manager", "Ожидает руководителя"
        PENDING_LAWYER = "pending_lawyer", "Ожидает юриста"
        PENDING_CFO = "pending_cfo", "Ожидает финансового директора"
        APPROVED = "approved", "Согласован"
        REJECTED = "rejected", "Отклонен"
        ARCHIVED = "archived", "В архиве"

    title = models.CharField(max_length=200)
    document_type = models.CharField(max_length=20, choices=Types.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    content = models.TextField(blank=True)
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="documents")
    status = models.CharField(max_length=30, choices=Statuses.choices, default=Statuses.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Approval(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="approvals")
    approver = models.ForeignKey(User, on_delete=models.PROTECT)
    step = models.CharField(max_length=30)
    decision = models.CharField(max_length=20, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class History(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ArchiveRecord(models.Model):
    document = models.OneToOneField(Document, on_delete=models.PROTECT, related_name="archive_record")
    archive_number = models.CharField(max_length=40, unique=True)
    registered_at = models.DateTimeField(auto_now_add=True)
