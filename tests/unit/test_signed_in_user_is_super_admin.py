"""signed_in_user_is_super_admin: the session role, or the signed-in email, makes a super admin.

A super admin who signed in through tenant SSO carries session["role"] = "tenant_admin", so a
check on the role alone (as reactivate_tenant had) refuses them.
"""

from unittest.mock import patch

import pytest
from flask import Flask, session

from src.admin.utils import signed_in_user_is_super_admin


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test_secret"
    return app


def test_super_admin_role_is_enough(app):
    with app.test_request_context():
        session["role"] = "super_admin"
        with patch("src.admin.utils.helpers.is_super_admin", return_value=False):
            assert signed_in_user_is_super_admin() is True


@pytest.mark.parametrize("user", ["ops@example.com", {"email": "ops@example.com"}])
def test_sso_login_with_a_super_admin_email(app, user):
    with app.test_request_context():
        session["role"] = "tenant_admin"
        session["user"] = user
        with patch("src.admin.utils.helpers.is_super_admin", return_value=True) as check:
            assert signed_in_user_is_super_admin() is True
        check.assert_called_once_with("ops@example.com")


def test_tenant_admin_is_not(app):
    with app.test_request_context():
        session["role"] = "tenant_admin"
        session["user"] = "ops@example.com"
        with patch("src.admin.utils.helpers.is_super_admin", return_value=False):
            assert signed_in_user_is_super_admin() is False


def test_signed_out_is_not(app):
    with app.test_request_context():
        with patch("src.admin.utils.helpers.is_super_admin", return_value=False) as check:
            assert signed_in_user_is_super_admin() is False
        check.assert_called_once_with("")
