from rest_framework import serializers
from django.db import models
from .models import BankAccount, Payout, Payment

class CountryBankInfoSerializer(serializers.Serializer):
    """
    Serializer for returning bank account requirements per country
    
    This serializer defines the structure for bank account requirements
    and specifications for different countries.
    """
    country = serializers.CharField()
    name = serializers.CharField()
    required_fields = serializers.ListField(child=serializers.CharField())
    supported_currencies = serializers.ListField(child=serializers.CharField())
    account_holder_types = serializers.ListField(child=serializers.CharField())
    account_types = serializers.ListField(child=serializers.CharField())

class BankAccountSerializer(serializers.ModelSerializer):
    """
    Serializer for bank accounts with dynamic fields based on country
    
    Handles validation and serialization of bank account information,
    with country-specific validation rules.
    """
    account_holder_type = serializers.ChoiceField(
        choices=[('individual', 'Individual'), ('company', 'Company')],
        default='individual',
        help_text="Type of account holder (individual or company)"
    )
    account_type = serializers.ChoiceField(
        choices=BankAccount.ACCOUNT_TYPES,
        default='checking',
        help_text="Type of bank account (checking or savings)"
    )
    
    class Meta:
        model = BankAccount
        fields = [
            'id', 'account_holder_name', 'account_holder_type', 'account_type',
            'country', 'currency', 'is_default', 'account_number', 
            'routing_number', 'iban', 'bank_code', 'branch_code', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'stripe_bank_account_id']
        extra_kwargs = {
            'account_number': {'write_only': True, 'required': False, 'allow_blank': True, 'allow_null': True},
            'routing_number': {'write_only': True, 'required': False, 'allow_blank': True, 'allow_null': True},
            'iban': {'write_only': True, 'required': False, 'allow_blank': True, 'allow_null': True},
            'bank_code': {'write_only': True, 'required': False, 'allow_blank': True, 'allow_null': True},
            'branch_code': {'write_only': True, 'required': False, 'allow_blank': True, 'allow_null': True},
        }
    
    def to_representation(self, instance):
        """Customize the response to include masked sensitive data"""
        ret = super().to_representation(instance)
        
        # Mask sensitive data
        if instance.iban:
            ret['masked_iban'] = f"****{instance.iban[-4:]}"
            ret.pop('iban', None)
        if instance.account_number:
            ret['masked_account_number'] = f"****{instance.account_number[-4:]}"
            ret.pop('account_number', None)
        
        # Add required fields for the country (for frontend validation)
        ret['required_fields'] = instance.get_required_fields(instance.country)
        
        return ret
    
    def validate(self, data):
        """Validate bank account based on country"""
        country = data.get('country', 'US').upper()
        
        # Validate required fields based on country
        if country in ['US', 'CA', 'GB', 'AU']:
            if not data.get('account_number') or not data.get('routing_number'):
                raise serializers.ValidationError({
                    'detail': 'Account number and routing number are required for this country.'
                })
            # Basic validation for US routing number (9 digits)
            if country == 'US' and data.get('routing_number') and not data['routing_number'].isdigit() or len(data['routing_number']) != 9:
                raise serializers.ValidationError({
                    'routing_number': 'US routing number must be 9 digits.'
                })
        elif country in ['GB', 'DE', 'FR', 'ES', 'IT', 'NL', 'BE', 'IE', 'AT', 'PT', 'CH', 'SE', 'NO', 'DK', 'FI']:
            if not data.get('iban'):
                raise serializers.ValidationError({
                    'detail': 'IBAN is required for this country.'
                })
            # Basic IBAN validation (this is a simple check, consider using a library for full validation)
            if data.get('iban') and (len(data['iban']) < 15 or len(data['iban']) > 34):
                raise serializers.ValidationError({
                    'iban': 'Invalid IBAN format.'
                })
        else:
            if not data.get('account_number') or not data.get('bank_code'):
                raise serializers.ValidationError({
                    'detail': 'Account number and bank code are required for this country.'
                })
        
        return data

class PayoutSerializer(serializers.ModelSerializer):
    """
    Serializer for payout operations
    
    Handles serialization and validation of payout requests,
    including balance verification and bank account validation.
    """
    bank_account_details = serializers.SerializerMethodField(
        help_text="Details of the linked bank account"
    )
    
    class Meta:
        model = Payout
        fields = [
            'id', 'amount', 'fee', 'status', 'stripe_payout_id',
            'created_at', 'updated_at', 'completed_at', 'bank_account',
            'bank_account_details'
        ]
        read_only_fields = [
            'user', 'status', 'stripe_payout_id', 'fee', 'completed_at'
        ]
    
    def get_bank_account_details(self, obj):
        if obj.bank_account:
            return {
                'id': obj.bank_account.id,
                'account_holder_name': obj.bank_account.account_holder_name,
                'last4': f"****{obj.bank_account.account_number[-4:]}" if obj.bank_account.account_number else None,
                'bank_name': "Bank"  # You might want to add bank name to the model
            }
        return None
    
    def validate(self, data):
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            raise serializers.ValidationError("User not found in request context")
        
        # Check if user has enough balance
        total_earnings = Payment.objects.filter(
            payee=request.user, 
            status='completed'
        ).aggregate(total_earnings=models.Sum('amount'))['total_earnings'] or 0
        
        total_payouts = Payout.objects.filter(
            user=request.user,
            status__in=['pending', 'in_transit', 'paid']
        ).aggregate(total_payouts=models.Sum('amount'))['total_payouts'] or 0
        
        available_balance = total_earnings - total_payouts
        
        if data['amount'] > available_balance:
            raise serializers.ValidationError({
                'amount': f'Insufficient balance. Available: ${available_balance:.2f}'
            })
            
        # Check if bank account exists and belongs to user
        try:
            bank_account = BankAccount.objects.get(
                id=data['bank_account'].id,
                user=request.user
            )
            data['bank_account'] = bank_account
        except BankAccount.DoesNotExist:
            raise serializers.ValidationError({
                'bank_account': 'Bank account not found or does not belong to you.'
            })
            
        return data

class PaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for payment operations
    
    Handles serialization of payment records, including related gig information
    when the payment is associated with a gig.
    """
    gig = serializers.SerializerMethodField(
        help_text="Gig details if this payment is for a gig"
    )
    
    class Meta:
        model = Payment
        fields = [
            'id', 'amount', 'status', 'created_at', 'updated_at',
            'gig', 'foreign_key', 'foreign_key_type'
        ]
        read_only_fields = fields
    
    def get_gig(self, obj):
        """
        Get gig details if the payment is for a gig
        
        Args:
            obj: Payment instance
            
        Returns:
            dict: Serialized gig data or None if not a gig payment
        """
        if obj.foreign_key_type.model == 'gig':
            from gigs.serializers import GigSerializer
            return GigSerializer(obj.foreign_key).data
        return None
