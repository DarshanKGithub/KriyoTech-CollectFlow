"""Native OAuth handoff: fixed redirect allowlist, PKCE, expiring encrypted codes.

Uses existing OAuth-state rows, so this bridge requires no schema migration.
"""
import base64
import hashlib
import json
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView


class NativeRedirect(HttpResponseRedirect):
    allowed_schemes = ['http', 'https', 'kriyopay', 'exp']


def allowed_return(value):
    if value in {'kriyopay://oauth', 'kriyopay://gmail'}:
        return True
    try:
        url = urlsplit(value)
        return bool(settings.DEBUG and url.scheme == 'exp' and url.hostname in settings.ALLOWED_HOSTS
                    and url.path in {'/--/oauth', '/--/gmail'} and url.port
                    and not url.username and not url.password and not url.query and not url.fragment)
    except (TypeError, ValueError):
        return False


def start_mobile_state(request):
    source = request.query_params if request.method == 'GET' else request.data
    target = source.get('return_uri')
    if not target:
        return secrets.token_urlsafe(36)
    challenge = source.get('code_challenge', '')
    if not isinstance(target, str) or not allowed_return(target) or not isinstance(challenge, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', challenge):
        raise ValidationError('A supported mobile return URI and S256 code challenge are required.')
    return signing.dumps({'return_uri': target, 'challenge': challenge, 'nonce': secrets.token_urlsafe(20)}, salt='kriyopay-native-oauth', compress=True)


def read_mobile_state(raw):
    try:
        data = signing.loads(raw, salt='kriyopay-native-oauth', max_age=600)
        return data if allowed_return(data.get('return_uri')) else None
    except (signing.BadSignature, TypeError, AttributeError):
        return None


def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('native-oauth:' + settings.SECRET_KEY).encode()).digest()))


def mobile_signin_redirect(state, *, error='', access='', refresh='', workspace=''):
    if not state:
        return None
    target = state['return_uri']
    if error:
        return NativeRedirect(target + '?' + urlencode({'google_error': error}))
    from accounts.models import User
    from tenants.models import Tenant
    from phase3.models import GoogleSignInState
    from rest_framework_simplejwt.tokens import AccessToken
    user = User.objects.get(pk=AccessToken(access)['user_id'])
    tenant = Tenant.objects.get(workspace_key=workspace)
    payload = {'access': access, 'refresh': refresh, 'workspace': workspace, 'user_id': str(user.pk),
               'credential': hashlib.sha256(user.password.encode()).hexdigest(), 'challenge': state['challenge']}
    code = cipher().encrypt(json.dumps(payload).encode()).decode()
    GoogleSignInState.objects.create(state_hash=hashlib.sha256(code.encode()).hexdigest(), tenant=tenant, expires_at=timezone.now()+timedelta(seconds=120))
    response = NativeRedirect(target + '?' + urlencode({'handoff': code}))
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


class MobileOAuthExchange(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'google_signin_callback'

    @transaction.atomic
    def post(self, request):
        from accounts.models import User, Membership
        from phase3.models import GoogleSignInState
        code = request.data.get('handoff', '')
        verifier = request.data.get('code_verifier', '')
        if not isinstance(code, str) or not 1 <= len(code) <= 10000 or not isinstance(verifier, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier):
            raise ValidationError('A complete mobile authorization handoff is required.')
        try:
            payload = json.loads(cipher().decrypt(code.encode(), ttl=120))
        except (InvalidToken, ValueError, UnicodeDecodeError):
            raise ValidationError('The mobile handoff expired. Sign in again.') from None
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        if not constant_time_compare(challenge, payload.get('challenge', '')):
            raise ValidationError('This handoff belongs to a different sign-in attempt.')
        state = GoogleSignInState.objects.select_for_update().filter(state_hash=hashlib.sha256(code.encode()).hexdigest(), used_at__isnull=True, expires_at__gt=timezone.now()).first()
        user = User.objects.filter(pk=payload.get('user_id'), is_active=True).first()
        if not state or not user or hashlib.sha256(user.password.encode()).hexdigest() != payload.get('credential') or not Membership.objects.filter(tenant=state.tenant, user=user, is_active=True).exists():
            raise ValidationError('The mobile handoff is invalid, used, or access has changed.')
        state.used_at = timezone.now(); state.save(update_fields=['used_at'])
        response = Response({key: payload[key] for key in ('access', 'refresh', 'workspace')})
        response['Cache-Control'] = 'no-store'
        return response
