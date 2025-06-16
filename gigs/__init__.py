# Import tour-related models and views lazily to prevent circular imports

def Tour():
    from .models import Tour as T
    return T

def TourVenueSuggestion():
    from .models import TourVenueSuggestion as TVS
    return TVS

def TourVenueSuggestionsAPI():
    from .views import TourVenueSuggestionsAPI as TVSAPI
    return TVSAPI

def BookedVenuesAPI():
    from .views import BookedVenuesAPI as BVA
    return BVA

# Make tour-related views available at package level
__all__ = [
    'TourVenueSuggestionsAPI',
    'BookedVenuesAPI'
]