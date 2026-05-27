from unittest.mock import patch, MagicMock
from django.test import TestCase

from .webhook import parse_incoming_webhook, _extract_content


SAMPLE_WEBHOOK = {
    "entry": [{
        "changes": [{
            "value": {
                "messages": [{
                    "from": "5491112345678",
                    "id": "wamid.abc123",
                    "type": "text",
                    "text": {"body": "Hola, quiero información"},
                    "timestamp": "1700000000",
                }],
                "contacts": [{
                    "wa_id": "5491112345678",
                    "profile": {"name": "Juan Pérez"},
                }],
            }
        }]
    }]
}


class WebhookParseTest(TestCase):
    def test_parses_text_message(self):
        messages = parse_incoming_webhook(SAMPLE_WEBHOOK)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['from_phone'], '5491112345678')
        self.assertEqual(messages[0]['content'], 'Hola, quiero información')
        self.assertEqual(messages[0]['type'], 'text')
        self.assertEqual(messages[0]['contact_name'], 'Juan Pérez')

    def test_extract_audio_content(self):
        msg = {'type': 'audio', 'audio': {'id': 'media_123'}}
        self.assertEqual(_extract_content(msg), '[Audio]')

    def test_empty_payload(self):
        messages = parse_incoming_webhook({})
        self.assertEqual(messages, [])


class SenderTest(TestCase):
    @patch('apps.whatsapp.sender.requests.post')
    def test_send_text_message(self, mock_post):
        from .sender import send_text_message
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'messages': [{'id': 'wamid.test123'}]}
        mock_post.return_value = mock_response

        result = send_text_message('+5491112345678', 'Hola!')
        self.assertEqual(result['messages'][0]['id'], 'wamid.test123')
        mock_post.assert_called_once()

    @patch('apps.whatsapp.sender.requests.post')
    def test_send_text_logs_on_error(self, mock_post):
        from requests.exceptions import RequestException
        from .sender import send_text_message
        mock_post.side_effect = RequestException('timeout')
        with self.assertRaises(RequestException):
            send_text_message('+5491112345678', 'test')
