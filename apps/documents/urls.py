from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ArchiveListView, DocumentViewSet, RawDocumentSearchView, RegisterView

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")

# АНТИПАТТЕРН: маршруты пяти доменных зон (users, documents, workflow, audit, archive)
# перечислены в одном urls.py одного приложения.
urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("documents/search-raw/", RawDocumentSearchView.as_view(), name="document-search-raw"),
    path("archive/", ArchiveListView.as_view(), name="archive-list"),
    path("", include(router.urls)),
]
