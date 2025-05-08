from django.db import models

# Create your models here.

class PaymentStatus(models.TextChoices):
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'

class Payment(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey('custom_auth.User', on_delete=models.CASCADE)
    payee = models.ForeignKey('custom_auth.User', on_delete=models.CASCADE, related_name='payee')
    status = models.CharField(max_length=255, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_intent_id = models.CharField(max_length=255, unique=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2)
    foreign_key = models.IntegerField()
    foreign_key_type = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)