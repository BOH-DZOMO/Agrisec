from django.db.models import Avg
from django.db.models import Count
from django.db.models import Max
from django.db.models import Min
from django.db.models import Prefetch
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from drf_spectacular.utils import inline_serializer
from rest_framework import mixins
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework.viewsets import ModelViewSet

from agrisec.farms.models import Farm
from agrisec.farms.models import SensorDevice
from agrisec.farms.models import TelemetryReading
from agrisec.global_utils.models import DeviceType

from .serializers import DeviceTelemetryIngestSerializer
from .serializers import FarmSerializer
from .serializers import FarmSummarySerializer
from .serializers import SensorDeviceSerializer
from .serializers import TelemetryReadingSerializer


@extend_schema_view(
    list=extend_schema(
        tags=["Farms"],
        summary="List owned farms",
        description="Returns all farms owned by the authenticated user along with device counts.",
    ),
    create=extend_schema(
        tags=["Farms"],
        summary="Create a new farm",
        description="Creates a farm and automatically assigns ownership to the authenticated user.",
    ),
    retrieve=extend_schema(tags=["Farms"], summary="Retrieve farm details"),
    update=extend_schema(tags=["Farms"], summary="Replace farm details"),
    partial_update=extend_schema(tags=["Farms"], summary="Partially update farm details"),
    destroy=extend_schema(tags=["Farms"], summary="Delete a farm"),
)
class FarmViewSet(ModelViewSet):
    serializer_class = FarmSerializer
    queryset = Farm.objects.all()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Farm.objects.none()
        return (
            Farm.objects.filter(owner=self.request.user)
            .annotate(
                device_count=Count("devices", distinct=True),
                active_device_count=Count(
                    "devices",
                    filter=Q(devices__is_active=True),
                    distinct=True,
                ),
            )
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @extend_schema(
        tags=["Farms"],
        summary="List sensor devices for a farm",
        description="Returns all IoT sensor devices registered under this farm.",
        responses={200: SensorDeviceSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def devices(self, request, pk=None):
        farm = self.get_object()
        devices_qs = (
            farm.devices.select_related("farm")
            .prefetch_related(
                Prefetch(
                    "readings",
                    queryset=TelemetryReading.objects.order_by("-timestamp"),
                    to_attr="prefetched_readings",
                ),
            )
            .order_by("-created_at")
        )
        page = self.paginate_queryset(devices_qs)
        if page is not None:
            serializer = SensorDeviceSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = SensorDeviceSerializer(devices_qs, many=True, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["Farms"],
        summary="Get aggregated farm telemetry summary",
        description=(
            "Computes device counts and min/max/average environmental metrics "
            "(temperature and soil moisture) across all sensors on this farm."
        ),
        responses={200: FarmSummarySerializer},
    )
    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        farm = self.get_object()
        readings_stats = TelemetryReading.objects.filter(device__farm=farm).aggregate(
            total_readings=Count("id"),
            avg_temperature=Avg("temperature"),
            min_temperature=Min("temperature"),
            max_temperature=Max("temperature"),
            avg_soil_moisture=Avg("soil_moisture"),
            min_soil_moisture=Min("soil_moisture"),
            max_soil_moisture=Max("soil_moisture"),
            latest_reading_at=Max("timestamp"),
        )
        payload = {
            "farm_id": farm.id,
            "farm_name": farm.name,
            "total_devices": getattr(farm, "device_count", farm.devices.count()),
            "active_devices": getattr(
                farm,
                "active_device_count",
                farm.devices.filter(is_active=True).count(),
            ),
            "total_readings": readings_stats["total_readings"] or 0,
            "avg_temperature": (
                round(readings_stats["avg_temperature"], 2)
                if readings_stats["avg_temperature"] is not None
                else None
            ),
            "min_temperature": readings_stats["min_temperature"],
            "max_temperature": readings_stats["max_temperature"],
            "avg_soil_moisture": (
                round(readings_stats["avg_soil_moisture"], 2)
                if readings_stats["avg_soil_moisture"] is not None
                else None
            ),
            "min_soil_moisture": readings_stats["min_soil_moisture"],
            "max_soil_moisture": readings_stats["max_soil_moisture"],
            "latest_reading_at": readings_stats["latest_reading_at"],
        }
        serializer = FarmSummarySerializer(payload)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Devices"],
        summary="List sensor devices",
        description="Lists all IoT sensor devices across your farms, with optional query filtering.",
        parameters=[
            OpenApiParameter(
                name="farm",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter devices by Farm UUID.",
            ),
            OpenApiParameter(
                name="device_type",
                type=OpenApiTypes.STR,
                enum=DeviceType.values,
                location=OpenApiParameter.QUERY,
                description="Filter by microcontroller hardware type.",
            ),
            OpenApiParameter(
                name="is_active",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filter by active status (`true` or `false`).",
            ),
        ],
    ),
    create=extend_schema(
        tags=["Devices"],
        summary="Register a sensor device",
        description="Registers a new hardware sensor device (ESP32, STM32, Arduino) to one of your farms.",
    ),
    retrieve=extend_schema(tags=["Devices"], summary="Retrieve sensor device details"),
    update=extend_schema(tags=["Devices"], summary="Replace sensor device details"),
    partial_update=extend_schema(tags=["Devices"], summary="Partially update sensor device"),
    destroy=extend_schema(tags=["Devices"], summary="Remove a sensor device"),
)
class SensorDeviceViewSet(ModelViewSet):
    serializer_class = SensorDeviceSerializer
    queryset = SensorDevice.objects.all()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SensorDevice.objects.none()

        qs = (
            SensorDevice.objects.filter(farm__owner=self.request.user)
            .select_related("farm")
            .prefetch_related(
                Prefetch(
                    "readings",
                    queryset=TelemetryReading.objects.order_by("-timestamp"),
                    to_attr="prefetched_readings",
                ),
            )
            .order_by("-created_at")
        )

        farm_id = self.request.query_params.get("farm")
        if farm_id:
            qs = qs.filter(farm_id=farm_id)

        device_type = self.request.query_params.get("device_type")
        if device_type:
            qs = qs.filter(device_type=device_type.upper())

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            lowered = is_active.lower()
            if lowered in {"true", "1"}:
                qs = qs.filter(is_active=True)
            elif lowered in {"false", "0"}:
                qs = qs.filter(is_active=False)

        return qs

    @extend_schema(
        tags=["Devices"],
        summary="Toggle device active status",
        description="Flips `is_active` between `true` and `false` for maintenance or decommissioning.",
        request=None,
        responses={200: SensorDeviceSerializer},
    )
    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        device = self.get_object()
        device.is_active = not device.is_active
        device.save(update_fields=["is_active"])
        serializer = self.get_serializer(device)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Devices"],
        summary="List telemetry readings for a device",
        description="Returns paginated historical telemetry readings recorded by this sensor device.",
        responses={200: TelemetryReadingSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def readings(self, request, pk=None):
        device = self.get_object()
        readings_qs = device.readings.select_related("device").order_by("-timestamp")
        page = self.paginate_queryset(readings_qs)
        if page is not None:
            serializer = TelemetryReadingSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = TelemetryReadingSerializer(readings_qs, many=True, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        tags=["Devices"],
        summary="Get latest reading for a device",
        description="Returns the single most recent telemetry reading for this device, or 404 if none exist.",
        responses={
            200: TelemetryReadingSerializer,
            404: OpenApiResponse(description="No telemetry readings recorded for this device yet."),
        },
    )
    @action(detail=True, methods=["get"], url_path="latest-reading")
    def latest_reading(self, request, pk=None):
        device = self.get_object()
        reading = device.readings.select_related("device").first()
        if reading is None:
            return Response(
                {"detail": "No telemetry readings recorded for this device yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = TelemetryReadingSerializer(reading, context={"request": request})
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Telemetry"],
        summary="List telemetry readings",
        description="Returns paginated environmental telemetry across your farms and devices.",
        parameters=[
            OpenApiParameter(
                name="device",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter readings by SensorDevice UUID.",
            ),
            OpenApiParameter(
                name="farm",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter readings by Farm UUID.",
            ),
            OpenApiParameter(
                name="since",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                description="ISO-8601 start timestamp (inclusive), e.g. `2026-08-19T00:00:00Z`.",
            ),
            OpenApiParameter(
                name="until",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                description="ISO-8601 end timestamp (inclusive), e.g. `2026-08-20T00:00:00Z`.",
            ),
        ],
    ),
    create=extend_schema(
        tags=["Telemetry"],
        summary="Record a telemetry reading (authenticated user)",
        description="Manually creates a telemetry reading for one of your sensor devices.",
    ),
    retrieve=extend_schema(tags=["Telemetry"], summary="Retrieve a telemetry reading"),
    destroy=extend_schema(tags=["Telemetry"], summary="Delete a telemetry reading"),
)
class TelemetryReadingViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    serializer_class = TelemetryReadingSerializer
    queryset = TelemetryReading.objects.all()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TelemetryReading.objects.none()

        qs = (
            TelemetryReading.objects.filter(device__farm__owner=self.request.user)
            .select_related("device", "device__farm")
            .order_by("-timestamp")
        )

        device_id = self.request.query_params.get("device")
        if device_id:
            qs = qs.filter(device_id=device_id)

        farm_id = self.request.query_params.get("farm")
        if farm_id:
            qs = qs.filter(device__farm_id=farm_id)

        since = self.request.query_params.get("since")
        if since:
            parsed_since = parse_datetime(since)
            if parsed_since is None:
                raise ValidationError({"since": "Invalid ISO-8601 datetime format."})
            qs = qs.filter(timestamp__gte=parsed_since)

        until = self.request.query_params.get("until")
        if until:
            parsed_until = parse_datetime(until)
            if parsed_until is None:
                raise ValidationError({"until": "Invalid ISO-8601 datetime format."})
            qs = qs.filter(timestamp__lte=parsed_until)

        return qs

    @extend_schema(
        tags=["Telemetry"],
        summary="Ingest telemetry from an IoT device",
        description=(
            "Hardware ingestion endpoint for microcontrollers (ESP32, STM32, Arduino). "
            "Authenticates the sensor via its registered active `mac_address` and stores "
            "temperature and/or soil moisture readings."
        ),
        request=DeviceTelemetryIngestSerializer,
        responses={
            201: TelemetryReadingSerializer,
            400: OpenApiResponse(description="Unknown/inactive MAC address or invalid sensor metrics."),
        },
    )
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def ingest(self, request):
        serializer = DeviceTelemetryIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reading = serializer.save()
        output = TelemetryReadingSerializer(reading, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class TestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Health"],
        summary="API health check",
        description="Lightweight unauthenticated endpoint verifying that the API service is reachable.",
        responses={
            200: inline_serializer(
                name="HealthCheckResponse",
                fields={"message": serializers.CharField()},
            ),
        },
    )
    def get(self, request, *args, **kwargs):
        return Response(
            {"message": "All good."},
            status=status.HTTP_200_OK,
        )
