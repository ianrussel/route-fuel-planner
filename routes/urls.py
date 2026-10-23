from django.urls import path

from .views import MapView, RouteView

urlpatterns = [
    path("route/", RouteView.as_view(), name="route"),
    path("route/map/", MapView.as_view(), name="route-map"),
]
