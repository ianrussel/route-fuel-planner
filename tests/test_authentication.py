"""Tests for routes/authentication.py"""

from unittest.mock import MagicMock

from django.test import TestCase, override_settings

import pytest
from rest_framework.exceptions import AuthenticationFailed

from routes.authentication import ApiKeyAuthentication


def _request(api_key_header=None):
    req = MagicMock()
    req.META = {}
    if api_key_header is not None:
        req.META["HTTP_X_API_KEY"] = api_key_header
    return req


class TestApiKeyAuthenticationNoKeyConfigured(TestCase):
    @override_settings(API_KEY="")
    def test_no_config_allows_any_request(self):
        auth = ApiKeyAuthentication()
        user, _ = auth.authenticate(_request())
        assert user.is_authenticated is True

    @override_settings(API_KEY="")
    def test_no_config_ignores_provided_header(self):
        auth = ApiKeyAuthentication()
        user, _ = auth.authenticate(_request(api_key_header="anything"))
        assert user.is_authenticated is True


class TestApiKeyAuthenticationKeyConfigured(TestCase):
    @override_settings(API_KEY="secret123")
    def test_correct_key_authenticates(self):
        auth = ApiKeyAuthentication()
        user, _ = auth.authenticate(_request(api_key_header="secret123"))
        assert user.is_authenticated is True

    @override_settings(API_KEY="secret123")
    def test_wrong_key_raises(self):
        auth = ApiKeyAuthentication()
        with pytest.raises(AuthenticationFailed, match="Invalid API key"):
            auth.authenticate(_request(api_key_header="wrongkey"))

    @override_settings(API_KEY="secret123")
    def test_missing_header_raises(self):
        auth = ApiKeyAuthentication()
        with pytest.raises(AuthenticationFailed, match="Missing X-Api-Key"):
            auth.authenticate(_request())

    @override_settings(API_KEY="secret123")
    def test_empty_header_raises(self):
        auth = ApiKeyAuthentication()
        with pytest.raises(AuthenticationFailed):
            auth.authenticate(_request(api_key_header=""))


class TestApiKeyEndToEnd(TestCase):
    @override_settings(API_KEY="mykey")
    def test_request_without_key_returns_403(self):
        resp = self.client.get("/api/route/?start=New+York&finish=LA")
        assert resp.status_code == 403

    @override_settings(API_KEY="mykey")
    def test_request_with_wrong_key_returns_403(self):
        resp = self.client.get(
            "/api/route/?start=New+York&finish=LA",
            HTTP_X_API_KEY="badkey",
        )
        assert resp.status_code == 403

    @override_settings(API_KEY="mykey")
    def test_request_with_correct_key_passes_auth(self):
        resp = self.client.get(
            "/api/route/?start=New+York&finish=LA",
            HTTP_X_API_KEY="mykey",
        )
        # Auth passed; missing geocode data gives 400, not 403
        assert resp.status_code != 403

    @override_settings(API_KEY="")
    def test_no_key_configured_allows_request(self):
        resp = self.client.get("/api/route/?start=New+York&finish=LA")
        assert resp.status_code != 403
