from django.contrib import admin
from django.urls import path

from app.ds.adapters.views.health_view import health
from app.ds.adapters.views.ingest_view import ingest
from app.ds.adapters.views.search_view import search

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("ingest", ingest),
    path("search", search),
]
