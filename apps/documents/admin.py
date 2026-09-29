from django.contrib import admin

from .models import ArchiveRecord, Approval, Document, History, User

admin.site.register(User)
admin.site.register(Document)
admin.site.register(Approval)
admin.site.register(History)
admin.site.register(ArchiveRecord)
