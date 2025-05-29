from django.db import models
from django.conf import settings
import stripe

# Create your models here.

class PaymentStatus(models.TextChoices):
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    REFUNDED = 'refunded'

class PayoutStatus(models.TextChoices):
    PENDING = 'pending'
    IN_TRANSIT = 'in_transit'
    PAID = 'paid'
    FAILED = 'failed'
    CANCELED = 'canceled'

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

class BankAccount(models.Model):
    user = models.ForeignKey('custom_auth.User', on_delete=models.CASCADE, related_name='bank_accounts')
    account_holder_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    routing_number = models.CharField(max_length=50)
    country = models.CharField(max_length=2, default='US')
    currency = models.CharField(max_length=3, default='usd')
    is_default = models.BooleanField(default=False)
    stripe_bank_account_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.is_default:
            # Ensure only one default account per user
            BankAccount.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.account_holder_name} - ****{self.account_number[-4:]}"

class Payout(models.Model):
    user = models.ForeignKey('custom_auth.User', on_delete=models.CASCADE, related_name='payouts')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, related_name='payouts')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=PayoutStatus.choices, default=PayoutStatus.PENDING)
    stripe_payout_id = models.CharField(max_length=100, blank=True, null=True)
    failure_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Payout of ${self.amount} to {self.bank_account} ({self.status})"

class Ticket(models.Model):
    id = models.AutoField(primary_key=True)
    booking_code = models.CharField(max_length=255)
    user = models.ForeignKey('custom_auth.User', on_delete=models.CASCADE)
    gig = models.ForeignKey('gigs.Gig', on_delete=models.CASCADE)
    qr_code = models.ImageField(upload_to='gigs/qr_codes/', blank=True, null=True)
    checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True, default=None)
    checked_out = models.BooleanField(default=False)
    checked_out_at = models.DateTimeField(null=True, blank=True, default=None)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

#  suporting artist