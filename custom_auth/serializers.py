from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ROLE_CHOICES

User = get_user_model()

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    first_name = serializers.CharField(write_only=True, required=False)
    last_name = serializers.CharField(write_only=True, required=False)
    name = serializers.CharField(write_only=True, required=False)  # For venue
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'role', 'first_name', 'last_name', 'name')
        extra_kwargs = {
            'role': {'required': True}
        }
        
    def validate(self, data):
        role = data.get('role')
        
        if role == ROLE_CHOICES.ARTIST or role == ROLE_CHOICES.FAN:
            if not data.get('first_name'):
                raise serializers.ValidationError("First name is required for this role")
                
        if role == ROLE_CHOICES.VENUE:
            if not data.get('name'):
                raise serializers.ValidationError("Venue name is required")
                
        return data
        
    def create(self, validated_data):
        # Remove role-specific fields before user creation
        validated_data.pop('first_name', None)
        validated_data.pop('last_name', None)
        validated_data.pop('name', None)
        
        user = User.objects.create_user(**validated_data)
        return user