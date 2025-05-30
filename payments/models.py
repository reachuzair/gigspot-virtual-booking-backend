from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
import stripe

# Create your models here.

class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    REFUNDED = 'refunded', 'Refunded'


class PayoutStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    IN_TRANSIT = 'in_transit', 'In Transit'
    PAID = 'paid', 'Paid'
    FAILED = 'failed', 'Failed'
    CANCELED = 'canceled', 'Canceled'

class Payment(models.Model):
    """Represents a payment transaction."""
    user = models.ForeignKey('custom_auth.User', on_delete=models.CASCADE, related_name='payments')
    payee = models.ForeignKey('custom_auth.User', on_delete=models.CASCADE, related_name='received_payments')
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_intent_id = models.CharField(max_length=255, unique=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gig = models.ForeignKey('gigs.Gig', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['payee']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Payment {self.id}: ${self.amount} ({self.status})"


class BankAccount(models.Model):
    ACCOUNT_TYPES = [
        ('checking', 'Checking'),
        ('savings', 'Savings'),
    ]
    
    ACCOUNT_HOLDER_TYPES = [
        ('individual', 'Individual'),
        ('company', 'Company'),
    ]
    
    user = models.ForeignKey('custom_auth.User', on_delete=models.CASCADE, related_name='bank_accounts')
    account_holder_name = models.CharField(max_length=255)
    account_holder_type = models.CharField(
        max_length=20, 
        choices=ACCOUNT_HOLDER_TYPES, 
        default='individual'
    )
    account_type = models.CharField(
        max_length=20, 
        choices=ACCOUNT_TYPES, 
        default='checking'
    )
    country = models.CharField(max_length=2, default='US')
    currency = models.CharField(max_length=3, default='usd')
    is_default = models.BooleanField(default=False)
    
    # Bank account details (format depends on country)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    routing_number = models.CharField(max_length=50, blank=True, null=True)  # For US/CA/UK/AU
    iban = models.CharField(max_length=50, blank=True, null=True)  # For SEPA countries
    bank_code = models.CharField(max_length=50, blank=True, null=True)  # For other countries
    
    # Stripe integration
    stripe_bank_account_id = models.CharField(max_length=100, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_default', '-created_at']
        verbose_name = 'Bank Account'
        verbose_name_plural = 'Bank Accounts'
    
    def __str__(self):
        if self.iban:
            return f"{self.account_holder_name} - {self.iban[-4:]}"
        return f"{self.account_holder_name} - ****{self.account_number[-4:] if self.account_number else '****'}"
    
    def clean(self):
        """Validate bank account details based on country."""
        if self.country in ['US', 'CA', 'GB', 'AU']:
            if not self.account_number or not self.routing_number:
                raise ValidationError('Account number and routing number are required for this country')
        else:
            if not self.iban:
                raise ValidationError('IBAN is required for this country')
    
    def save(self, *args, **kwargs):
        if self.is_default:
            BankAccount.objects.filter(
                user=self.user, 
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class Payout(models.Model):
    """Represents a payout to a user's bank account."""
    user = models.ForeignKey(
        'custom_auth.User', 
        on_delete=models.CASCADE, 
        related_name='payouts'
    )
    bank_account = models.ForeignKey(
        BankAccount, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='payouts'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, 
        choices=PayoutStatus.choices, 
        default=PayoutStatus.PENDING
    )
    stripe_payout_id = models.CharField(max_length=100, blank=True, null=True)
    failure_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Payout #{self.id}: ${self.amount} ({self.status})"
    
    @property
    def net_amount(self):
        """Calculate the net amount after fees."""
        return self.amount - self.fee


class Ticket(models.Model):
    """Represents a ticket for an event/gig."""
    booking_code = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique code for ticket validation"
    )
    user = models.ForeignKey(
        'custom_auth.User',
        on_delete=models.CASCADE,
        related_name='tickets'
    )
    gig = models.ForeignKey(
        'gigs.Gig',
        on_delete=models.CASCADE,
        related_name='tickets'
    )
    qr_code = models.ImageField(
        upload_to='tickets/qr_codes/',
        blank=True,
        null=True,
        help_text="QR code for ticket validation"
    )
    checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out = models.BooleanField(default=False)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price at the time of purchase"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['gig']),
            models.Index(fields=['booking_code']),
            models.Index(fields=['checked_in']),
        ]

    def __str__(self):
        return f"Ticket {self.booking_code} - {self.gig.title}"
    
    def check_in(self):
        """Mark the ticket as checked in."""
        if not self.checked_in:
            from django.utils import timezone
            self.checked_in = True
            self.checked_in_at = timezone.now()
            self.save(update_fields=['checked_in', 'checked_in_at', 'updated_at'])
    
    def check_out(self):
        """Mark the ticket as checked out."""
        if not self.checked_out:
            from django.utils import timezone
            self.checked_out = True
            self.checked_out_at = timezone.now()
            self.save(update_fields=['checked_out', 'checked_out_at', 'updated_at'])