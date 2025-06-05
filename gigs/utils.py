from decimal import Decimal
from django.core.exceptions import ValidationError
from custom_auth.models import PerformanceTier

class PricingValidationError(ValidationError):
    """Custom exception for pricing validation errors"""
    pass

def validate_ticket_price(tier, price):
    """
    Validate ticket price based on artist's performance tier.
    
    Args:
        tier (str): The artist's performance tier
        price (Decimal): The proposed ticket price
        
    Returns:
        dict: Validation result with 'is_valid' and 'message' keys
    """
    if not isinstance(price, (Decimal, int, float)) or price < 5:
        return {
            'is_valid': False,
            'message': 'Minimum ticket price is $5 for all artist-hosted shows.'
        }
    
    price = Decimal(str(price))
    
    # Pricing guardrails by tier (only for first three tiers)
    tier_guardrails = {
        PerformanceTier.FRESH_TALENT: {
            'min': Decimal('5'),
            'max': Decimal('10'),
            'message': 'For Fresh Talent, suggested ticket price range is $5 - $10.'
        },
        PerformanceTier.NEW_BLOOD: {
            'min': Decimal('5'),
            'max': Decimal('30'),
            'message': 'For New Blood, suggested ticket price range is $5 - $30.'
        },
        PerformanceTier.UP_AND_COMING: {
            'min': Decimal('7'),
            'max': Decimal('35'),
            'message': 'For Up & Coming, suggested ticket price range is $7 - $35.'
        }
    }
    
    # No guardrails for Rising Star and above
    if tier not in tier_guardrails:
        return {'is_valid': True, 'message': ''}
    
    guardrail = tier_guardrails[tier]
    if price < guardrail['min'] or price > guardrail['max']:
        return {
            'is_valid': False,
            'message': guardrail['message'] + ' Please confirm if you want to proceed with this price.'
        }
    
    return {'is_valid': True, 'message': ''}
