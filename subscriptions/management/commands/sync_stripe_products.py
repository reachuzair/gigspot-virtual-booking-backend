from django.core.management.base import BaseCommand
import stripe
from django.conf import settings
from ...models import SubscriptionPlan, SubscriptionTier

stripe.api_key = settings.STRIPE_SECRET_KEY

class Command(BaseCommand):
    help = 'Sync Stripe products with subscription tiers'

    def handle(self, *args, **options):
        TIER_MAP = {
            'STARTER': {'price': 0, 'features': []},
            'ESSENTIAL': {'price': 12.99, 'features': ['basic_shows']},
            'PRO': {'price': 34.99, 'features': ['unlimited_shows', 'merch']},
            'ELITE': {'price': 89.99, 'features': ['priority_bookings']}
        }

        for tier, details in TIER_MAP.items():
            product = stripe.Product.create(
                name=f"{tier.capitalize()} Tier",
                metadata={'tier': tier}
            )

            # Create monthly price
            monthly_price = stripe.Price.create(
                product=product.id,
                unit_amount=int(details['price'] * 100),
                currency='usd',
                recurring={'interval': 'month'},
                metadata={'tier': tier, 'interval': 'month'}
            )

            # Create yearly price with 25% discount
            yearly_price = stripe.Price.create(
                product=product.id,
                unit_amount=int(details['price'] * 12 * 100 * 0.75),  # 25% discount
                currency='usd',
                recurring={'interval': 'year'},
                metadata={'tier': tier, 'interval': 'year'}
            )

            # Update or create the subscription plan
            SubscriptionPlan.objects.update_or_create(
                subscription_tier=tier,
                defaults={
                    'stripe_price_id': monthly_price.id,
                    'price': details['price'],
                    'billing_interval': 'month',
                    'features': details['features']
                }
            )

            # Create yearly subscription plan
            yearly_plan, created = SubscriptionPlan.objects.update_or_create(
                subscription_tier=f"{tier}_YEARLY",
                defaults={
                    'stripe_price_id': yearly_price.id,
                    'price': details['price'] * 12 * 0.75,
                    'billing_interval': 'year',
                    'features': details['features']
                }
            )

            self.stdout.write(self.style.SUCCESS(f'Synced {tier} tier (Monthly and Yearly)'))

    def get_features_for_tier(self, tier):
        """Return features list based on tier"""
        features = {
            SubscriptionTier.STARTER: [
                "Max Shows: 1",
                "Basic Analytics",
                "Manual Payouts"
            ],
            SubscriptionTier.ESSENTIAL: [
                "All Starter features",
                "Create Tours",
                "Create Shows",
                "Basic Merch Store",
                "Basic AI Promo",
                "Basic Analytics",
                "Manual Payouts"
            ],
            SubscriptionTier.PRO: [
                "All Essential features",
                "Unlimited Shows",
                "Advanced Analytics",
                "Automatic Payouts"
            ],
            SubscriptionTier.ELITE: [
                "All Pro features",
                "Priority Support",
                "Custom Analytics Dashboard",
                "Exclusive Promotion Opportunities"
            ],
        }
        return features.get(tier, [])