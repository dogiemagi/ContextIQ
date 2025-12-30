from django.urls import path
from .views import index, upload_file, chat

urlpatterns = [
    path('', index),
    path('upload/', upload_file),
    path('chat/', chat),
]
