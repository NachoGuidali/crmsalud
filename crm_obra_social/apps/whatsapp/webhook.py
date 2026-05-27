import logging

from django.utils import timezone

logger = logging.getLogger('apps.whatsapp')

# Evolution API status → internal status
_STATUS_MAP = {
    'PENDING': 'pending',
    'SENT': 'sent',
    'DELIVERY_ACK': 'delivered',
    'READ': 'read',
    'PLAYED': 'read',
    'ERROR': 'failed',
    'FAILED': 'failed',
}


def verify_webhook_token(request_token: str, configured_token: str) -> bool:
    """
    Validate the webhook token sent by Evolution API in the 'apikey' header.
    If no token is configured, skip validation (dev mode).
    """
    if not configured_token:
        logger.warning('No webhook_token configured — skipping webhook token verification')
        return True
    return request_token == configured_token


def parse_incoming_webhook(payload: dict) -> list:
    """
    Parse Evolution API webhook payload and return list of message dicts.
    Each dict: from_phone, message_id, type, content, media_url, timestamp, contact_name.
    Returns [] for non-message events (e.g. connection.update).
    """
    event = payload.get('event', '')

    if event == 'messages.upsert':
        return _parse_message_upsert(payload)

    if event == 'messages.update':
        _process_status_updates(payload.get('data', []))
        return []

    return []


def _parse_message_upsert(payload: dict) -> list:
    messages_data = []
    try:
        data = payload.get('data', {})
        key = data.get('key', {})

        # Ignore messages sent by us
        if key.get('fromMe', False):
            return []

        remote_jid = key.get('remoteJid', '')
        # Ignore group messages
        if '@g.us' in remote_jid:
            return []

        from_phone = _extract_from_jid(remote_jid)
        message_id = key.get('id', '')
        msg_type_raw = data.get('messageType', 'conversation')
        message = data.get('message', {})
        timestamp_val = data.get('messageTimestamp', 0)

        msg_type = _normalize_type(msg_type_raw)
        content = _extract_content_evo(message, msg_type_raw)
        media_url = _extract_media_url_evo(message, msg_type_raw)
        contact_name = data.get('pushName', '')

        if isinstance(timestamp_val, (int, float)):
            ts = timezone.datetime.fromtimestamp(int(timestamp_val), tz=timezone.utc)
        else:
            ts = timezone.now()

        messages_data.append({
            'from_phone': from_phone,
            'message_id': message_id,
            'type': msg_type,
            'content': content,
            'media_url': media_url,
            'timestamp': ts,
            'contact_name': contact_name,
        })
    except Exception as e:
        logger.exception('Error parsing webhook upsert payload: %s', e)
    return messages_data


def _extract_from_jid(jid: str) -> str:
    """'5491112345678@s.whatsapp.net' → '+5491112345678'"""
    number = jid.split('@')[0]
    if not number.startswith('+'):
        number = '+' + number
    return number


def _normalize_type(msg_type_raw: str) -> str:
    """Map Evolution API messageType to internal Mensaje.tipo values."""
    type_map = {
        'conversation': 'text',
        'extendedTextMessage': 'text',
        'imageMessage': 'image',
        'documentMessage': 'document',
        'documentWithCaptionMessage': 'document',
        'audioMessage': 'audio',
        'videoMessage': 'video',
        'stickerMessage': 'image',
        'buttonsResponseMessage': 'text',
        'listResponseMessage': 'text',
        'templateButtonReplyMessage': 'text',
    }
    return type_map.get(msg_type_raw, 'text')


def _extract_content_evo(message: dict, msg_type_raw: str) -> str:
    if msg_type_raw in ('conversation', 'extendedTextMessage'):
        return (
            message.get('conversation', '')
            or message.get('extendedTextMessage', {}).get('text', '')
        )
    if msg_type_raw == 'imageMessage':
        return message.get('imageMessage', {}).get('caption', '')
    if msg_type_raw == 'videoMessage':
        return message.get('videoMessage', {}).get('caption', '') or '[Video]'
    if msg_type_raw == 'documentMessage':
        doc = message.get('documentMessage', {})
        return doc.get('title', '') or doc.get('caption', '') or '[Documento]'
    if msg_type_raw == 'documentWithCaptionMessage':
        inner = message.get('documentWithCaptionMessage', {}).get('message', {}).get('documentMessage', {})
        return inner.get('title', '') or inner.get('caption', '') or '[Documento]'
    if msg_type_raw == 'audioMessage':
        return '[Audio]'
    if msg_type_raw == 'stickerMessage':
        return '[Sticker]'
    if msg_type_raw == 'buttonsResponseMessage':
        return message.get('buttonsResponseMessage', {}).get('selectedDisplayText', '')
    if msg_type_raw == 'listResponseMessage':
        row = message.get('listResponseMessage', {}).get('singleSelectReply', {})
        return row.get('title', '') or row.get('selectedRowId', '')
    if msg_type_raw == 'templateButtonReplyMessage':
        return message.get('templateButtonReplyMessage', {}).get('selectedDisplayText', '')
    return f'[{msg_type_raw}]'


def _extract_media_url_evo(message: dict, msg_type_raw: str) -> str:
    """Extract direct media URL from Evolution API webhook (already included in payload)."""
    media_keys = {
        'imageMessage': 'imageMessage',
        'videoMessage': 'videoMessage',
        'documentMessage': 'documentMessage',
        'audioMessage': 'audioMessage',
        'stickerMessage': 'stickerMessage',
    }
    key = media_keys.get(msg_type_raw)
    if key:
        return message.get(key, {}).get('url', '')
    if msg_type_raw == 'documentWithCaptionMessage':
        inner = message.get('documentWithCaptionMessage', {}).get('message', {}).get('documentMessage', {})
        return inner.get('url', '')
    return ''


def _process_status_updates(update_list: list):
    """Update Mensaje status based on Evolution API messages.update events."""
    from .models import Mensaje
    for item in update_list:
        msg_id = item.get('key', {}).get('id', '')
        raw_status = item.get('update', {}).get('status', '')
        mapped = _STATUS_MAP.get(raw_status.upper() if raw_status else '', '')
        if msg_id and mapped:
            Mensaje.objects.filter(whatsapp_message_id=msg_id).update(status=mapped)
