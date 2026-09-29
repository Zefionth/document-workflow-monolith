"""
Сериализаторы DRF. АНТИПАТТЕРН: валидация поверхностная — проверяются только
типы полей, а бизнес-правила (сумма > 0, тип документа, длина комментария)
разбросаны по views и services или вообще отсутствуют.
"""
from rest_framework import serializers

from .models import ArchiveRecord, Approval, Document, History, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # УЯЗВИМОСТЬ: role — writable, клиент сам выбирает себе роль cfo.
        fields = ("id", "username", "password", "first_name", "last_name", "role", "department")
        extra_kwargs = {"password": {"write_only": True}}


class DocumentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Document
        # УЯЗВИМОСТЬ: status writable — через PUT можно выставить "approved" минуя согласование.
        fields = (
            "id", "title", "document_type", "amount", "content", "author",
            "author_name", "status", "created_at", "updated_at",
        )
        read_only_fields = ("author", "created_at", "updated_at")
        # АНТИПАТТЕРН: нет validate_amount — отрицательные суммы допустимы.


class ApprovalSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source="approver.username", read_only=True)

    class Meta:
        model = Approval
        fields = ("id", "approver_name", "step", "decision", "comment", "created_at")


class HistorySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = History
        fields = ("id", "actor_name", "action", "old_status", "new_status", "comment", "created_at")


class ArchiveRecordSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="document.title", read_only=True)

    class Meta:
        model = ArchiveRecord
        fields = ("id", "document", "title", "archive_number", "registered_at")
