"""
Serializers for auth endpoints.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import ALL_ROLES, ROLE_ADMIN, Membership, Workspace, unique_username

User = get_user_model()


class WorkspaceSerializer(serializers.ModelSerializer):
    """Workspace plus the requesting user's role in it (pass context={"user": user})."""
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "created_at", "role"]

    def get_role(self, obj):
        user = self.context.get("user")
        return user.role_in(obj.id) if user else None


class MemberSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="user_id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "email", "role", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label="Confirm password")

    # Role is deliberately NOT accepted from the client. A new user becomes admin of
    # the workspace they own; access to anyone else's workspace comes only from that
    # workspace's admin adding them.
    class Meta:
        model  = User
        fields = ["id", "email", "username", "password", "password2"]
        extra_kwargs = {"username": {"required": False}}

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password2"):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        # Derived usernames collide across domains (a@one.com, a@two.com), which
        # used to surface as a 500 from the unique constraint.
        username = validated_data.get("username") or unique_username(validated_data["email"])

        user = User.objects.create_user(
            email    = validated_data["email"],
            username = username,
            password = validated_data["password"],
        )

        workspace = Workspace.objects.create(name=f"{username}'s Workspace")
        workspace.add_member(user, ROLE_ADMIN)

        return user


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(read_only=True)
    workspaces = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ["id", "email", "username", "role", "workspaces", "date_joined", "is_active"]

    def get_workspaces(self, obj):
        return WorkspaceSerializer(obj.workspaces.order_by("id"), many=True, context={"user": obj}).data


class WorkspaceCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)


class MemberAddSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=ALL_ROLES, default="viewer")


class RoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ALL_ROLES)
