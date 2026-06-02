# Integración n8n ↔ CRM Supreg — Guía para el flujo de bot WhatsApp

## URLs

| Servicio | URL |
|---|---|
| CRM | https://crmsalud.supregsolutions.com |
| n8n | https://n8n.supregsolutions.com |
| API base | https://crmsalud.supregsolutions.com/api/v1/ |

---

## Paso 1 — Obtener la API Key

1. Ir a **https://crmsalud.supregsolutions.com/integraciones/**
2. Crear nueva clave → nombre: `n8n-bot`
3. Configurar: agente por defecto, origen `whatsapp`, estado inicial `nuevo`
4. Guardar la UUID generada — va en el header de todos los HTTP Request de n8n:

```
X-API-Key: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## Endpoints disponibles

### POST `/api/v1/leads/` — Crear o actualizar lead

Si el teléfono ya existe, actualiza campos vacíos. Si no existe, lo crea.

```json
{
  "nombre_completo": "Juan Pérez",     // requerido
  "telefono": "+541123456789",         // requerido
  "origen": "whatsapp",
  "email": "juan@example.com",
  "dni": "35123456",
  "localidad": "Buenos Aires",
  "provincia": "Buenos Aires",
  "plan": "Individual",
  "notas": "...",
  "datos_extra": { "clave": "valor" }
}
```

Respuesta:
```json
{ "status": "created", "lead_id": 42, "telefono": "+541123456789" }
// o
{ "status": "updated", "lead_id": 42, "telefono": "+541123456789" }
```

---

### GET `/api/v1/leads/buscar/?telefono=+541123456789` — Buscar lead por teléfono

Devuelve todos los datos del lead incluyendo `datos_extra` (donde se guarda el estado del bot).

```json
// Si existe (HTTP 200):
{
  "found": true,
  "lead_id": 42,
  "nombre_completo": "Juan Pérez",
  "telefono": "+541123456789",
  "email": "juan@example.com",
  "dni": "35123456",
  "localidad": "Buenos Aires",
  "provincia": "Buenos Aires",
  "plan": "Individual",
  "estado": "interesado",
  "estado_display": "Interesado",
  "prioridad": "alta",
  "agente": "María González",
  "datos_extra": {
    "bot_step": "esperando_email"
  },
  "created_at": "2026-06-02T10:30:00-03:00",
  "updated_at": "2026-06-02T14:22:00-03:00"
}

// Si no existe (HTTP 404):
{ "found": false, "telefono": "+541123456789" }
```

---

### POST `/api/v1/leads/actualizar/` — Actualizar campos de un lead existente

Busca por teléfono y actualiza solo los campos que se envíen.
Cualquier campo desconocido se guarda en `datos_extra` automáticamente.

```json
{
  "telefono": "+541123456789",          // requerido — para identificar al lead

  // Campos estándar (todos opcionales):
  "nombre_completo": "Juan Pérez",
  "email": "juan@example.com",
  "dni": "35123456",
  "localidad": "Buenos Aires",
  "provincia": "Buenos Aires",
  "notas": "Tiene 2 hijos",
  "plan": "Familiar",
  "estado": "interesado",               // ver valores válidos abajo
  "prioridad": "alta",                  // alta | media | baja

  // Campos extra (se mezclan con datos_extra):
  "datos_extra": { "bot_step": "esperando_plan" },

  // O directamente como campo suelto (también va a datos_extra):
  "cobertura_solicitada": "completa",
  "cantidad_hijos": "2"
}
```

Respuesta:
```json
{
  "status": "updated",
  "lead_id": 42,
  "telefono": "+541123456789",
  "campos_actualizados": ["email", "datos_extra"]
}
```

**Valores válidos para `estado`:**

| Valor | Display |
|---|---|
| `nuevo` | Nuevo |
| `contactado` | Contactado |
| `interesado` | Interesado |
| `doc_pendiente` | Documentación pendiente |
| `en_revision` | En revisión |
| `afiliado` | Afiliado |
| `perdido` | Perdido / No interesado |

---

## Cómo extraer el teléfono del webhook de Evolution API

El webhook de Evolution API llega con este formato:

```json
{
  "event": "messages.upsert",
  "instance": "crm-supreg",
  "data": {
    "key": {
      "remoteJid": "5491112345678@s.whatsapp.net",
      "fromMe": false,
      "id": "MSG_ID"
    },
    "pushName": "Juan Pérez",
    "message": {
      "conversation": "texto del mensaje"
    },
    "messageType": "conversation",
    "messageTimestamp": 1234567890
  }
}
```

**Nodo Code en n8n para extraer los datos:**

```javascript
const data = $json.data;

// Ignorar mensajes enviados por el bot
if (data.key.fromMe) return [];

// Extraer y limpiar el teléfono
const jid = data.key.remoteJid || '';
const phone = '+' + jid
  .replace(/@s\.whatsapp\.net$/, '')
  .replace(/@c\.us$/, '');

// Extraer texto (maneja distintos tipos de mensaje)
const msg = data.message || {};
const text = (
  msg.conversation ||
  msg.extendedTextMessage?.text ||
  msg.buttonsResponseMessage?.selectedDisplayText ||
  msg.listResponseMessage?.singleSelectReply?.selectedRowId ||
  ''
).trim();

const pushName = data.pushName || '';

return [{ json: { _phone: phone, _text: text, _pushName: pushName } }];
```

A partir de ahí usar `{{ $json._phone }}`, `{{ $json._text }}`, `{{ $json._pushName }}` en todos los nodos.

---

## Diagrama del flujo completo

```
[Webhook Trigger — Evolution API]
            ↓
[Code: extraer _phone, _text, _pushName]
            ↓
[HTTP GET /api/v1/leads/buscar/?telefono={{ _phone }}]
  ⚠️ "Continue on Fail" = true
            ↓
[IF: {{ $json.found }} == true]
      ↓ TRUE                ↓ FALSE
  (ya existe)           [HTTP POST /api/v1/leads/]
                          crear lead con pushName
      ↓                       ↓
             [Merge]
                ↓
  [Switch por {{ $('Buscar Lead').item.json.datos_extra.bot_step }}]
        ↓           ↓           ↓           ↓
   [vacío/       [espe-      [espe-      [espe-
    inicio]      rando_      rando_      rando_
                 nombre]     email]      plan]
        ↓           ↓           ↓           ↓
  [actualizar   [actualizar [actualizar [actualizar
   bot_step]    nombre +    email +     plan +
                bot_step]   bot_step]   estado +
                                        bot_step]
        ↓           ↓           ↓           ↓
  [Enviar msg] [Enviar msg] [Enviar msg] [Enviar msg]
  "¿Cuál es   "Gracias!    "¿Qué plan  "Perfecto,
  tu nombre?" ¿Tu email?"  te interesa?" un asesor
                                         te contacta"
```

---

## Configuración de cada nodo HTTP Request

### Buscar lead (GET)

```
Método:  GET
URL:     https://crmsalud.supregsolutions.com/api/v1/leads/buscar/
Params:  telefono = {{ $json._phone }}
Headers: X-API-Key: TU-API-KEY
Options: Continue on Fail = true
```

### Crear lead (POST) — rama FALSE del IF

```
Método:  POST
URL:     https://crmsalud.supregsolutions.com/api/v1/leads/
Headers: X-API-Key: TU-API-KEY
         Content-Type: application/json
Body:
{
  "nombre_completo": "{{ $('Code').item.json._pushName }}",
  "telefono":        "{{ $('Code').item.json._phone }}",
  "origen":          "whatsapp"
}
```

### Actualizar lead — rama inicio

```json
{
  "telefono":    "{{ $('Code').item.json._phone }}",
  "datos_extra": { "bot_step": "esperando_nombre" }
}
```
Mensaje: `"¡Hola! Soy el asistente de Supreg. ¿Cuál es tu nombre completo?"`

### Actualizar lead — rama esperando_nombre

```json
{
  "telefono":        "{{ $('Code').item.json._phone }}",
  "nombre_completo": "{{ $('Code').item.json._text }}",
  "datos_extra":     { "bot_step": "esperando_email" }
}
```
Mensaje: `"Gracias! ¿Cuál es tu email?"`

### Actualizar lead — rama esperando_email

```json
{
  "telefono":    "{{ $('Code').item.json._phone }}",
  "email":       "{{ $('Code').item.json._text }}",
  "datos_extra": { "bot_step": "esperando_plan" }
}
```
Mensaje: `"¿Qué plan te interesa? Individual, Familiar, Senior o Empresa"`

### Actualizar lead — rama esperando_plan

```json
{
  "telefono":    "{{ $('Code').item.json._phone }}",
  "plan":        "{{ $('Code').item.json._text }}",
  "estado":      "interesado",
  "prioridad":   "alta",
  "datos_extra": { "bot_step": "completado" }
}
```
Mensaje: `"Perfecto, un asesor se va a comunicar con vos en breve 👍"`

---

## Enviar mensajes por Evolution API desde n8n

```
Método:  POST
URL:     http://evolution-api:8080/message/sendText/crm-supreg
         (o la URL pública: https://crmsalud.supregsolutions.com:8080/message/sendText/crm-supreg)
Headers: apikey: TU-EVOLUTION-API-KEY
         Content-Type: application/json
Body:
{
  "number": "{{ $('Code').item.json._phone }}",
  "text":   "Tu mensaje acá"
}
```

---

## Guardar campos personalizados

Si en el CRM hay campos personalizados (se ven en `/leads/campos/`), se guardan enviando el slug del campo directamente:

```json
POST /api/v1/leads/actualizar/
{
  "telefono":            "+541123456789",
  "grupo_familiar":      "4",
  "cobertura_solicitada":"alta",
  "empresa":             "Acme SA"
}
```

El slug de cada campo se ve en el CRM: **Leads → Campos personalizados**. Es el nombre en minúsculas y sin espacios (ej: "Cobertura solicitada" → `cobertura_solicitada`).

---

## Notas importantes

- **Continue on Fail = true** en el nodo GET de búsqueda — el 404 es esperado para contactos nuevos y no debe cortar el flujo.
- **Ignorar mensajes propios**: el Code node filtra `fromMe = true` para que el bot no se responda a sí mismo.
- **Lead existente sin bot_step**: si el número ya tenía un lead creado manualmente (sin pasar por el bot), `bot_step` va a estar vacío → cae en la rama "inicio" y arranca el flujo desde el principio.
- **El teléfono es la clave**: todos los endpoints buscan y actualizan por teléfono. El formato `+54911...` y `54911...` son equivalentes, la API normaliza automáticamente.
- **No duplica leads**: si el POST de creación recibe un teléfono que ya existe, simplemente actualiza — nunca crea duplicados.
