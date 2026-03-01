from rest_framework import serializers
from .models import KBEntry, TempNotice

class KBEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = KBEntry
        fields = ["id","title","body_md","tags","status","version"]

class TempNoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TempNotice
        fields = ["id","title","body","mode","scope","priority","starts_at","ends_at","enabled"]