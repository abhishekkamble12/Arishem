"""
Serializers for auth endpoints.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import ALL_ROLES, Workspace

User = get_user_model()


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ["id", "name", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label="Confirm password")

    # Role is deliberately NOT accepted from the client: self-registered users get
    # settings.SIGNUP_ROLE (never admin). Promotion uses the admin-only role endpoint.
    class Meta:
        model  = User
        fields = ["id", "email", "username", "password", "password2"]
        extra_kwargs = {"username": {"required": False}}

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password2"):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        username = validated_data.get("username") or validated_data["email"].split("@")[0]

        user = User.objects.create_user(
            email    = validated_data["email"],
            username = username,
            password = validated_data["password"],
        )

        group, _ = Group.objects.get_or_create(name=settings.SIGNUP_ROLE)
        user.groups.set([group])

        # Create a default workspace for the user
        workspace = Workspace.objects.create(name=f"{username}'s Workspace")
        workspace.members.add(user)

        return user


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(read_only=True)
    workspaces = WorkspaceSerializer(many=True, read_only=True)

    class Meta:
        model  = User
        fields = ["id", "email", "username", "role", "workspaces", "date_joined", "is_active"]


class RoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ALL_ROLES)
