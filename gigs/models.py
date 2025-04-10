from django.db import models
from custom_auth.models import Artist, Venue, User
from django.utils import timezone

# Create your models here.

class Gig(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    startDate = models.DateTimeField()
    endDate = models.DateTimeField()
    eventStartDate = models.DateTimeField(default=timezone.now)
    
    def default_event_end_date():
        return timezone.now() + timezone.timedelta(days=1)
    
    eventEndDate = models.DateTimeField(default=default_event_end_date)
    description = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gigs', default=None, null=True, blank=True)
    is_public = models.BooleanField(default=True)
    max_artist = models.IntegerField()
    flyer_bg = models.ImageField(upload_to='gigs/flyer_bg/', blank=True, null=True)
    flyer_text = models.CharField(max_length=255, blank=True, null=True)
    is_live = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Gig'
        verbose_name_plural = 'Gigs'

class SeatRow(models.Model):
    id = models.AutoField(primary_key=True)
    gig = models.ForeignKey('Gig', on_delete=models.CASCADE, related_name='rows')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Seat(models.Model):
    id = models.AutoField(primary_key=True)
    gig = models.ForeignKey('Gig', on_delete=models.CASCADE)
    row = models.ForeignKey('SeatRow', on_delete=models.CASCADE, related_name='seats', null=True, blank=True, default=None)
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Seat'
        verbose_name_plural = 'Seats'

class Contract(models.Model):
    id = models.AutoField(primary_key=True)
    gig = models.ForeignKey('Gig', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contracts_as_user', default=None, null=True, blank=True)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contracts_as_recipient', default=None, null=True, blank=True)
    image = models.ImageField(upload_to='gigs/contracts/', blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Contract'
        verbose_name_plural = 'Contracts'

class Application(models.Model):
    id = models.AutoField(primary_key=True)
    gig = models.ForeignKey('Gig', on_delete=models.CASCADE)
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE)
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE, default=None, null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'
