from rest_framework import serializers
import re
from .models import Vendor

class VendorSerializer(serializers.ModelSerializer):
    def validate_contact_phone(self, value):
        digits = re.sub(r"\D", "", value or "")
        if value and len(digits) < 8:
            raise serializers.ValidationError("Enter a vendor phone number with country code.")
        return f"+{digits}" if digits else ""

    class Meta:
        model = Vendor
        exclude = ["tenant"]
        read_only_fields = ["id"]
