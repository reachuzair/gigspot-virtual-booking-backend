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
    proof_type = serializers.ChoiceField(
        choices=['DOCUMENT', 'URL'], read_only=False)
    proof_document = serializers.FileField(required=False, allow_null=True)
    proof_url = serializers.URLField(required=False, allow_null=True)

    class Meta:
        model = Venue
        fields = (
            'name',
            'phone_number',
            'logo',
            'city', 'state', 'address', 'capacity', 'amenities',
            'reservation_fee', 'artist_capacity', 'is_completed',
            'stripe_account_id', 'stripe_onboarding_completed',
            'profileImage', 'proof_type', 'proof_document', 'proof_url'

        )

    def validate(self, data):
        proof_type = data.get("proof_type")
        if proof_type == "DOCUMENT" and not data.get("proof_document"):
            raise serializers.ValidationError(
                "Document is required when proof_type is DOCUMENT.")
        if proof_type == "URL" and not data.get("proof_url"):
            raise serializers.ValidationError(
                "URL is required when proof_type is URL.")
        return data

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
    name = serializers.CharField(write_only=True, required=False)
    phone_number = serializers.CharField(write_only=True, required=False)
    logo = serializers.ImageField(write_only=True, required=False)
    city = serializers.CharField(write_only=True, required=False)
    state = serializers.CharField(write_only=True, required=False)

    # Artist-only fields
    band_name = serializers.CharField(write_only=True, required=False)
    band_email = serializers.EmailField(write_only=True, required=False)

    # Venue-only fields for proof
    proof_type = serializers.ChoiceField(
        choices=[("DOCUMENT", "Document"), ("URL", "URL")], write_only=True, required=False)
    proof_document = serializers.FileField(write_only=True, required=False)
    proof_url = serializers.URLField(write_only=True, required=False)

    class Meta:
        model = User
        fields = (
            'email', 'password', 'role',
            'full_name', 'phone_number', 'logo', 'city', 'state',
            'band_name', 'band_email', 'name',
            'proof_type', 'proof_document', 'proof_url'
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
            proof_type = data.get('proof_type')
            if proof_type == "DOCUMENT" and not data.get('proof_document'):
                errors['proof_document'] = 'This field is required when proof_type is DOCUMENT.'
            if proof_type == "URL" and not data.get('proof_url'):
                errors['proof_url'] = 'This field is required when proof_type is URL.'

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
        proof_type = validated_data.pop('proof_type', None)
        proof_document = validated_data.pop('proof_document', None)
        proof_url = validated_data.pop('proof_url', None)

        # Set User.name appropriately
        if role == ROLE_CHOICES.ARTIST and full_name:
            validated_data['name'] = full_name
        elif role in [ROLE_CHOICES.VENUE, ROLE_CHOICES.FAN] and name:
            validated_data['name'] = name

        user = User.objects.create_user(**validated_data)

        # Build profile_data for downstream usage in view
        profile_data = {
            'phone_number': phone_number,
            'logo': logo,
            'city': city,
            'state': state,
        }

        if role == ROLE_CHOICES.ARTIST:
            profile_data.update({
                'full_name': full_name,
                'band_name': band_name,
                'band_email': band_email
            })

        elif role == ROLE_CHOICES.VENUE:
            profile_data.update({
                'proof_type': proof_type,
                'proof_document': proof_document,
                'proof_url': proof_url
            })

        # Save additional user settings
        UserSettings.objects.create(user=user)

        # OTP flow
        otp = user.gen_otp()
        send_templated_email(
            'OTP Verification',
            [user.email],
            'otp_verification',
            {'otp': otp}
        )

        # Attach to user instance for view usage
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
