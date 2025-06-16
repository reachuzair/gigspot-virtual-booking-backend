from rest_framework import permissions
from subscriptions.models import ArtistSubscription

class IsArtist(permissions.BasePermission):
    """
    Custom permission to only allow artists to access the view.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and
            hasattr(request.user, 'artist')
        )

class IsVenue(permissions.BasePermission):
    """
    Custom permission to only allow venues to access the view.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and
            hasattr(request.user, 'venue')
        )

class IsTourOwner(permissions.BasePermission):
    """
    Custom permission to only allow the owner of a tour to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the tour.
        return obj.artist.user == request.user

class CanEditGig(permissions.BasePermission):
    """
    Custom permission to only allow the creator of a gig or the venue to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the creator or the venue.
        return obj.created_by == request.user or \
               (hasattr(request.user, 'venue') and obj.venue == request.user.venue)


class IsPremiumUser(permissions.BasePermission):
    """
    Custom permission to only allow users with an active premium subscription.
    This permission checks if the user has the required subscription
    to access premium features like tour creation and management.
    """
    message = "This feature requires an active premium subscription."
    
    def has_permission(self, request, view):
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return False
            
        # Check if user is an artist
        if not hasattr(request.user, 'artist_profile'):
            return False
            
        # Check if artist has an active premium subscription
        try:
            subscription = request.user.artist_profile.subscription
            return subscription and subscription.can_create_tour()
        except ArtistSubscription.DoesNotExist:
            return False
