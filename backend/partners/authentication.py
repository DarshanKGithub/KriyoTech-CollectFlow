"""Reject retired reseller sessions without changing existing KriyoPay logins."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenRefreshSerializer, TokenBlacklistSerializer


def check_binding(token):
    if token.get("partner_schema", "public") != "public" or token.get("product_instance"):
        raise AuthenticationFailed("This retired product session cannot access KriyoPay. Sign in again.")


class KriyoPayJWTAuthentication(JWTAuthentication):
    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        check_binding(token)
        return token


class KriyoPayTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        check_binding(self.token_class(attrs["refresh"]))
        return super().validate(attrs)


class KriyoPayTokenBlacklistSerializer(TokenBlacklistSerializer):
    def validate(self, attrs):
        check_binding(self.token_class(attrs["refresh"]))
        return super().validate(attrs)
