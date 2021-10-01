from rest_framework import serializers  # DRF's serializer base classes
from django.contrib.auth.password_validation import validate_password  # Django's built-in password rules
from .models import User  # our custom User model


class RegisterSerializer(serializers.ModelSerializer):  # handles user registration
    password = serializers.CharField(write_only=True, validators=[validate_password])  # write_only means password never appears in response JSON

    class Meta:
        model = User  # which model this serializer maps to
        fields = ['username', 'email', 'password', 'role', 'cohort']  # which fields to accept in request

    def create(self, validated_data):  # called when .save() is invoked
        return User.objects.create_user(**validated_data)  # create_user hashes the password automatically


class UserSerializer(serializers.ModelSerializer):  # read-only user profile data
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'cohort']  # never expose password here
