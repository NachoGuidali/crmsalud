import json
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger('apps.whatsapp')


def _cfg(key):
    """Read an Evolution API credential from DB config (falls back to settings/env)."""
    from .models import ConfiguracionWhatsApp
    return ConfiguracionWhatsApp.get_setting(key)


def _evo_headers():
    return {
        'apikey': _cfg('evolution_api_key'),
        'Content-Type': 'application/json',
    }


def _evo_url(path: str) -> str:
    base = _cfg('evolution_api_url') or getattr(settings, 'EVOLUTION_API_URL', 'http://evolution-api:8080')
    return f'{base.rstrip("/")}{path}'


def _instance() -> str:
    return _cfg('evolution_instance_name') or getattr(settings, 'EVOLUTION_INSTANCE_NAME', 'crm-supreg')


def _normalize_phone(phone: str) -> str:
    """'+5491112345678' → '5491112345678' (Evolution API format)."""
    return phone.lstrip('+')


def _log_request(endpoint, method, request_body, response, duracion_ms):
    from .models import LogAPIWhatsApp
    try:
        LogAPIWhatsApp.objects.create(
            endpoint=endpoint,
            method=method,
            request_body=json.dumps(request_body) if isinstance(request_body, dict) else str(request_body),
            response_status=response.status_code if response else None,
            response_body=response.text[:5000] if response else '',
            duracion_ms=duracion_ms,
            exitoso=response is not None and response.status_code < 300,
        )
    except Exception:
        pass


def _extract_message_id(data: dict) -> str:
    """Extract message ID from Evolution API response."""
    return data.get('key', {}).get('id', '')


def send_text_message(to: str, body: str) -> dict:
    """Send a plain text message via Evolution API."""
    url = _evo_url(f'/message/sendText/{_instance()}')
    payload = {
        'number': _normalize_phone(to),
        'text': body,
    }
    start = time.monotonic()
    response = None
    try:
        response = requests.post(url, json=payload, headers=_evo_headers(), timeout=15)
        response.raise_for_status()
        data = response.json()
        msg_id = _extract_message_id(data)
        logger.info('Text message sent to %s (id=%s)', to, msg_id)
        return {'id': msg_id}
    except requests.RequestException as e:
        logger.error('Error sending text to %s: %s', to, e)
        raise
    finally:
        _log_request(url, 'POST', payload, response, int((time.monotonic() - start) * 1000))


def send_media_message(to: str, media_url: str, mediatype: str, filename: str = '', caption: str = '') -> dict:
    """Send a media message via public URL."""
    url = _evo_url(f'/message/sendMedia/{_instance()}')
    payload = {
        'number': _normalize_phone(to),
        'mediatype': mediatype,
        'media': media_url,
    }
    if caption:
        payload['caption'] = caption
    if filename:
        payload['fileName'] = filename
    start = time.monotonic()
    response = None
    try:
        response = requests.post(url, json=payload, headers=_evo_headers(), timeout=30)
        response.raise_for_status()
        data = response.json()
        msg_id = _extract_message_id(data)
        logger.info('Media (%s) sent to %s (id=%s)', mediatype, to, msg_id)
        return {'id': msg_id}
    except requests.RequestException as e:
        logger.error('Error sending media to %s: %s', to, e)
        raise
    finally:
        _log_request(url, 'POST', payload, response, int((time.monotonic() - start) * 1000))


def send_media_base64(to: str, base64_data: str, mediatype: str, mimetype: str,
                      filename: str = '', caption: str = '') -> dict:
    """Send a media message from base64-encoded content (no public URL needed)."""
    url = _evo_url(f'/message/sendMedia/{_instance()}')
    payload = {
        'number': _normalize_phone(to),
        'mediatype': mediatype,
        'media': base64_data,
        'mimetype': mimetype,
        'fileName': filename or f'archivo.{mediatype}',
    }
    if caption:
        payload['caption'] = caption
    start = time.monotonic()
    response = None
    # Don't log full base64 payload (too large) — use truncated version
    log_payload = {**payload, 'media': f'<base64 {len(base64_data)} chars>'}
    try:
        response = requests.post(url, json=payload, headers=_evo_headers(), timeout=60)
        response.raise_for_status()
        data = response.json()
        msg_id = _extract_message_id(data)
        logger.info('Media base64 (%s) sent to %s (id=%s)', mediatype, to, msg_id)
        return {'id': msg_id}
    except requests.RequestException as e:
        logger.error('Error sending media base64 to %s: %s', to, e)
        raise
    finally:
        _log_request(url, 'POST', log_payload, response, int((time.monotonic() - start) * 1000))


def send_interactive_message(to: str, body_text: str, buttons: list, header_text: str = '', footer_text: str = '') -> dict:
    """
    Send an interactive button message via Evolution API (max 3 buttons).
    buttons: [{"id": "btn_1", "title": "Texto botón"}]
    """
    url = _evo_url(f'/message/sendButtons/{_instance()}')
    evo_buttons = [
        {'type': 'reply', 'displayText': btn['title'][:20], 'id': btn['id']}
        for btn in buttons[:3]
    ]
    payload = {
        'number': _normalize_phone(to),
        'title': header_text or '',
        'description': body_text,
        'footer': footer_text or '',
        'buttons': evo_buttons,
    }
    start = time.monotonic()
    response = None
    try:
        response = requests.post(url, json=payload, headers=_evo_headers(), timeout=15)
        response.raise_for_status()
        data = response.json()
        msg_id = _extract_message_id(data)
        logger.info('Interactive message sent to %s (id=%s)', to, msg_id)
        return {'id': msg_id}
    except requests.RequestException as e:
        logger.error('Error sending interactive to %s: %s', to, e)
        raise
    finally:
        _log_request(url, 'POST', payload, response, int((time.monotonic() - start) * 1000))


def reset_instance():
    """Force a clean reconnection by logging out and restarting the instance."""
    import time
    instance = _instance()
    # Step 1: logout (clears saved session from DB)
    try:
        requests.delete(_evo_url(f'/instance/logout/{instance}'), headers=_evo_headers(), timeout=10)
        logger.info('Instance logged out for reset')
    except Exception:
        pass
    time.sleep(1)
    # Step 2: restart (reloads instance in clean state, will show QR since session was cleared)
    try:
        requests.post(_evo_url(f'/instance/restart/{instance}'), headers=_evo_headers(), timeout=10)
        logger.info('Instance restarted for reset')
    except Exception:
        pass
    time.sleep(2)


def logout_instance():
    """Logout (disconnect) the Evolution API WhatsApp instance. Falls back to restart if already closed."""
    instance = _instance()
    try:
        response = requests.delete(_evo_url(f'/instance/logout/{instance}'), headers=_evo_headers(), timeout=10)
        if response.ok:
            logger.info('Instance logged out')
            return
    except Exception:
        pass
    # Fallback: restart the instance so it enters close state and can show a new QR
    try:
        requests.post(_evo_url(f'/instance/restart/{instance}'), headers=_evo_headers(), timeout=10)
        logger.info('Instance restarted (fallback from logout)')
    except Exception as e:
        logger.error('Error restarting instance: %s', e)
        raise


def get_connection_state() -> str:
    """
    Check Evolution API instance connection state.
    Returns: 'open' | 'close' | 'connecting' | 'error'
    """
    url = _evo_url(f'/instance/connectionState/{_instance()}')
    try:
        response = requests.get(url, headers=_evo_headers(), timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('instance', {}).get('state', 'close')
    except Exception as e:
        logger.error('Error checking connection state: %s', e)
        return 'error'


def get_qr_code(force: bool = False) -> str | None:
    """
    Get QR code for scanning (base64 PNG string).
    Returns None if instance is already connected (unless force=True).
    """
    state = get_connection_state()
    if state == 'open' and not force:
        return None

    url = _evo_url(f'/instance/connect/{_instance()}')
    try:
        response = requests.get(url, headers=_evo_headers(), timeout=15)
        response.raise_for_status()
        data = response.json()
        logger.info('QR response keys: %s', list(data.keys()))
        qr = (data.get('base64') or
              data.get('qrcode', {}).get('base64') or
              data.get('code') or
              data.get('qr') or '')
        return qr or None
    except Exception as e:
        logger.error('Error getting QR code: %s', e)
        return None


def setup_instance_webhook(webhook_url: str) -> bool:
    """Configure the webhook URL on the Evolution API instance."""
    url = _evo_url(f'/webhook/set/{_instance()}')
    payload = {
        'webhook': {
            'enabled': True,
            'url': webhook_url,
            'webhook_by_events': False,
            'webhook_base64': False,
            'events': ['MESSAGES_UPSERT', 'MESSAGES_UPDATE', 'CONNECTION_UPDATE'],
        }
    }
    try:
        response = requests.post(url, json=payload, headers=_evo_headers(), timeout=10)
        response.raise_for_status()
        logger.info('Webhook configured: %s', webhook_url)
        return True
    except Exception as e:
        logger.error('Error configuring webhook: %s', e)
        return False


def ensure_instance_exists():
    """
    Create the Evolution API instance if it doesn't exist yet.
    Safe to call multiple times — does nothing if instance already exists.
    """
    instance = _instance()

    # Check if instance already exists
    try:
        url = _evo_url(f'/instance/fetchInstances')
        response = requests.get(url, headers=_evo_headers(), timeout=10)
        if response.ok:
            instances = response.json()
            if isinstance(instances, list):
                existing = [
                    i.get('instance', {}).get('instanceName', '') or i.get('instanceName', '')
                    for i in instances
                ]
            else:
                existing = []
            if instance in existing:
                return
    except Exception:
        pass

    create_url = _evo_url('/instance/create')
    payload = {
        'instanceName': instance,
        'integration': 'WHATSAPP-BAILEYS',
    }
    try:
        response = requests.post(create_url, json=payload, headers=_evo_headers(), timeout=15)
        if response.status_code == 403:
            # Instance already exists
            return
        response.raise_for_status()
        logger.info('Evolution API instance "%s" created', instance)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 403:
            return
        logger.error('Error creating Evolution API instance: %s', e)
    except Exception as e:
        logger.error('Error creating Evolution API instance: %s', e)
