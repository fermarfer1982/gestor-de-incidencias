from django.urls import path

from erp.views import ErpIndexView

urlpatterns = [
    path("", ErpIndexView.as_view(), name="erp-index"),
]
