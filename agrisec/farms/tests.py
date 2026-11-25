from decimal import Decimal
from http import HTTPStatus

import pytest
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from agrisec.farms.models import Farm
from agrisec.farms.models import SensorDevice
from agrisec.farms.models import TelemetryReading
from agrisec.users.models import User


@pytest.fixture
def owner(db) -> User:
    return User.objects.create_user(
        email="farmer@example.com",
        username="farmer",
        password="StrongPassword123!",
    )


@pytest.fixture
def other_user(db) -> User:
    return User.objects.create_user(
        email="other@example.com",
        username="other",
        password="StrongPassword123!",
    )


@pytest.fixture
def auth_client(owner: User) -> APIClient:
    client = APIClient()
    token = Token.objects.create(user=owner)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.mark.django_db
class TestFarmAndIoTEndpoints:
    def test_farm_crud_isolation_and_summary(
        self,
        auth_client: APIClient,
        owner: User,
        other_user: User,
    ):
        # Other user's farm must never appear in owner's farm list
        Farm.objects.create(owner=other_user, name="Neighbor Farm", location="South Valley")

        create_resp = auth_client.post(
            reverse("api:farm-list"),
            {"name": "Greenhouse Alpha", "location": "North Sector"},
            format="json",
        )
        assert create_resp.status_code == HTTPStatus.CREATED
        farm_id = create_resp.data["id"]

        list_resp = auth_client.get(reverse("api:farm-list"))
        assert list_resp.status_code == HTTPStatus.OK
        assert list_resp.data["count"] == 1
        assert list_resp.data["results"][0]["id"] == farm_id

        # Register a device and readings to verify farm summary stats
        device = SensorDevice.objects.create(
            farm_id=farm_id,
            name="Soil Probe 1",
            mac_address="AA:BB:CC:DD:EE:01",
            device_type="ESP32",
        )
        TelemetryReading.objects.create(
            device=device,
            temperature=Decimal("24.50"),
            soil_moisture=Decimal("60.00"),
        )
        TelemetryReading.objects.create(
            device=device,
            temperature=Decimal("28.50"),
            soil_moisture=Decimal("50.00"),
        )

        summary_resp = auth_client.get(reverse("api:farm-summary", kwargs={"pk": farm_id}))
        assert summary_resp.status_code == HTTPStatus.OK
        assert summary_resp.data["total_devices"] == 1
        assert summary_resp.data["active_devices"] == 1
        assert summary_resp.data["total_readings"] == 2
        assert Decimal(summary_resp.data["avg_temperature"]) == Decimal("26.50")
        assert Decimal(summary_resp.data["min_soil_moisture"]) == Decimal("50.00")
        assert Decimal(summary_resp.data["max_soil_moisture"]) == Decimal("60.00")

        farm_devices_resp = auth_client.get(reverse("api:farm-devices", kwargs={"pk": farm_id}))
        assert farm_devices_resp.status_code == HTTPStatus.OK
        assert farm_devices_resp.data["count"] == 1

    def test_device_registration_ownership_and_actions(
        self,
        auth_client: APIClient,
        owner: User,
        other_user: User,
    ):
        own_farm = Farm.objects.create(owner=owner, name="My Orchard")
        foreign_farm = Farm.objects.create(owner=other_user, name="Foreign Orchard")

        # Cannot attach a sensor device to someone else's farm
        forbidden_resp = auth_client.post(
            reverse("api:device-list"),
            {
                "farm": str(foreign_farm.id),
                "name": "Rogue Sensor",
                "mac_address": "aa-bb-cc-11-22-33",
                "device_type": "ESP32",
            },
            format="json",
        )
        assert forbidden_resp.status_code == HTTPStatus.BAD_REQUEST
        assert "farm" in forbidden_resp.data

        # Registering on own farm normalizes MAC address to uppercase colons
        ok_resp = auth_client.post(
            reverse("api:device-list"),
            {
                "farm": str(own_farm.id),
                "name": "Orchard Sensor",
                "mac_address": "aa-bb-cc-11-22-33",
                "device_type": "STM32",
            },
            format="json",
        )
        assert ok_resp.status_code == HTTPStatus.CREATED
        assert ok_resp.data["mac_address"] == "AA:BB:CC:11:22:33"
        device_id = ok_resp.data["id"]

        # Latest reading returns 404 before any telemetry exists
        empty_latest = auth_client.get(
            reverse("api:device-latest-reading", kwargs={"pk": device_id}),
        )
        assert empty_latest.status_code == HTTPStatus.NOT_FOUND

        # Toggle active flips True -> False
        toggle_resp = auth_client.post(
            reverse("api:device-toggle-active", kwargs={"pk": device_id}),
        )
        assert toggle_resp.status_code == HTTPStatus.OK
        assert toggle_resp.data["is_active"] is False

    def test_iot_telemetry_ingest_and_validation(
        self,
        auth_client: APIClient,
        owner: User,
    ):
        farm = Farm.objects.create(owner=owner, name="Hydroponics Bay")
        device = SensorDevice.objects.create(
            farm=farm,
            name="Bay Node",
            mac_address="11:22:33:44:55:66",
            device_type="ARDUINO",
            is_active=True,
        )

        anon_client = APIClient()
        ingest_url = reverse("api:reading-ingest")

        # Valid unauthenticated IoT hardware ingestion using MAC address
        ingest_resp = anon_client.post(
            ingest_url,
            {
                "mac_address": "11-22-33-44-55-66",
                "temperature": "23.75",
                "soil_moisture": "72.40",
            },
            format="json",
        )
        assert ingest_resp.status_code == HTTPStatus.CREATED
        assert ingest_resp.data["device_name"] == "Bay Node"

        # Latest reading endpoint now returns the ingested reading
        latest_resp = auth_client.get(
            reverse("api:device-latest-reading", kwargs={"pk": device.id}),
        )
        assert latest_resp.status_code == HTTPStatus.OK
        assert Decimal(latest_resp.data["temperature"]) == Decimal("23.75")

        # Out-of-range soil moisture (>100) is rejected
        bad_moisture = anon_client.post(
            ingest_url,
            {"mac_address": "11:22:33:44:55:66", "soil_moisture": "120.00"},
            format="json",
        )
        assert bad_moisture.status_code == HTTPStatus.BAD_REQUEST

        # Inactive sensor device is rejected during ingestion
        device.is_active = False
        device.save(update_fields=["is_active"])
        inactive_resp = anon_client.post(
            ingest_url,
            {"mac_address": "11:22:33:44:55:66", "temperature": "21.00"},
            format="json",
        )
        assert inactive_resp.status_code == HTTPStatus.BAD_REQUEST

    def test_logout_revokes_token(self, auth_client: APIClient, owner: User):
        logout_resp = auth_client.post(reverse("logout"))
        assert logout_resp.status_code == HTTPStatus.OK
        assert not Token.objects.filter(user=owner).exists()
