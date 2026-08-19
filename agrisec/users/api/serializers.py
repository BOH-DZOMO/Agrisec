from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username","email", "url"]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "pk"},
        }

class UserSignupSerializer(serializers.ModelSerializer):
    # Add an explicit password field with security built-in
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password] # Automatically uses Django's password rules
    )
    confirm_password = serializers.CharField(
        write_only=True, 
        required=True, 
    )
    def validate(self, attrs):
        if attrs.get('password') != attrs.get('confirm_password'):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs
    class Meta:
        model = User
        # Fields the user needs to provide or read back
        fields = ["email", "username", "password","confirm_password", "url"]
        
        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "pk"},
        }

    def create(self, validated_data):
        """
        Intercepts creation to ensure the password gets hashed properly.
        """
        # Create the user using Django's standard UserManager helper
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data.get('username', ''),
            password=validated_data['password'] # create_user automatically hashes this!
        )
        return user
    
class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    