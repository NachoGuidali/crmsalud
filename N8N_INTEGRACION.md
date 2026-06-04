# Integración n8n ↔ CRM Supreg — Guía del bot WhatsApp

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
3. La UUID generada va en el header de todos los HTTP Request de n8n:

```
X-API-Key: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## Paso 2 — Configurar el Webhook Trigger en n8n

El CRM reenvía cada mensaje de WhatsApp a la URL de webhook de n8n.

**En el CRM:** ir a *WhatsApp → Configuración* y poner la URL del webhook de n8n en el campo correspondiente.

**Estructura del payload que llega a n8n** (el CRM lo enriquece con campos extra):

```json
{
  "event": "messages.upsert",
  "instance": "crm-supreg",
  "data": {
    "key": {
      "remoteJid": "5491112345678@s.whatsapp.net",
      "fromMe": false,
      "id": "MSG_ID_UNICO"
    },
    "pushName": "Juan Pérez",
    "message": { "conversation": "Hola, quiero info" },
    "messageType": "conversation",
    "messageTimestamp": 1234567890
  },
  // ── Campos extras que agrega el CRM ──
  "phone": "+5491112345678",        // teléfono ya normalizado, listo para usar
  "message": "Hola, quiero info",   // texto del mensaje extraído
  "contact_name": "Juan Pérez",     // nombre de WhatsApp
  "bot_n8n_activo": true            // ← SI ESTO ES FALSE, EL BOT NO DEBE RESPONDER
}
```

### ⚠️ Lo más importante: chequear `bot_n8n_activo`

El primer nodo después del Webhook Trigger debe ser un **IF**:

```
Condición: {{ $json.bot_n8n_activo }} == true
  → TRUE:  continuar el flujo del bot
  → FALSE: no hacer nada (parar el flujo)
```

Cuando el bot hace handoff o un agente toma la conversación, el CRM pone `bot_n8n_activo = false`. Si n8n no chequea esto, va a seguir respondiendo aunque el agente ya esté atendiendo.

---

## Nodo Code — Extraer datos del webhook

Poner este nodo justo después del IF (rama TRUE):

```javascript
// Ignorar mensajes enviados por el bot mismo
if ($json.data?.key?.fromMe) return [];

// Los campos enriquecidos por el CRM ya vienen listos:
const phone    = $json.phone;        // "+5491112345678"
const text     = $json.message;      // "Hola, quiero info"
const pushName = $json.contact_name; // "Juan Pérez"

// Si el CRM no los mandó, extraer manualmente del payload original:
// const jid = $json.data?.key?.remoteJid || '';
// const phone = '+' + jid.replace(/@s\.whatsapp\.net$/, '').replace(/@c\.us$/, '');

return [{ json: { _phone: phone, _text: text, _pushName: pushName } }];
```

A partir de ahí usar `{{ $json._phone }}`, `{{ $json._text }}`, `{{ $json._pushName }}`.

---

## Endpoints disponibles

### 1. Buscar lead — `GET /api/v1/leads/buscar/`

```
Método:  GET
URL:     https://crmsalud.supregsolutions.com/api/v1/leads/buscar/
Params:  telefono = {{ $json._phone }}
Headers: X-API-Key: TU-API-KEY
Options: ✅ Continue on Fail = true  ← importante, el 404 no debe cortar el flujo
```

**Respuesta si existe (HTTP 200):**
```json
{
  "found": true,
  "lead_id": 42,
  "nombre_completo": "Juan Pérez",
  "telefono": "+5491112345678",
  "email": "juan@example.com",
  "dni": "35123456",
  "plan": "Familiar",
  "estado": "interesado",
  "datos_extra": {
    "bot_step": "esperando_email"
  }
}
```

**Respuesta si no existe (HTTP 404):**
```json
{ "found": false, "telefono": "+5491112345678" }
```

---

### 2. Crear lead — `POST /api/v1/leads/`

Usar en la rama cuando el lead no existe. Si el teléfono ya existe no crea duplicado, actualiza.

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

---

### 3. Actualizar lead — `POST /api/v1/leads/actualizar/`

Busca por teléfono y actualiza solo los campos que se envíen.
**Cualquier campo desconocido se guarda automáticamente en `datos_extra`.**

```
Método:  POST
URL:     https://crmsalud.supregsolutions.com/api/v1/leads/actualizar/
Headers: X-API-Key: TU-API-KEY
         Content-Type: application/json
```

```json
{
  "telefono": "{{ $('Code').item.json._phone }}",

  // Campos estándar (todos opcionales):
  "nombre_completo": "Juan Pérez",
  "email":           "juan@example.com",
  "dni":             "35123456",
  "localidad":       "Buenos Aires",
  "provincia":       "Buenos Aires",
  "plan":            "Familiar",
  "notas":           "Tiene 3 hijos",
  "estado":          "interesado",
  "prioridad":       "alta",

  // Para guardar el paso del bot (se usa como "estado interno" del bot):
  "datos_extra": { "bot_step": "esperando_email" },

  // También se pueden enviar campos extra directamente (van a datos_extra):
  "cobertura_solicitada": "completa",
  "cantidad_hijos": "3"
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

### 4. Enviar mensaje — `POST /whatsapp/api/enviar/` ← usar este, NO Evolution API directamente

Enviar siempre por el CRM para que el mensaje quede en el historial de la conversación.

```
Método:  POST
URL:     https://crmsalud.supregsolutions.com/whatsapp/api/enviar/
Headers: X-API-Key: TU-API-KEY
         Content-Type: application/json
Body:
{
  "phone":   "{{ $('Code').item.json._phone }}",
  "message": "¡Hola! ¿Cuál es tu nombre completo?"
}
```

Con imagen/archivo:
```json
{
  "phone":      "{{ $('Code').item.json._phone }}",
  "message":    "Texto del caption (opcional)",
  "media_url":  "https://url-publica-del-archivo.com/imagen.jpg",
  "media_type": "image"
}
```

`media_type`: `image` | `video` | `audio` | `document`

---

### 5. ⭐ Handoff al agente — `POST /whatsapp/api/handoff/`

**Llamar este endpoint cuando el bot termina y quiere derivar al agente humano.**

Esto hace: `bot_n8n_activo = false`, `estado_conversacion = pendiente`, asigna agente automáticamente, y le aparece una notificación al agente en el CRM.

```
Método:  POST
URL:     https://crmsalud.supregsolutions.com/whatsapp/api/handoff/
Headers: X-API-Key: TU-API-KEY
         Content-Type: application/json
Body:
{
  "telefono": "{{ $('Code').item.json._phone }}"
}
```

Respuesta:
```json
{
  "ok": true,
  "conversacion_id": 15,
  "estado": "pendiente",
  "agente_id": 3
}
```

Después del handoff, el agente ve la conversación con un badge **LISTO** parpadeante y recibe una notificación sonora.

> **Importante:** después de llamar `/api/handoff/`, el bot ya NO va a recibir más mensajes de ese contacto (el CRM setea `bot_n8n_activo = false`). Si el contacto escribe de nuevo más tarde (después de que el agente cierre la conversación), el flujo empieza de cero automáticamente.

---

## Diagrama del flujo completo

```
[Webhook Trigger — mensaje entrante desde CRM]
            ↓
[IF: bot_n8n_activo == true]
      ↓ FALSE                ↓ TRUE
   [STOP]              [Code: extraer _phone, _text, _pushName]
                                    ↓
                    [GET /api/v1/leads/buscar/?telefono=_phone]
                      (Continue on Fail = true)
                                    ↓
                    [IF: $json.found == true]
                          ↓               ↓ FALSE
                       (existe)      [POST /api/v1/leads/]
                          ↓          crear lead
                          └────────────┘
                                    ↓
                    [Switch por datos_extra.bot_step]
                     ↓          ↓          ↓          ↓
                  [vacío/   [esperando_ [esperando_ [esperando_
                   inicio]   nombre]    email]      plan]
                     ↓          ↓          ↓          ↓
              [Actualizar  [Actualizar [Actualizar [Actualizar
               bot_step:   nombre +    email +     plan +
               esperando_  bot_step:   bot_step:   estado:
               nombre]     esperando_  esperando_  interesado]
                           email]      plan]           ↓
                     ↓          ↓          ↓   [POST /api/handoff/]
              [Enviar msg] [Enviar msg] [Enviar msg]  ↓
              "¿Cuál es   "¿Tu email?" "¿Qué plan  [Enviar msg]
               tu nombre?"             te interesa?" "Un asesor
                                                     te contacta"
```

---

## Configuración paso a paso de cada nodo

### Nodo: Buscar lead
```
Método:  GET
URL:     https://crmsalud.supregsolutions.com/api/v1/leads/buscar/
Query params: telefono → {{ $json._phone }}
Headers: X-API-Key: TU-API-KEY
⚠️ Options → "Continue on Fail" = true
```

### Nodo: IF lead existe
```
Condición: {{ $('Buscar Lead').item.json.found }} == true
```

### Nodo: Crear lead (rama FALSE)
```
Método: POST
URL:    https://crmsalud.supregsolutions.com/api/v1/leads/
Body (JSON):
{
  "nombre_completo": "{{ $('Code').item.json._pushName }}",
  "telefono":        "{{ $('Code').item.json._phone }}",
  "origen":          "whatsapp"
}
```

### Switch: bot_step
```
Valor: {{ $('Buscar Lead').item.json.datos_extra?.bot_step ?? '' }}
Casos: '' (vacío/inicio) | 'esperando_nombre' | 'esperando_email' | 'esperando_plan'
Default → caso vacío (por si llega un valor inesperado)
```

### Rama "inicio" — preguntar nombre
```json
// Actualizar:
{ "telefono": "...", "datos_extra": { "bot_step": "esperando_nombre" } }
// Enviar: "¡Hola! Soy el asistente de Supreg. ¿Cuál es tu nombre completo?"
```

### Rama "esperando_nombre" — guardar nombre, preguntar email
```json
{
  "telefono":        "{{ $('Code').item.json._phone }}",
  "nombre_completo": "{{ $('Code').item.json._text }}",
  "datos_extra":     { "bot_step": "esperando_email" }
}
// Enviar: "Gracias {{ nombre }}! ¿Cuál es tu email?"
```

### Rama "esperando_email" — guardar email, preguntar plan
```json
{
  "telefono":    "{{ $('Code').item.json._phone }}",
  "email":       "{{ $('Code').item.json._text }}",
  "datos_extra": { "bot_step": "esperando_plan" }
}
// Enviar: "¿Qué plan te interesa? Individual, Familiar, Senior o Empresa"
```

### Rama "esperando_plan" — guardar plan + handoff
```json
// 1. Actualizar lead:
{
  "telefono":    "{{ $('Code').item.json._phone }}",
  "plan":        "{{ $('Code').item.json._text }}",
  "estado":      "interesado",
  "prioridad":   "alta",
  "datos_extra": { "bot_step": "completado" }
}
// 2. Enviar mensaje:
// "Perfecto! Un asesor te va a contactar en breve 👍"

// 3. Handoff al agente:
POST /whatsapp/api/handoff/
{ "telefono": "{{ $('Code').item.json._phone }}" }
```

---

## Campos personalizados (datos_extra)

Si en el CRM hay campos personalizados (se ven en *Leads → Campos personalizados*), se guardan enviando el slug directamente. El slug es el nombre en minúsculas sin espacios:

```json
{
  "telefono":            "+5491112345678",
  "grupo_familiar":      "4",
  "cobertura_solicitada":"alta",
  "empresa":             "Acme SA"
}
```

---

## Notas importantes

| Tema | Detalle |
|---|---|
| **`bot_n8n_activo`** | Siempre chequear al inicio del flujo. Si es `false`, no responder. |
| **Handoff** | Usar `/api/handoff/` al terminar el bot. NO usar Evolution API directamente para desactivar el bot. |
| **Envío de mensajes** | Usar `/whatsapp/api/enviar/` del CRM, no Evolution API directo. Así los mensajes quedan en el historial. |
| **Continue on Fail** | Activar en el nodo GET de búsqueda. El 404 es esperado para contactos nuevos. |
| **fromMe** | Filtrar `data.key.fromMe == true` para que el bot no se responda a sí mismo. |
| **Duplicados** | Si POST de creación recibe teléfono existente, actualiza — nunca duplica. |
| **Reapertura** | Si el contacto vuelve a escribir después de que el agente cerró la conversación, el flujo empieza de cero automáticamente (bot_step vuelve a vacío). |
| **Teléfono** | `+54911...` y `54911...` son equivalentes, la API normaliza. |
