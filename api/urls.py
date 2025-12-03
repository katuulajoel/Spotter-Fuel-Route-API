from django.urls import path

from .views import RoutePlanningView

urlpatterns = [
    path("route/", RoutePlanningView.as_view(), name="route-planning"),
]
