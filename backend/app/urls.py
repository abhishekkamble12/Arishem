from django.urls import path
from . import views

urlpatterns = [
    path("upload", views.store_vectordb, name="store_vectordb"),
]
