from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Venue, VenueTier

@receiver(pre_save, sender=Venue)
def set_venue_tier_based_on_capacity(sender, instance, **kwargs):
    """
    Signal to automatically set the venue tier based on capacity.
    This will be triggered whenever a Venue instance is saved.
    """
    if instance.capacity is not None:
        # Only proceed if capacity is set
        try:
            # Find the appropriate tier based on capacity
            tier = VenueTier.objects.filter(
                min_capacity__lte=instance.capacity,
                max_capacity__gte=instance.capacity
            ).order_by('min_capacity').first()
            
            if tier and (not instance.tier or instance.tier != tier):
                instance.tier = tier
        except VenueTier.DoesNotExist:
            # If no matching tier is found, set to None
            instance.tier = None
    elif instance.tier:
        # If capacity is None but tier is set, clear the tier
        instance.tier = None
