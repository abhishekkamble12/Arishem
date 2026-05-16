from django.urls import path
from . import views

urlpatterns = [
    path("upload",  views.store_vectordb,  name="store_vectordb"),
    path("query",   views.query_vectordb,  name="query_vectordb"),
    path("files",   views.list_files,      name="list_files"),
]
