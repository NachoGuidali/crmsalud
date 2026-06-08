# Integración n8n ↔ CRM Supreg — Guía completa del bot WhatsApp

## URLs

| Servicio | URL |
|---|---|
| CRM | https://crmsalud.supregsolutions.com |
| n8n | https://n8n.supregsolutions.com |
| Base API leads | https://crmsalud.supregsolutions.com/api/v1/ |
| Base API WhatsApp | https://crmsalud.supregsolutions.com/whatsapp/api/ |

---

## ⚠️ Autenticación — HAY DOS SISTEMAS DE CLAVE DISTINTOS

Esto es lo que más confunde y lo que probablemente esté rompiendo la integración: **no es una sola API key para todo**. Hay dos mecanismos completamente independientes:

### A) Clave UUID — para los endpoints de Leads (`/api/v1/leads/...`)

1. Ir a **https://crmsalud.supregsolutions.com/integraciones/**
2. Crear nueva clave → nombre: `n8n-bot`
3. Se genera un UUID, ej: `a1b2c3d4-e5f6-...`
4. Va en el header de los HTTP Request que apuntan a `/api/v1/leads/...`:

```
X-API-Key: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Internamente esto valida contra el modelo `ApiKey` (tabla en la base de datos, con `activa=True`).

### B) `CRM_API_KEY` — para enviar mensajes y hacer handoff (`/whatsapp/api/...`)

Los endpoints `POST /whatsapp/api/enviar/` y `POST /whatsapp/api/handoff/` **NO usan la clave UUID de arriba**. Usan una variable de entorno fija configurada en el servidor del CRM:

```
CRM_API_KEY=<valor-secreto-definido-en-el-.env-del-servidor>
```

Y se manda en el mismo header `X-Api-Key` (el nombre del header es igual, pero el valor es **distinto** al de la clave UUID):

```
X-Api-Key: <valor-de-CRM_API_KEY>
```

> **Pedile este valor a quien administra el servidor** (no se genera desde la UI de Integraciones — está en las variables de entorno / `.env` del deploy). Si todavía no está seteado, hay que agregarlo al `.env` y reiniciar.

**Comportamiento si `CRM_API_KEY` no está configurado:**
- `/whatsapp/api/enviar/` responde `403 — "API not enabled. Set CRM_API_KEY."`
- `/whatsapp/api/handoff/` **no exige ninguna clave** (queda abierto) — por eso es importante configurarlo en producción.

### Resumen

| Endpoint | Header | Clave |
|---|---|---|
| `GET /api/v1/leads/buscar/` | `X-API-Key` | UUID de `/integraciones/` |
| `POST /api/v1/leads/` | `X-API-Key` | UUID de `/integraciones/` |
| `POST /api/v1/leads/actualizar/` | `X-API-Key` | UUID de `/integraciones/` |
| `POST /whatsapp/api/enviar/` | `X-Api-Key` | valor de `CRM_API_KEY` (env var) |
| `POST /whatsapp/api/handoff/` | `X-Api-Key` | valor de `CRM_API_KEY` (env var) |

En n8n conviene crear **dos credenciales/variables separadas** (ej. `crm_leads_api_key` y `crm_api_key`) para no mezclarlas.

---

## Cómo llega un mensaje a n8n (Webhook)

El CRM reenvía cada evento del WhatsApp (Evolution API) a la URL de webhook de n8n configurada en la variable de entorno `N8N_WEBHOOK_URL` del servidor del CRM. **No hace falta configurar nada en la UI del CRM** — esa URL se define del lado del servidor.

**En n8n:** crear un *Webhook Trigger* (POST), copiar su URL de producción y pasársela a quien administra el CRM para que la cargue en `N8N_WEBHOOK_URL`.

### Estructura del payload que llega a n8n

El CRM reenvía el payload crudo de Evolution API **y le agrega 4 campos de conveniencia al final**:

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

  "phone": "+5491112345678",        // teléfono extraído del remoteJid, listo para usar
  "message": "Hola, quiero info",   // texto del mensaje ya extraído
  "contact_name": "Juan Pérez",     // pushName de WhatsApp
  "bot_n8n_activo": true            // ← SI ESTO ES FALSE, EL BOT NO DEBE RESPONDER
}
```

### ⚠️ Importante: el CRM reenvía TODOS los eventos, no solo mensajes

Evolution API manda varios tipos de evento (`messages.upsert`, `messages.update` con cambios de estado tipo "entregado"/"leído", `connection.update`, etc.) y el CRM **los reenvía todos tal cual los recibe**, sumándole los 4 campos de conveniencia.

Para los eventos que no son un mensaje nuevo, `message` llega vacío (`""`) y `phone` también puede llegar vacío. **El bot debe filtrar por esto** (ver el nodo Code más abajo) — si no, puede intentar procesar un evento de "mensaje leído" como si fuera un mensaje del usuario.

Filtros recomendados, en este orden:
1. `event !== 'messages.upsert'` → ignorar
2. `data.key.fromMe === true` → ignorar (mensaje enviado por el bot/agente mismo)
3. `message` vacío → ignorar (es un evento sin texto: foto sin caption, audio, sticker, etc., salvo que quieras manejar esos casos)

### ⚠️ Lo MÁS importante: chequear `bot_n8n_activo`

El **primer nodo después del Webhook Trigger** debe ser un **IF**:

```
Condición: {{ $json.bot_n8n_activo }} es igual a (boolean) true
  → TRUE:  continuar el flujo del bot
  → FALSE: no hacer nada (cortar el flujo, sin nodos conectados)
```

`bot_n8n_activo` se pone en `false` en estos casos:
- Cuando el bot llama a `/api/handoff/` (ver más abajo)
- Cuando un agente lo desactiva manualmente desde el inbox del CRM (botón de bot en la conversación)

Si n8n no chequea esto, **el bot va a seguir respondiendo aunque un agente humano ya esté atendiendo la conversación** — esto es probablemente lo que dejó de funcionar: antes el bot no necesitaba este check porque no existía el sistema de handoff/agentes; ahora si no lo agregás, vas a tener al bot y al agente respondiendo al mismo tiempo.

---

## Estados de la conversación (`Conversacion.estado`)

Cada conversación de WhatsApp tiene un estado que el CRM gestiona automáticamente:

| Estado | Significado |
|---|---|
| `pendiente` | Recién creada, o recién derivada por el bot — esperando que un agente la abra/atienda |
| `abierta` | Un agente la está atendiendo activamente (se marca así cuando el agente la abre en el inbox) |
| `cerrada` | El agente terminó la atención y la cerró manualmente |

**Transiciones automáticas relevantes para el bot:**

- Mensaje nuevo de un contacto sin conversación previa → se crea en `pendiente`, `bot_n8n_activo=True`
- Bot llama a `/api/handoff/` → pasa a `pendiente`, `bot_n8n_activo=False`, se asigna un agente automáticamente
- Agente abre la conversación → pasa a `abierta`
- Agente presiona "Cerrar conversación" → pasa a `cerrada`
- **Si el contacto vuelve a escribir a una conversación `cerrada`** → el CRM la **reabre automáticamente**: vuelve a `pendiente`, `bot_n8n_activo=True` (el bot vuelve a tomar el control desde cero) y se reasigna agente si no tenía

Esto último es clave: **no hace falta que el bot haga nada especial para "reiniciar"** — el CRM se encarga de poner `bot_n8n_activo` en `true` de nuevo y limpiar el estado. El bot simplemente va a recibir el próximo mensaje con `bot_n8n_activo: true`, y como el lead ya existe pero su `datos_extra.bot_step` puede seguir en `"completado"`, conviene que el flujo trate ese caso como un reinicio (ver Switch más abajo: agregar un caso para `completado` que vuelva a preguntar o salude de nuevo).

---

## Endpoints disponibles

### 1. Buscar lead — `GET /api/v1/leads/buscar/`

```
Método:  GET
URL:     https://crmsalud.supregsolutions.com/api/v1/leads/buscar/
Params:  telefono = {{ $json._phone }}
Headers: X-API-Key: <UUID de integraciones>
Options: ✅ Continue on Fail = true   ← el 404 (lead nuevo) es esperado, no debe cortar el flujo
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
  "estado_display": "Interesado",
  "prioridad": "media",
  "agente": "Pedro Gómez",
  "datos_extra": { "bot_step": "esperando_email" },
  "created_at": "2026-05-01T12:00:00Z",
  "updated_at": "2026-06-01T12:00:00Z"
}
```

**Respuesta si no existe (HTTP 404):**
```json
{ "found": false, "telefono": "+5491112345678" }
```

---

### 2. Crear lead — `POST /api/v1/leads/`

Usar en la rama cuando el lead no existe. Si el teléfono ya existe, **no duplica**: actualiza datos vacíos y devuelve `status: "updated"`.

```
Método:  POST
URL:     https://crmsalud.supregsolutions.com/api/v1/leads/
Headers: X-API-Key: <UUID de integraciones>
         Content-Type: application/json
Body:
{
  "nombre_completo": "{{ $('Code').item.json._name }}",
  "telefono":        "{{ $('Code').item.json._phone }}",
  "origen":          "whatsapp"
}
```

Respuesta: `{"status": "created"|"updated", "lead_id": 42, "telefono": "+549..."}`

---

### 3. Actualizar lead — `POST /api/v1/leads/actualizar/`

Busca por teléfono y actualiza solo los campos enviados. **Cualquier campo que no sea uno de los conocidos se guarda automáticamente en `datos_extra`** — así es como el bot guarda su "estado interno" (`bot_step`).

```
Método:  POST
URL:     https://crmsalud.supregsolutions.com/api/v1/leads/actualizar/
Headers: X-API-Key: <UUID de integraciones>
         Content-Type: application/json
```

```json
{
  "telefono": "{{ $('Code').item.json._phone }}",

  "nombre_completo": "Juan Pérez",
  "email":           "juan@example.com",
  "dni":             "35123456",
  "localidad":       "Buenos Aires",
  "provincia":       "Buenos Aires",
  "plan":            "Familiar",
  "notas":           "Tiene 3 hijos",
  "estado":          "interesado",
  "prioridad":       "alta",

  "datos_extra": { "bot_step": "esperando_email" },

  "cobertura_solicitada": "completa",
  "cantidad_hijos": "3"
}
```

Todos los campos son opcionales salvo `telefono`. Devuelve 404 `lead_not_found` si no existe — por eso siempre conviene crear el lead primero (paso 2) si `found: false`.

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

**Valores válidos para `prioridad`:** `alta` | `media` | `baja`

---

### 4. Enviar mensaje — `POST /whatsapp/api/enviar/`

⚠️ Usar **siempre** este endpoint para que el bot responda — **nunca** llamar a Evolution API directamente. Si el bot le habla a Evolution API "por afuera" del CRM, el mensaje no queda registrado en el historial de la conversación ni se actualiza `ultimo_mensaje_at`, y el agente no lo va a ver en el inbox.

```
Método:  POST
URL:     https://crmsalud.supregsolutions.com/whatsapp/api/enviar/
Headers: X-Api-Key: <valor de CRM_API_KEY>
         Content-Type: application/json
```

**Solo texto:**
```json
{
  "phone":   "{{ $('Code').item.json._phone }}",
  "message": "¡Hola! ¿Cuál es tu nombre completo?"
}
```

**Con imagen / archivo / audio / video:**
```json
{
  "phone":      "{{ $('Code').item.json._phone }}",
  "message":    "Texto del caption (opcional)",
  "media_url":  "https://url-publica-del-archivo.com/folleto.pdf",
  "media_type": "document"
}
```

`media_type`: `image` | `video` | `audio` | `document`. La `media_url` tiene que ser una URL pública accesible (el CRM la baja y la reenvía a Evolution API).

**Respuesta:**
```json
{
  "ok": true,
  "message_id": "3EB0...",
  "mensaje_id": 153,
  "conversacion_id": 12,
  "lead_id": 8
}
```

---

### 5. ⭐ Handoff al agente — `POST /whatsapp/api/handoff/`

**Llamar este endpoint cuando el bot termina su flujo y quiere derivar la conversación a un humano.**

Esto hace, todo de una sola vez:
- pone `bot_n8n_activo = false` (el bot deja de recibir mensajes de ese contacto)
- pone la conversación en estado `pendiente`
- asigna un agente automáticamente (el de menor carga de trabajo actual), salvo que mandes `agente_id`
- dispara la notificación al agente en el CRM (badge **LISTO** parpadeante + sonido + parpadeo de la pestaña del navegador)

```
Método:  POST
URL:     https://crmsalud.supregsolutions.com/whatsapp/api/handoff/
Headers: X-Api-Key: <valor de CRM_API_KEY>
         Content-Type: application/json
Body:
{
  "telefono": "{{ $('Code').item.json._phone }}"
}
```

Opcionalmente se puede forzar un agente puntual:
```json
{ "telefono": "+5491112345678", "agente_id": 3 }
```

**Respuesta:**
```json
{
  "ok": true,
  "conversacion_id": 15,
  "estado": "pendiente",
  "agente_id": 3
}
```

Si no encuentra una conversación con ese teléfono devuelve `404 {"error": "conversation_not_found"}`.

> **Después de llamar a `/api/handoff/`, el bot ya NO va a recibir más mensajes de ese contacto** (`bot_n8n_activo` queda en `false`, así que el IF del principio del flujo va a cortar todo). Si el contacto escribe de nuevo más tarde — incluso después de que el agente cierre la conversación — el CRM la reabre y vuelve a poner `bot_n8n_activo = true` automáticamente, así que el flujo arranca de cero sin que el bot tenga que hacer nada especial.

---

## Diagrama del flujo completo

```
[Webhook Trigger — evento entrante desde el CRM]
            │
[IF: event == 'messages.upsert'  AND  data.key.fromMe == false  AND  message no vacío]
      │ FALSE                                          │ TRUE
   [STOP]                                  [IF: bot_n8n_activo == true]
                                                 │ FALSE          │ TRUE
                                              [STOP]    [Code: extraer _phone, _text, _name]
                                                                  │
                                              [GET /api/v1/leads/buscar/?telefono=_phone]
                                                  (Continue on Fail = true)
                                                                  │
                                              [IF: $json.found == true]
                                                    │ FALSE                │ TRUE
                                          [POST /api/v1/leads/]            │
                                            crear lead                     │
                                                    └──────── Merge ───────┘
                                                                  │
                                          [Code: unificar lead_id + sacar bot_step]
                                                                  │
                                          [Switch por datos_extra.bot_step]
                       ┌───────────┬───────────────┬───────────────┬───────────────┬─────────────┐
                  '' / inicio  esperando_      esperando_       esperando_      completado /
                              nombre           email            plan            otro valor
                       │           │               │               │               │
              [Actualizar    [Validar nombre  [Validar email  [Normalizar    [tratar como
               bot_step:      → Actualizar     → Actualizar    plan          reinicio:
               esperando_     nombre +         email +         → Actualizar  volver a
               nombre]        bot_step:        bot_step:       plan + estado:  bot_step
                              esperando_       esperando_      interesado +    inicial y
                              email]           plan]           bot_step:       saludar de
                       │           │               │            completado]    nuevo]
              [Enviar:       [Enviar:        [Enviar:        [Enviar mensaje
               "¿Cuál es      "Gracias!       "¿Qué plan      de cierre]
               tu nombre?"]   ¿Tu email?"]    te interesa?"]        │
                                                              [POST /api/handoff/]
                                                                     │
                                                              (a partir de acá
                                                               bot_n8n_activo=false,
                                                               el bot ya no responde
                                                               más a este contacto)
```

> Nota: en cada rama de "validación" (nombre/email/plan), si el dato no es válido hay que **volver a preguntar** en vez de avanzar el `bot_step` — esa rama "inválido" no está dibujada arriba para no saturar el diagrama, pero está detallada nodo por nodo abajo.

---

## Configuración paso a paso de cada nodo

### Nodo: Webhook Trigger
Sin configuración especial más que el método `POST`. Copiar la URL de producción y pasarla para cargar en `N8N_WEBHOOK_URL`.

### Nodo: IF — filtrar evento válido
```
Condición 1: {{ $json.event }} es igual a "messages.upsert"
Condición 2: {{ $json.data.key.fromMe }} es igual a false
Condición 3: {{ $json.message }} no está vacío
Combinar con: AND
```

### Nodo: IF — bot activo
```
Condición: {{ $json.bot_n8n_activo }} es igual a (boolean) true
```

### Nodo: Code — extraer datos
```javascript
const phone = $json.phone;
const text  = ($json.message || '').trim();
const name  = $json.contact_name || '';

return [{ json: { _phone: phone, _text: text, _name: name } }];
```

### Nodo: Buscar lead
```
Método:  GET
URL:     https://crmsalud.supregsolutions.com/api/v1/leads/buscar/
Query params: telefono → {{ $json._phone }}
Headers: X-API-Key: <UUID de integraciones>
⚠️ Options → "Continue on Fail" = true
```

### Nodo: IF — lead existe
```
Condición: {{ $json.found }} es igual a true
```

### Nodo: Crear lead (rama FALSE)
```
Método: POST
URL:    https://crmsalud.supregsolutions.com/api/v1/leads/
Headers: X-API-Key: <UUID de integraciones>
Body (JSON):
{
  "nombre_completo": "{{ $('Code').item.json._name }}",
  "telefono":        "{{ $('Code').item.json._phone }}",
  "origen":          "whatsapp"
}
```

### Nodo: Merge
Modo **"Append"** (o "Choose Branch" / "Wait" según versión de n8n) — el objetivo es unificar las dos ramas (lead existente / lead recién creado) en un solo camino antes de seguir.

### Nodo: Code — unificar datos
```javascript
const code   = $('Code').item.json;
const buscar = $('Buscar Lead').item.json;
const crear  = $('Crear Lead')?.item?.json;

const lead = buscar.found ? buscar : crear;
const bot_step = lead?.datos_extra?.bot_step || '';

return [{
  json: {
    _phone:   code._phone,
    _text:    code._text,
    _name:    code._name,
    _lead_id: lead?.lead_id,
    _step:    bot_step,
  }
}];
```

### Nodo: Switch — bot_step
```
Valor:   {{ $json._step }}
Caso 1:  ''                 → rama "inicio"
Caso 2:  'esperando_nombre' → rama "tiene_nombre"
Caso 3:  'esperando_email'  → rama "tiene_email"
Caso 4:  'esperando_plan'   → rama "tiene_plan"
Default: (cualquier otro, incluido 'completado') → tratar como reinicio / saludo
```

---

### Rama "inicio" — preguntar nombre

**Actualizar:**
```json
{ "telefono": "{{ $json._phone }}", "datos_extra": { "bot_step": "esperando_nombre" } }
```
**Enviar:**
```json
{ "phone": "{{ $json._phone }}", "message": "¡Hola! 👋 Soy el asistente de Supreg.\n\n¿Cuál es tu nombre completo?" }
```

---

### Rama "esperando_nombre"

**Code — validar:**
```javascript
const text = $json._text;
const valido = text.length >= 3 && !/^\d+$/.test(text);
return [{ json: { ...$json, _valido: valido } }];
```

**IF `_valido == true`:**

- *TRUE* — Actualizar:
  ```json
  {
    "telefono":        "{{ $json._phone }}",
    "nombre_completo": "{{ $json._text }}",
    "datos_extra":     { "bot_step": "esperando_email" }
  }
  ```
  Enviar: `"Gracias, {{ $json._text }}! 😊\n\n¿Cuál es tu email?"`

- *FALSE* — Enviar: `"Por favor escribí tu nombre completo (ej: Juan Pérez)"` (sin avanzar `bot_step`, así vuelve a preguntar)

---

### Rama "esperando_email"

**Code — validar:**
```javascript
const text  = $json._text;
const valido = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text);
return [{ json: { ...$json, _valido: valido } }];
```

**IF `_valido == true`:**

- *TRUE* — Actualizar:
  ```json
  {
    "telefono":    "{{ $json._phone }}",
    "email":       "{{ $json._text }}",
    "datos_extra": { "bot_step": "esperando_plan" }
  }
  ```
  Enviar: `"Perfecto! ¿Qué plan te interesa?\n\n1️⃣ Individual\n2️⃣ Familiar\n3️⃣ Senior\n4️⃣ Empresa"`

- *FALSE* — Enviar: `"Eso no parece un email válido 🤔\nEscribilo así: nombre@ejemplo.com"`

---

### Rama "esperando_plan"

**Code — normalizar:**
```javascript
const text = $json._text.toLowerCase();
let plan = null;
if (text.includes('1') || text.includes('individual')) plan = 'Individual';
else if (text.includes('2') || text.includes('familiar')) plan = 'Familiar';
else if (text.includes('3') || text.includes('senior'))   plan = 'Senior';
else if (text.includes('4') || text.includes('empresa'))  plan = 'Empresa';

return [{ json: { ...$json, _plan: plan, _valido: plan !== null } }];
```

**IF `_valido == true`:**

- *TRUE*:
  1. Actualizar lead:
     ```json
     {
       "telefono":    "{{ $json._phone }}",
       "plan":        "{{ $json._plan }}",
       "estado":      "interesado",
       "prioridad":   "alta",
       "datos_extra": { "bot_step": "completado" }
     }
     ```
  2. Enviar mensaje de cierre:
     ```json
     { "phone": "{{ $json._phone }}", "message": "¡Perfecto! 🎉 Un asesor de Supreg te va a contactar en breve para darte más info sobre el plan *{{ $json._plan }}*. ¡Hasta pronto! 👋" }
     ```
  3. **Handoff:**
     ```json
     POST /whatsapp/api/handoff/
     { "telefono": "{{ $json._phone }}" }
     ```

- *FALSE* — Enviar: `"No entendí bien 😅 Respondé con el número o nombre del plan:\n\n1️⃣ Individual\n2️⃣ Familiar\n3️⃣ Senior\n4️⃣ Empresa"`

---

### Rama "completado" / reinicio (caso default del Switch)

Si el `bot_step` ya está en `completado` (o cualquier valor no contemplado), significa que el contacto vuelve a escribir después de haber pasado por todo el flujo (probablemente la conversación se cerró y se reabrió). Conviene resetear y arrancar de nuevo:

**Actualizar:**
```json
{ "telefono": "{{ $json._phone }}", "datos_extra": { "bot_step": "esperando_nombre" } }
```
**Enviar:** `"¡Hola de nuevo! 👋 ¿En qué puedo ayudarte esta vez? Para empezar, ¿cuál es tu nombre completo?"`

(O, si preferís, podés saltar directo a notificar a un agente con `/api/handoff/` en vez de repetir todo el cuestionario — depende de qué prefiera el equipo comercial.)

---

## Campos personalizados (`datos_extra`)

Si en el CRM hay *Campos personalizados* configurados (Leads → Campos personalizados), se guardan enviando el slug directamente en `/api/v1/leads/actualizar/` — el slug es el nombre en minúsculas sin espacios:

```json
{
  "telefono":             "+5491112345678",
  "grupo_familiar":       "4",
  "cobertura_solicitada": "alta",
  "empresa":              "Acme SA"
}
```

---

## Notas importantes / checklist de troubleshooting

| Tema | Detalle |
|---|---|
| **Dos API keys distintas** | UUID de `/integraciones/` para `/api/v1/leads/...`, valor de `CRM_API_KEY` (env var del servidor) para `/whatsapp/api/enviar/` y `/whatsapp/api/handoff/`. Si usás la incorrecta vas a recibir `401 unauthorized`. |
| **`CRM_API_KEY` sin configurar** | `/whatsapp/api/enviar/` responde `403`. `/whatsapp/api/handoff/` queda sin autenticación (riesgo de seguridad). Pedile a quien administra el servidor que lo setee en el `.env`. |
| **`bot_n8n_activo`** | Chequear SIEMPRE al inicio del flujo, antes de cualquier otra cosa. Si es `false`, no responder — es la causa más probable de que "antes andaba y ahora no". |
| **Eventos que no son mensajes** | El CRM reenvía TODOS los eventos de Evolution API (`messages.update`, `connection.update`, etc.), no solo mensajes nuevos. Filtrar por `event == 'messages.upsert'` y `message` no vacío. |
| **`fromMe`** | Filtrar `data.key.fromMe == true` para que el bot no se responda a sí mismo (o reaccione a mensajes enviados por el agente humano desde el CRM). |
| **Envío de mensajes** | Usar siempre `/whatsapp/api/enviar/`, nunca Evolution API directo — así quedan en el historial del inbox y el agente los ve. |
| **Handoff** | Llamar `/api/handoff/` al terminar el flujo del bot. Es lo único que dispara la notificación al agente (badge + sonido). NO alcanza con cambiar el `estado` del lead. |
| **Continue on Fail** | Activar en el nodo GET de búsqueda de lead — el 404 es esperado para contactos nuevos, no es un error real. |
| **Duplicados** | `POST /api/v1/leads/` nunca duplica: si el teléfono ya existe, actualiza y devuelve `status: "updated"`. |
| **Reapertura automática** | Si el contacto escribe después de que la conversación fue cerrada por un agente, el CRM la reabre solo y vuelve a poner `bot_n8n_activo = true`. El bot recibe el próximo mensaje normalmente — conviene tratar `bot_step: "completado"` como un reinicio (ver rama "completado" arriba). |
| **Formato de teléfono** | `+54911...` y `+5411...` son equivalentes — la API del CRM los reconoce como el mismo contacto. Usar siempre el `phone` que viene en el payload del webhook, no reformatearlo. |
| **`bot_n8n_activo` también se puede apagar manualmente** | Un agente puede desactivar el bot para una conversación puntual desde el inbox del CRM (sin pasar por handoff). En ese caso también deja de recibir mensajes — es un comportamiento esperado, no un bug. |
