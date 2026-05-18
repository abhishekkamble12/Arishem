"""
Serializers for auth endpoints.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import ALL_ROLES, ROLE_VIEWER

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label="Confirm password")
    role      = serializers.ChoiceField(choices=ALL_ROLES, default=ROLE_VIEWER, write_only=True)

    class Meta:
        model  = User
        fields = ["id", "email", "username", "password", "password2", "role"]
        extra_kwargs = {"username": {"required": False}}

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password2"):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        role     = validated_data.pop("role", ROLE_VIEWER)
        username = validated_data.get("username") or validated_data["email"].split("@")[0]

        user = User.objects.create_user(
            email    = validated_data["email"],
            username = username,
            password = validated_data["password"],
        )

        # Assign role via Django Group
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.set([group])

        return user


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="role", read_only=True)

    class Meta:
        model  = User
        fields = ["id", "email", "username", "role", "date_joined", "is_active"]
