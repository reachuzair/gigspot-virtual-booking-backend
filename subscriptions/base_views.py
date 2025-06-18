"""Base views for subscription management."""
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import Http404

from .services import PlanService


class BaseSubscriptionView(APIView):
    """
    Base view for subscription management.
    Handles common subscription operations for both artist and venue subscriptions.
    """
    permission_classes = [IsAuthenticated]
    plan_model = None
    subscription_model = None
    profile_relation = None
    subscription_type = None

    def get_plan(self, plan_id):
        """
        Retrieve a plan by ID, handling both prefixed and raw IDs.
        Expected format for plan_id: 'artist_123' or 'venue_456' or just the numeric ID.
        """
        # Remove prefix if present (e.g., 'artist_123' -> '123')
        if '_' in str(plan_id):
            plan_id = plan_id.split('_')[-1]
            
        try:
            plan_id = int(plan_id)  # Ensure it's a valid integer
            plan = PlanService.get_plan_by_id(self.plan_model, plan_id)
            if not plan:
                raise Http404("Plan not found")
            return plan
        except (ValueError, TypeError):
            raise Http404("Invalid plan ID format")

    def get_subscription(self, profile):
        """Retrieve active subscription for a profile if it exists."""
        try:
            return self.subscription_model.objects.get(
                **{self.profile_relation: profile},
                status='active'
            )
        except self.subscription_model.DoesNotExist:
            return None

    def get_profile(self, user):
        """Retrieve the user's profile (artist or venue)."""
        return getattr(user, self.user_profile_attr, None)

    def post(self, request):
        """Handle subscription creation request."""
        profile = self.get_profile(request.user)
        if not profile:
            return self._error_response("User profile not found")

        plan_id = request.data.get('plan_id')
        if not plan_id:
            return self._error_response("Plan ID is required")

        try:
            plan = self.get_plan(plan_id)
            return self._subscription_creation_response(plan)
        except Http404:
            return self._error_response("Invalid plan")

    def delete(self, request):
        """Handle subscription cancellation request."""
        profile = self.get_profile(request.user)
        if not profile:
            return self._error_response("User profile not found")

        subscription = self.get_subscription(profile)
        if not subscription:
            return self._error_response("No active subscription found", status.HTTP_404_NOT_FOUND)

        try:
            subscription.cancel_at_period_end = True
            subscription.status = 'canceled'
            subscription.save(update_fields=['cancel_at_period_end', 'status', 'updated_at'])
            return Response({"status": "subscription_will_cancel"})
        except Exception as e:
            return self._error_response(str(e))

    def get(self, request):
        """Retrieve current subscription details."""
        profile = self.get_profile(request.user)
        if not profile:
            return self._error_response("User profile not found")

        subscription = self.get_subscription(profile)
        if not subscription:
            return Response({"status": "no_subscription"})

        return self._subscription_details(subscription)

    def _error_response(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        """Helper method for error responses."""
        return Response({"error": message}, status=status_code)

    def _get_plan_name(self, plan):
        """Get the display name of a plan based on its type."""
        if hasattr(plan, 'get_subscription_tier_display'):  # For SubscriptionPlan
            return plan.get_subscription_tier_display()
        elif hasattr(plan, 'get_name_display'):  # For VenueAdPlan
            return plan.get_name_display()
        return str(plan.id)
        
    def _subscription_creation_response(self, plan):
        """Prepare subscription creation response."""
        return Response({
            "plan_id": str(plan.id),
            "plan_name": self._get_plan_name(plan),
            "price": str(plan.price if hasattr(plan, 'price') else plan.monthly_price),
            "subscription_type": self.subscription_type,
            "next_step": "process_payment"
        })

    def _subscription_details(self, subscription):
        """Prepare subscription details response."""
        plan = subscription.plan
        return Response({
            "status": subscription.status,
            "plan": {
                "id": str(plan.id),
                "name": self._get_plan_name(plan),
                "price": str(plan.price if hasattr(plan, 'price') else plan.monthly_price),
                "billing_interval": getattr(plan, 'billing_interval', 'month')
            },
            "current_period_end": (
                subscription.current_period_end.isoformat() 
                if subscription.current_period_end 
                else None
            ),
            "cancel_at_period_end": getattr(subscription, 'cancel_at_period_end', False)
        })