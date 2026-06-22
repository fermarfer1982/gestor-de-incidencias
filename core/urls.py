from django.urls import path

from core.views import AccessDeniedView, HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("acceso-denegado/", AccessDeniedView.as_view(), name="access-denied"),
]
