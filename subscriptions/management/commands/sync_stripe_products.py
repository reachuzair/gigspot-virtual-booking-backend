from django.core.management.base import BaseCommand
import stripe
from django.conf import settings
from ...models import SubscriptionPlan, VenueAdPlan, SubscriptionTier

stripe.api_key = settings.STRIPE_SECRET_KEY

class Command(BaseCommand):
    help = 'Sync Stripe products with subscription tiers for both artists and venues'

    def handle(self, *args, **options):
        # Artist Tiers
        ARTIST_TIERS = {
            'FREE': {
                'monthly_price': 0.00,
                'features': [
                    'Basic profile',
                    'Limited show postings',
                    'Basic analytics'
                ]
            },
            'PREMIUM': {
                'monthly_price': 20.00,
                'features': [
                    'All Free tier features',
                    'Unlimited show postings',
                    'Advanced analytics',
                    'Priority support',
                    'Merchandise integration',
                    'Tour management'
                ]
            }
        }

        # Venue Tiers
        VENUE_TIERS = {
            'STARTER': {
                'monthly_price': 75.00,
                'weekly_price': 25.00,
                'features': ['basic_visibility', 'suggested_venue', 'city_search']
            },
            'BOOSTED': {
                'monthly_price': 150.00,
                'weekly_price': 37.50,
                'features': ['priority_search', 'custom_map_pin', 'analytics', 'all_starter_features']
            },
            'PREMIUM': {
                'monthly_price': 250.00,
                'weekly_price': 62.50,
                'features': ['homepage_feature', 'email_spotlight', 'priority_support', 'all_boosted_features']
            }
        }

        # Sync artist plans
        self.stdout.write(self.style.SUCCESS('Syncing Artist Tiers...'))
        for tier, details in ARTIST_TIERS.items():
            try:
                # Create or update the product in Stripe
                product = stripe.Product.create(
                    name=f"{tier.capitalize()}",
                    metadata={'tier': tier, 'type': 'artist'}
                )

                # Create monthly price (only for premium, free tier is $0)
                monthly_price = stripe.Price.create(
                    product=product.id,
                    unit_amount=int(details['monthly_price'] * 100),  # Convert to cents
                    currency='usd',
                    recurring={'interval': 'month'},
                    metadata={
                        'tier': tier,
                        'interval': 'month',
                        'type': 'artist'
                    }
                )

                # Update or create the subscription plan in our database
                SubscriptionPlan.objects.update_or_create(
                    subscription_tier=tier,
                    defaults={
                        'stripe_price_id': monthly_price.id,
                        'price': details['monthly_price'],
                        'billing_interval': 'month',
                        'features': details['features'],
                        'is_active': True
                    }
                )

                self.stdout.write(self.style.SUCCESS(f'✓ Synced Artist {tier} tier'))

            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error syncing Artist {tier}: {str(e)}'))

        # Sync venue plans
        self.stdout.write(self.style.SUCCESS('\nSyncing Venue Tiers...'))
        for tier, details in VENUE_TIERS.items():
            try:
                # Create or update the product in Stripe
                product = stripe.Product.create(
                    name=f"{tier.capitalize()}",
                    metadata={'tier': tier, 'type': 'venue'}
                )

                # Create monthly price
                monthly_price = stripe.Price.create(
                    product=product.id,
                    unit_amount=int(details['monthly_price'] * 100),  # Convert to cents
                    currency='usd',
                    recurring={'interval': 'month'},
                    metadata={
                        'tier': tier,
                        'interval': 'month',
                        'type': 'venue'
                    }
                )

                # Create weekly price
                weekly_price = stripe.Price.create(
                    product=product.id,
                    unit_amount=int(details['weekly_price'] * 100),  # Convert to cents
                    currency='usd',
                    recurring={'interval': 'week'},
                    metadata={
                        'tier': tier,
                        'interval': 'week',
                        'type': 'venue'
                    }
                )

                # Update or create the venue plan in our database
                VenueAdPlan.objects.update_or_create(
                    name=tier,
                    defaults={
                        'description': f"{tier.capitalize()} venue subscription",
                        'monthly_price': details['monthly_price'],
                        'weekly_price': details['weekly_price'],
                        'features': {
                            'description': f"Features for {tier} tier",
                            'features': details['features']
                        },
                        'monthly_stripe_price_id': monthly_price.id,
                        'weekly_stripe_price_id': weekly_price.id,
                        'stripe_product_id': product.id,
                        'is_active': True
                    }
                )

                self.stdout.write(self.style.SUCCESS(f'✓ Synced Venue {tier} tier'))

            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error syncing Venue {tier}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS('\nSubscription sync completed!'))

    def get_artist_tier_features(self, tier):
        """Return features description for artist tiers"""
        features = {
            'FREE': [
                'Basic artist profile',
                'Up to 3 active show postings',
                'Basic analytics dashboard',
                'Email support (72h response)'
            ],
            'PREMIUM': [
                'Unlimited show postings',
                'Advanced analytics and insights',
                'Priority customer support (24h response)',
                'Merchandise integration',
                'Tour management tools',
                'Verified badge',
                'Early access to new features'
            ]
        }
        return features.get(tier, [])

    def get_venue_tier_features(self, tier):
        """Return features description for venue tiers"""
        features = {
            'STARTER': [
                'Basic visibility for your venue',
                'Appear as "Suggested Venue" in artist dashboards',
                'Appear in city searches',
                'Basic venue profile visibility'
            ],
            'BOOSTED': [
                'Priority spot on map',
                'Always shown first in matching tier searches',
                'All Starter tier features',
                'Highlighted in search results',
                'Custom map pin',
                'Analytics access'
            ],
            'PREMIUM': [
                'Featured slot on home dashboard',
                'All Boosted tier features',
                'Premium badge on profile',
                'Priority support',
                'Featured in weekly newsletter',
                'Homepage feature',
                'Email spotlight',
                'Analytics access'
            ]
        }
        return features.get(tier, [])