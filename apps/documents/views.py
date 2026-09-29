"""
АНТИПАТТЕРН «Spaghetti Code / Fat Controller»: views одновременно принимают HTTP,
проверяют роли строками, содержат бизнес-логику, ходят в ORM напрямую и
выполняют сырой SQL через God-класс. Слоистость нарушена.
"""
from django.db import connection
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document, History
from .serializers import (
    ApprovalSerializer,
    ArchiveRecordSerializer,
    DocumentSerializer,
    HistorySerializer,
    UserSerializer,
)
from .services import DocumentService

# АНТИПАТТЕРН: глобальный синглтон сервиса, нет DI — в тестах не подменить.
service = DocumentService()


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=UserSerializer,
        responses={201: UserSerializer},
        description="Регистрация пользователя. Роль задаётся клиентом (учебная уязвимость).",
    )
    def post(self, request):
        # АНТИПАТТЕРН: сериализатор используется только для документации,
        # данные берутся напрямую из request.data без валидации.
        if not request.data.get("username") or not request.data.get("password"):
            return Response({"detail": "username и password обязательны"}, status=400)
        user = service.register_user(request.data)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.select_related("author").all()
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        # АНТИПАТТЕРН: проверка ролей хардкодом строк, копия такой же логики есть в services и utils.
        if self.request.user.role not in ("manager", "lawyer", "cfo"):
            queryset = queryset.filter(author=self.request.user)
        search = self.request.query_params.get("search", "")
        if search:
            queryset = queryset.filter(title__icontains=search)
        return queryset

    def get_object(self):
        # УЯЗВИМОСТЬ (IDOR): для detail-операций объект берётся без фильтра по владельцу,
        # любой авторизованный пользователь может читать/менять чужой документ по id.
        return get_object_or_404(Document, pk=self.kwargs["pk"])

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # АНТИПАТТЕРН: часть проверок здесь, часть в сервисе, часть нигде.
        if serializer.validated_data.get("amount") is not None and serializer.validated_data["amount"] < 0:
            print("negative amount from user", request.user.id)  # но всё равно пропускаем
        document = service.create_document(request.user, serializer.validated_data)
        return Response(self.get_serializer(document).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        document = self.get_object()
        # АНТИПАТТЕРН: мимо сериализатора и валидации — сырой dict прямо в сервис.
        service.update_document(document, request.user, request.data)
        return Response(self.get_serializer(document).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        document = self.get_object()
        # УЯЗВИМОСТЬ: удалить можно любой документ в любом статусе, даже архивный, и не только автору.
        service.delete_document(document, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._run(request, pk, service.submit_document)

    @extend_schema(request=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._run(request, pk, service.approve_document, request.data.get("comment", ""))

    @extend_schema(request=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._run(request, pk, service.reject_document, request.data.get("comment", ""))

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        document = get_object_or_404(Document, pk=pk)
        try:
            service.archive_document(document, request.user)
        except (ValueError, PermissionError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(document).data)

    @extend_schema(responses=HistorySerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        # УЯЗВИМОСТЬ (IDOR): историю чужого документа видит любой авторизованный пользователь.
        return Response(HistorySerializer(History.objects.filter(document_id=pk), many=True).data)

    @extend_schema(responses=ApprovalSerializer(many=True))
    @action(detail=True, methods=["get"])
    def approvals(self, request, pk=None):
        # АНТИПАТТЕРН: view сама пишет SQL, минуя и ORM, и сервис.
        # УЯЗВИМОСТЬ: pk из URL конкатенируется в запрос (SQL injection).
        sql = (
            "SELECT a.id, u.username, a.step, a.decision, a.comment, a.created_at "
            "FROM documents_approval a JOIN documents_user u ON u.id = a.approver_id "
            "WHERE a.document_id = " + str(pk) + " ORDER BY a.created_at"
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
        return Response([
            {"id": r[0], "approver_name": r[1], "step": r[2], "decision": r[3], "comment": r[4], "created_at": r[5]}
            for r in rows
        ])

    def _run(self, request, pk, operation, *args):
        document = get_object_or_404(Document, pk=pk)
        try:
            operation(document, request.user, *args)
        except (ValueError, PermissionError) as exc:
            # АНТИПАТТЕРН: ошибка прав и ошибка состояния возвращают одинаковый 400;
            # логирование через print без уровня и контекста.
            print("operation failed:", operation.__name__, "doc", pk, "user", request.user.id, "->", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(document).data)


class RawDocumentSearchView(APIView):
    @extend_schema(
        parameters=[OpenApiParameter("search", str, OpenApiParameter.QUERY)],
        responses=OpenApiTypes.OBJECT,
        description="Поиск документов через прямой SQL (учебная SQL injection: search=%' OR '1'='1).",
    )
    def get(self, request):
        rows = service.search_documents_raw(request.user, request.query_params.get("search", ""))
        return Response(rows)


class ArchiveListView(APIView):
    @extend_schema(
        parameters=[OpenApiParameter("order_by", str, OpenApiParameter.QUERY)],
        responses=ArchiveRecordSerializer(many=True),
        description="Список архивных записей. order_by подставляется в SQL без whitelist.",
    )
    def get(self, request):
        # АНТИПАТТЕРН: архив доступен всем авторизованным без учёта роли/отдела.
        rows = service.archive_list_raw(request.query_params.get("order_by", "registered_at"))
        return Response(rows)
