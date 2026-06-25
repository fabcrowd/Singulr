"""Static verify page copy tests."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_verify_html_shows_account_restricted() -> None:
    """Blocked state uses generic restricted copy."""
    html = (REPO / "static" / "verify.html").read_text(encoding="utf-8")
    assert "Account restricted" in html
    assert "fraud prevention" not in html.lower()


def test_verify_html_has_pending_state() -> None:
    """Under-review state is distinct from restricted."""
    html = (REPO / "static" / "verify.html").read_text(encoding="utf-8")
    assert 'id="pending"' in html
    assert "Verification under review" in html


def test_verify_js_routes_pending_decision() -> None:
    """Client shows pending panel for pending/flag decisions."""
    js = (REPO / "static" / "verify.js").read_text(encoding="utf-8")
    assert 'show("pending")' in js
    assert "result.decision === \"pending\"" in js
