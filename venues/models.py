from django.db import models
from custom_auth.models import Venue

class VenueProof(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="proofs")
    document = models.FileField(upload_to="venue_proofs/", null=True, blank=True)
    url = models.URLField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Proof for {self.venue.name or self.venue.id}"

