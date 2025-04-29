from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ROLE_CHOICES
from utils.email import send_templated_email
from users.models import UserSettings

User = get_user_model()

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    name = serializers.CharField(write_only=True, required=False)  # For venue
    
    class Meta:
        model = User
        fields = ('email', 'password', 'role', 'name')
        extra_kwargs = {
            'role': {'required': True}
        }
        
    def validate(self, data):
        print("serializer validate")
        role = data.get('role')
        
        if role == ROLE_CHOICES.ARTIST or role == ROLE_CHOICES.FAN:
            if not data.get('name'):
                raise serializers.ValidationError("Name is required for this role")
                
        if role == ROLE_CHOICES.VENUE:
            if not data.get('name'):
                raise serializers.ValidationError("Venue name is required")
                
        return data
        
    def create(self, validated_data):
        print("serializer create")
        # Remove role-specific fields before user creation
        
        user = User.objects.create_user(**validated_data)
        UserSettings.objects.create(user=user)

        otp = user.gen_otp()
        send_templated_email('OTP Verification', [user.email], 'otp_verification', {'otp': otp})

        return user

from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'name',
            'role',
            'is_active',
            'created_at',
            'updated_at',
        ]
    