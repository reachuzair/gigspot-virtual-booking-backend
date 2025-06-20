
from gigs.serializers import GigSerializer
from payments.models import Ticket
from rest_framework import serializers


class FanTicketSerializer(serializers.ModelSerializer):
    gig = GigSerializer()
    quantity=serializers.IntegerField(read_only=True)

    class Meta:
        model = Ticket
        fields = ['id', 'gig', 'quantity']
