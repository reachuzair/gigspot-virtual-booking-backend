from django.db import models

# Create your models here.

class CartItem(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey('custom_auth.User', on_delete=models.CASCADE)
    gig = models.ForeignKey('gigs.Gig', on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    is_booked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user} - {self.gig} - {self.quantity}"