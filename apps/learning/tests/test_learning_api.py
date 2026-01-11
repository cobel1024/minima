import pytest
from django.test.client import Client

from conftest import AdminUser


@pytest.mark.e2e
@pytest.mark.django_db
def test_enrollment_flow(client: Client, admin_user: AdminUser):
    admin_user.login()

    # get enrollments
    res = client.get("/api/v1/learning/enrollment")
    assert res.status_code == 200, "get enrollments"

    # get records
    res = client.get("/api/v1/learning/record")
    assert res.status_code == 200, "get records"

    # get catalogs
    res = client.get("/api/v1/learning/catalog")
    assert res.status_code == 200, "get catalogs"
