from django.urls import include, path

from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

_public = {"authentication_classes": [], "permission_classes": []}

urlpatterns = [
    path("api/", include("routes.urls")),
    path("api/schema/", SpectacularAPIView.as_view(**_public), name="schema"),
    path(
        "api/docs/", SpectacularSwaggerView.as_view(url_name="schema", **_public), name="swagger-ui"
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema", **_public), name="redoc"),
]
