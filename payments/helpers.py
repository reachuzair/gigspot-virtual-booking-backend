from custom_auth.models import Artist

def handle_account_update(account):
    artist = Artist.objects.get(stripe_account_id=account.id)

    if account['charges_enabled'] and account['payouts_enabled']:
        artist.stripe_onboarding_completed = True
        artist.save()