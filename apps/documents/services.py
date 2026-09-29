"""
АНТИПАТТЕРН «God Object»: DocumentService знает про пользователей, документы,
согласование, архив, историю, SQL и права доступа одновременно.
Пять bounded contexts (users / documents / workflow / audit / archive) смешаны в одном классе.
"""
from django.db import connection

from .models import ArchiveRecord, Approval, Document, History, User
from .utils import generate_archive_number, hash_password, is_boss, log, money


class DocumentService:

    # ------------------------------------------------------------------ users
    # АНТИПАТТЕРН: сервис документов занимается регистрацией пользователей.

    def register_user(self, data):
        user = User(
            username=data.get("username"),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            role=data.get("role", "employee"),          # УЯЗВИМОСТЬ: роль задаёт сам клиент (можно стать cfo)
            department=data.get("department", ""),
        )
        # УЯЗВИМОСТЬ: пароль хешируется самодельным MD5 без соли и кладётся в поле password
        # в формате джанговского UnsaltedMD5PasswordHasher ("md5$$<hex>"), чтобы JWT-логин работал.
        user.password = "md5$$" + hash_password(data.get("password", ""))
        user.save()
        log("user registered", user.username, user.role)
        return user

    # -------------------------------------------------------------- documents

    def create_document(self, user, data):
        # АНТИПАТТЕРН: нет транзакции. Если add_history упадёт — документ есть, истории нет.
        document = Document.objects.create(
            author=user,
            title=data.get("title", ""),
            document_type=data.get("document_type", "memo"),
            amount=data.get("amount", 0),
            content=data.get("content", ""),
        )
        print("created document", document.id, "by", user.username)
        self.add_history(document, user, "created", "", document.status)
        return document

    def update_document(self, document, user, data):
        # УЯЗВИМОСТЬ: нет проверки, что user — автор (IDOR).
        # АНТИПАТТЕРН: можно поменять сумму у документа, который уже на согласовании — маршрут не пересчитается.
        for field in ("title", "document_type", "amount", "content", "status"):
            if field in data:
                setattr(document, field, data[field])   # УЯЗВИМОСТЬ: status можно выставить напрямую
        document.save()
        self.add_history(document, user, "updated", document.status, document.status)
        return document

    def delete_document(self, document, user):
        # АНТИПАТТЕРН: история удаляется каскадом вместе с документом — аудит теряется.
        print("deleting document", document.id, "status", document.status, "by", user.username)
        document.delete()

    # --------------------------------------------------------------- workflow

    def submit_document(self, document, actor):
        if document.author_id != actor.id and actor.role != "manager":
            raise PermissionError("Недостаточно прав для отправки документа")
        if document.status != "draft":
            raise ValueError("На согласование можно отправить только черновик")
        old = document.status
        document.status = "pending_manager"
        document.save()
        self.add_history(document, actor, "submitted", old, document.status)
        return document

    def approve_document(self, document, actor, comment=""):
        # АНТИПАТТЕРН: проверка ролей строками + магические числа маршрута прямо здесь.
        st = document.status
        amount = money(document.amount)     # float вместо Decimal

        if st == "pending_manager":
            if actor.role != "manager":
                raise PermissionError("Согласовать может только руководитель")
            if amount < 1000:
                new = "approved"
            else:
                new = "pending_lawyer"
        elif st == "pending_lawyer":
            if actor.role != "lawyer":
                raise PermissionError("Согласовать может только юрист")
            if amount <= 10000:
                new = "approved"
            else:
                new = "pending_cfo"
        elif st == "pending_cfo":
            if actor.role != "cfo":
                raise PermissionError("Согласовать может только финансовый директор")
            new = "approved"
        else:
            raise ValueError("Документ сейчас нельзя согласовать")

        # АНТИПАТТЕРН: три отдельных INSERT/UPDATE без transaction.atomic.
        Approval.objects.create(document=document, approver=actor, step=st, decision="approved", comment=comment)
        document.status = new
        document.save()
        self.add_history(document, actor, "approved", st, new, comment)
        print("approved", document.id, st, "->", new)
        return document

    def reject_document(self, document, actor, comment):
        # АНТИПАТТЕРН: дублирование таблицы ролей из approve_document (copy-paste).
        st = document.status
        if st == "pending_manager" and actor.role != "manager":
            raise PermissionError("Отклонить может только руководитель")
        if st == "pending_lawyer" and actor.role != "lawyer":
            raise PermissionError("Отклонить может только юрист")
        if st == "pending_cfo" and actor.role != "cfo":
            raise PermissionError("Отклонить может только финансовый директор")
        if st not in ("pending_manager", "pending_lawyer", "pending_cfo"):
            raise ValueError("Документ сейчас нельзя отклонить")
        if not comment:
            raise ValueError("Комментарий обязателен")   # поверхностная валидация: "   " пройдёт
        Approval.objects.create(document=document, approver=actor, step=st, decision="rejected", comment=comment)
        document.status = "rejected"
        document.save()
        self.add_history(document, actor, "rejected", st, "rejected", comment)
        return document

    # ---------------------------------------------------------------- archive

    def archive_document(self, document, actor):
        if not is_boss(actor):
            raise PermissionError("Недостаточно прав для архивирования")
        if document.status != "approved":
            raise ValueError("Архивировать можно только согласованный документ")
        old = document.status
        document.status = "archived"
        document.save()
        # АНТИПАТТЕРН: если archive_number сколлизирует (unique) — статус уже сохранён, записи в архиве нет.
        archive = ArchiveRecord.objects.create(document=document, archive_number=generate_archive_number())
        self.add_history(document, actor, "archived", old, "archived")
        return archive

    # ------------------------------------------------------------------ audit

    def add_history(self, document, actor, action, old_status, new_status, comment=""):
        return History.objects.create(
            document=document, actor=actor, action=action,
            old_status=old_status, new_status=new_status, comment=comment,
        )

    # -------------------------------------------------------------- raw sql

    def search_documents_raw(self, user, search=""):
        # УЯЗВИМОСТЬ (SQL injection): параметр search конкатенируется в запрос.
        # Пример атаки: ?search=%' OR '1'='1
        sql = (
            "SELECT id, title, document_type, amount, status, author_id, created_at "
            "FROM documents_document WHERE title LIKE '%" + search + "%'"
        )
        if user.role not in ("manager", "lawyer", "cfo"):
            sql += " AND author_id = " + str(user.id)
        sql += " ORDER BY created_at DESC"
        print("SQL:", sql)
        with connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [c[0] for c in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def archive_list_raw(self, order_by="registered_at"):
        # УЯЗВИМОСТЬ (SQL injection через ORDER BY): поле сортировки подставляется без whitelist.
        sql = (
            "SELECT a.id, a.archive_number, a.registered_at, d.id AS document_id, d.title, d.amount "
            "FROM documents_archiverecord a JOIN documents_document d ON d.id = a.document_id "
            "ORDER BY " + order_by
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [c[0] for c in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]