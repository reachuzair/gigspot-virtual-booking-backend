from .models import Artist, Fan, User, Venue
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ROLE_CHOICES
from utils.email import send_templated_email
from users.models import UserSettings
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


class ArtistSerializer(serializers.ModelSerializer):
    logo = serializers.ImageField(read_only=True)
    profileImage = serializers.ImageField(source='logo', read_only=True)

    class Meta:
        model = Artist
        fields = ['full_name', 'phone_number', 'band_name',
                  'band_email', 'logo', 'city', 'state', 'profileImage']


class VenueSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    profileImage = serializers.ImageField(source='logo', read_only=True)

    class Meta:
        model = Venue
        fields = (
            'name',
            'phone_number',
            'logo',
            'city', 'state', 'address', 'capacity', 'amenities',
            'reservation_fee', 'artist_capacity', 'is_completed',
            'stripe_account_id', 'stripe_onboarding_completed',
            'profileImage'

        )

    def get_name(self, obj):
        return obj.user.name


class FanSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Fan
        fields = (
            'name',
        )

    def get_name(self, obj):
        return obj.user.name if obj.user else None


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={
                                     'input_type': 'password'})

    # Shared fields
    full_name = serializers.CharField(write_only=True, required=False)
    name = serializers.CharField(
        write_only=True, required=False)  # For Venue and Fan
    phone_number = serializers.CharField(write_only=True, required=False)
    logo = serializers.ImageField(write_only=True, required=False)
    city = serializers.CharField(write_only=True, required=False)
    state = serializers.CharField(write_only=True, required=False)

    # Artist-only fields
    band_name = serializers.CharField(write_only=True, required=False)
    band_email = serializers.EmailField(write_only=True, required=False)

    class Meta:
        model = User
        fields = (
            'email', 'password', 'role',
            'full_name', 'phone_number', 'logo', 'city', 'state',
            'band_name', 'band_email', 'name'
        )
        extra_kwargs = {
            'role': {'required': True}
        }

    def validate(self, data):
        role = data.get('role')
        errors = {}

        common_fields = ['phone_number', 'city', 'state']
        if role in [ROLE_CHOICES.ARTIST, ROLE_CHOICES.VENUE]:
            for field in common_fields:
                if not data.get(field):
                    errors[field] = 'This field is required for this role'

        if role == ROLE_CHOICES.ARTIST:
            if not data.get('full_name'):
                errors['full_name'] = 'This field is required for this role'
            for field in ['band_name', 'band_email']:
                if not data.get(field):
                    errors[field] = 'This field is required for this role'

        elif role == ROLE_CHOICES.VENUE:
            if not data.get('name'):
                errors['name'] = 'This field is required for this role'

        elif role == ROLE_CHOICES.FAN:
            if not data.get('name'):
                errors['name'] = 'This field is required for this role'

        if errors:
            raise serializers.ValidationError(errors)

        return data

    def create(self, validated_data):
        role = validated_data.get('role')
        full_name = validated_data.pop('full_name', None)
        name = validated_data.pop('name', None)
        phone_number = validated_data.pop('phone_number', None)
        logo = validated_data.pop('logo', None)
        city = validated_data.pop('city', None)
        state = validated_data.pop('state', None)
        band_name = validated_data.pop('band_name', None)
        band_email = validated_data.pop('band_email', None)

        # Set User.name appropriately
        if role == ROLE_CHOICES.ARTIST and full_name:
            validated_data['name'] = full_name
        elif role in [ROLE_CHOICES.VENUE, ROLE_CHOICES.FAN] and name:
            validated_data['name'] = name

        user = User.objects.create_user(**validated_data)
        profile_data = {
            'phone_number': phone_number,
            'logo': logo,
            'city': city,
            'state': state
        }

        if role == ROLE_CHOICES.ARTIST:
            profile_data.update({
                'full_name': full_name,
                'band_name': band_name,
                'band_email': band_email
            })

        UserSettings.objects.create(user=user)

        otp = user.gen_otp()
        send_templated_email(
            'OTP Verification',
            [user.email],
            'otp_verification',
            {'otp': otp}
        )
        user.profile_data = profile_data
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'name',
            'email_verified',
            'role',
            'is_active',
            'created_at',
            'updated_at',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get('role') == ROLE_CHOICES.ARTIST and data.get('name') == "":
            data.pop('name')
        return data
