
from gigs.serializers import GigSerializer
from payments.models import Ticket
from rest_framework import serializers


class FanTicketSerializer(serializers.ModelSerializer):
    gig = GigSerializer()

    class Meta:
        model = Ticket
        fields = ['id', 'gig', 'quantity', 'purchase_date']
