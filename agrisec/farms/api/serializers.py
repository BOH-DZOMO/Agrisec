from rest_framework import serializers

from agrisec.users.models import User
from agrisec.farms.models import Farm


class FarmSerializer(serializers.ModelSerializer):
    class Meta:
        model = Farm
        fields = ["id", "name", "location", "created_at"]