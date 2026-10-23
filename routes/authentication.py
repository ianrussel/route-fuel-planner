from django.conf import settings

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission


class ApiKeyAuthentication(BaseAuthentication):
    """
    Checks the X-Api-Key header against API_KEY in settings.
    If API_KEY is not set, authentication is skipped (dev mode).
    """

    def authenticate(self, request):
        api_key = getattr(settings, "API_KEY", "")
        if not api_key:
            return (_AnonymousApiUser(), None)

        provided = request.META.get("HTTP_X_API_KEY", "")
        if not provided:
            raise AuthenticationFailed("Missing X-Api-Key header.")
        if provided != api_key:
            raise AuthenticationFailed("Invalid API key.")

        return (_AnonymousApiUser(), None)


class _AnonymousApiUser:
    """Minimal user object returned after successful API key auth."""

    is_authenticated = True


class ApiKeyRequired(BasePermission):
    """Allows access only when API key auth passed (or no key is configured)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class ApiKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "routes.authentication.ApiKeyAuthentication"
    name = "ApiKeyAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-Api-Key",
        }

    def get_security_requirement(self, auto_schema):
        return {"ApiKeyAuth": []}
