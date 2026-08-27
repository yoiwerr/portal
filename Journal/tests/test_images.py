from __future__ import annotations

import base64
import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url


TEST_DATABASE_URL = os.environ.get("JOURNAL_TEST_DATABASE_URL", "")
JOURNAL_ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="JOURNAL_TEST_DATABASE_URL is not configured",
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(scope="module")
def journal():
    database_url = make_url(TEST_DATABASE_URL)
    if database_url.database != "journal_test":
        pytest.fail("image tests require the dedicated journal_test database")

    os.environ["JOURNAL_DATABASE_URL"] = TEST_DATABASE_URL
    sys.path.insert(0, str(JOURNAL_ROOT))
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    module.Base.metadata.drop_all(module.engine)
    module.Base.metadata.create_all(module.engine)

    with module.SessionLocal() as db:
        db.add(
            module.User(
                username="image_test_user",
                password_hash=module.ph.hash("test-password-not-for-production"),
            )
        )
        db.commit()

    yield module

    module.Base.metadata.drop_all(module.engine)
    module.engine.dispose()


def test_images_require_authentication(journal):
    module = journal
    with TestClient(module.app, base_url="https://testserver") as client:
        response = client.get("/journal/api/images/999999")
    assert response.status_code == 401


def test_upload_read_delete_and_entry_cleanup(journal):
    module = journal
    marker = {"X-Journal-Request": "1"}

    with TestClient(module.app, base_url="https://testserver") as client:
        login = client.post(
            "/journal/api/login",
            json={
                "username": "image_test_user",
                "password": "test-password-not-for-production",
            },
        )
        assert login.status_code == 200

        created = client.post(
            "/journal/api/entries",
            headers=marker,
            json={
                "title": "Image test",
                "entry_date": "2026-08-27",
                "content": "Attachment integration test",
            },
        )
        assert created.status_code == 201
        entry_id = created.json()["id"]

        rejected = client.post(
            f"/journal/api/entries/{entry_id}/images",
            headers=marker,
            files={"files": ("not-an-image.jpg", b"plain text", "image/jpeg")},
        )
        assert rejected.status_code == 415

        uploaded = client.post(
            f"/journal/api/entries/{entry_id}/images",
            headers=marker,
            files={"files": ("pixel.png", PNG_1X1, "image/png")},
        )
        assert uploaded.status_code == 201
        image = uploaded.json()["images"][0]
        with module.SessionLocal() as db:
            assert db.query(module.EntryImage).count() == 1

        fetched = client.get(image["url"])
        assert fetched.status_code == 200
        assert fetched.headers["content-type"] == "image/png"
        assert fetched.content == PNG_1X1

        removed = client.delete(
            f"/journal/api/images/{image['id']}",
            headers=marker,
        )
        assert removed.status_code == 204
        with module.SessionLocal() as db:
            assert db.query(module.EntryImage).count() == 0

        uploaded_again = client.post(
            f"/journal/api/entries/{entry_id}/images",
            headers=marker,
            files={"files": ("pixel.png", PNG_1X1, "image/png")},
        )
        assert uploaded_again.status_code == 201
        with module.SessionLocal() as db:
            assert db.query(module.EntryImage).count() == 1

        deleted_entry = client.delete(
            f"/journal/api/entries/{entry_id}",
            headers=marker,
        )
        assert deleted_entry.status_code == 204
        with module.SessionLocal() as db:
            assert db.query(module.EntryImage).count() == 0
