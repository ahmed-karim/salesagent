"""Every ``url_for("<blueprint>.<endpoint>")`` literal in the admin code and templates must
name an endpoint the assembled admin app actually registers.

A dangling name is a 500 at request time (werkzeug ``BuildError``) that no route test sees
until someone clicks the button — found 2026-09-15 on the GAM OAuth authorize route
(``tenants.settings``, an endpoint that was renamed to ``tenants.tenant_settings``) and on
two more redirects (``core.admin_dashboard``, ``superadmin_settings.superadmin_settings``).
FORK.md divergence 21; upstream prebid/salesagent#1786 is the wider render-drift ticket.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
URL_FOR = re.compile(r"""url_for\(\s*["']([A-Za-z_]\w*\.\w+)["']""")


def _literals() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for root, glob in ((REPO / "src", "*.py"), (REPO / "templates", "*.html")):
        for path in root.rglob(glob):
            for match in URL_FOR.finditer(path.read_text(encoding="utf-8")):
                found.setdefault(match.group(1), set()).add(str(path.relative_to(REPO)))
    return found


@pytest.fixture(scope="module")
def registered_endpoints() -> set[str]:
    from src.admin.app import create_app
    from src.admin.blueprints.test_auth import test_auth_bp

    endpoints = set(create_app().view_functions)
    # The test-credential login blueprint is registered only when ADCP_AUTH_TEST_MODE is on
    # (src/admin/app.py), and templates/login.html names it behind the same flag. Count its
    # endpoints as registered so the guard checks the name, not the deployment mode.
    endpoints.update(f"{test_auth_bp.name}.{name}" for name in _blueprint_endpoints(test_auth_bp))
    return endpoints


def _blueprint_endpoints(blueprint) -> set[str]:
    """Endpoint names a Flask blueprint would register, read off its deferred functions."""
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(blueprint)
    return {name.split(".", 1)[1] for name in app.view_functions if name.startswith(f"{blueprint.name}.")}


def test_every_url_for_literal_names_a_registered_endpoint(registered_endpoints):
    literals = _literals()
    assert literals, "scanner found no url_for literals — regex or paths are wrong"
    dangling = {name: sorted(files) for name, files in literals.items() if name not in registered_endpoints}
    assert not dangling, "url_for() names no registered endpoint (BuildError at request time):\n" + "\n".join(
        f"  {name}: {files}" for name, files in sorted(dangling.items())
    )
