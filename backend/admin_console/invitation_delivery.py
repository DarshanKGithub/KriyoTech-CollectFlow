import base64
import hashlib
import logging
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from kombu.exceptions import KombuError

from accounts.models import Invitation
from .models import InvitationDelivery

logger = logging.getLogger(__name__)


def _cipher():
    key = base64.urlsafe_b64encode(
        hashlib.sha256(("invitation-token:" + settings.SECRET_KEY).encode()).digest()
    )
    return Fernet(key)


def protect_token(token):
    return _cipher().encrypt(token.encode()).decode()


def reveal_token(encrypted_token):
    return _cipher().decrypt(encrypted_token.encode()).decode()


def queue_delivery(delivery_id):
    from .tasks import deliver_invitation

    def publish():
        try:
            deliver_invitation.delay(str(delivery_id))
        except KombuError:
            logger.warning("Invitation delivery %s remains queued because the task broker is unavailable.", delivery_id)

    transaction.on_commit(publish)


def create_invitation_delivery(invitation, token):
    delivery, _ = InvitationDelivery.objects.update_or_create(
        invitation=invitation,
        defaults={
            "status": InvitationDelivery.Status.PENDING,
            "encrypted_token": protect_token(token),
            "attempt_count": 0,
            "next_attempt_at": timezone.now(),
            "processing_token": None,
            "error_message": "",
        },
    )
    queue_delivery(delivery.pk)
    return delivery


def reissue_invitation(invitation):
    token = secrets.token_urlsafe(32)
    invitation.token_hash = hashlib.sha256(token.encode()).hexdigest()
    invitation.expires_at = timezone.now() + timedelta(days=7)
    invitation.save(update_fields=["token_hash", "expires_at"])
    return create_invitation_delivery(invitation, token)
