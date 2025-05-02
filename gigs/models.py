from django.db import models
from custom_auth.models import Artist, Venue, User, PerformanceTier
from django.utils import timezone

# Create your models here.

class GenreChoices(models.TextChoices):
    RAP = 'rap', 'Rap'
    HIP_HOP = 'hip_hop', 'Hip Hop'
    POP = 'pop', 'Pop'
    

class Gig(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    booking_start_date = models.DateTimeField()
    booking_end_date = models.DateTimeField()
    event_date = models.DateTimeField(default=timezone.now)
    description = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gigs', default=None, null=True, blank=True)
    is_public = models.BooleanField(default=True)
    max_artist = models.IntegerField()
    max_tickets = models.IntegerField(default=100)
    ticket_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    genre = models.CharField(max_length=255, choices=GenreChoices.choices, default=GenreChoices.RAP)
    minimum_performance_tier = models.CharField(max_length=255, choices=PerformanceTier.choices, default=PerformanceTier.FRESH_TALENT)
    request_message = models.TextField(blank=True, null=True, default="")
    flyer_bg = models.ImageField(upload_to='gigs/flyer_bg/', blank=True, null=True)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='gigs', default=None, null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Set expires_at to 10 minutes after created_at if not already set
        if not self.expires_at and self.created_at:
            self.expires_at = self.created_at + timezone.timedelta(minutes=10)
        super(Gig, self).save(*args, **kwargs)


    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Gig'
        verbose_name_plural = 'Gigs'

class Contract(models.Model):
    id = models.AutoField(primary_key=True)
    gig = models.ForeignKey('Gig', on_delete=models.CASCADE)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='contracts', default=None, null=True, blank=True)
    venue_signed = models.BooleanField(default=False)
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='contracts', default=None, null=True, blank=True)
    artist_signed = models.BooleanField(default=False)
    pdf = models.FileField(upload_to='gigs/contracts/', blank=True, null=True)
    image = models.ImageField(upload_to='gigs/contracts/', blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Contract'
        verbose_name_plural = 'Contracts'
    
