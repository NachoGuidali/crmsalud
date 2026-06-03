# Evolution API — Configuración y Puesta en Marcha

Guía completa para conectar el CRM Supreg con Evolution API (WhatsApp vía QR, sin API oficial de Meta).

---

## ¿Qué es Evolution API?

Evolution API es un bridge open-source que conecta WhatsApp Web (protocolo Baileys) con una REST API.
Funciona escaneando un QR igual que WhatsApp Web, sin necesidad de cuenta Business de Meta, sin plantillas
aprobadas y sin la restricción de la ventana de 24h.

El CRM lo consume como un servicio Docker más en el mismo stack.

---

## 1. Variables de entorno (`.env`)

```env
# Evolution API (WhatsApp vía QR)
EVOLUTION_API_URL=http://evolution-api:8080
EVOLUTION_API_KEY=tu_api_key_segura           # inventalo, mínimo 16 chars alfanuméricos
EVOLUTION_INSTANCE_NAME=crm-supreg           # nombre lógico de la instancia
EVOLUTION_WEBHOOK_TOKEN=token_secreto_webhooks # para validar que los webhooks vienen de Evo
EVOLUTION_SERVER_URL=https://tu-dominio.com:8080  # URL pública de Evolution API (para el QR)
```

> **`EVOLUTION_SERVER_URL`** es la URL que Evolution API usa en su propia configuración.
> Dentro de Docker, `EVOLUTION_API_URL=http://evolution-api:8080` apunta al contenedor.
> Desde fuera del VPS, el puerto `8080` tiene que estar accesible para que el webhook llegue.

---

## 2. `docker-compose.yml` — servicio Evolution API

Ya incluido en el proyecto. El servicio usa PostgreSQL (base de datos `evolution_api`) y Redis:

```yaml
evolution-api:
  image: evoapicloud/evolution-api:latest
  restart: unless-stopped
  ports:
    - "8080:8080"
  environment:
    SERVER_URL: ${EVOLUTION_SERVER_URL:-http://localhost:8080}
    AUTHENTICATION_API_KEY: ${EVOLUTION_API_KEY}
    DATABASE_ENABLED: "true"
    DATABASE_PROVIDER: postgresql
    DATABASE_CONNECTION_URI: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/evolution_api
    CACHE_REDIS_ENABLED: "true"
    CACHE_REDIS_URI: redis://redis:6379/6
    CACHE_REDIS_PREFIX_KEY: evolution
  volumes:
    - evolution_instances:/evolution/instances
  depends_on:
    redis:
      condition: service_healthy
    db:
      condition: service_healthy
```

**Importante:** la base de datos `evolution_api` hay que crearla en PostgreSQL antes de levantar el servicio:
```bash
docker compose exec db psql -U ${POSTGRES_USER} -c "CREATE DATABASE evolution_api;"
```

---

## 3. Django settings (`config/settings/base.py`)

Las variables de entorno se leen así (fallback a valores por defecto):

```python
EVOLUTION_API_URL      = os.environ.get('EVOLUTION_API_URL', 'http://evolution-api:8080')
EVOLUTION_API_KEY      = os.environ.get('EVOLUTION_API_KEY', '')
EVOLUTION_INSTANCE_NAME = os.environ.get('EVOLUTION_INSTANCE_NAME', 'crm-supreg')
EVOLUTION_WEBHOOK_TOKEN = os.environ.get('EVOLUTION_WEBHOOK_TOKEN', '')
```

Los valores en DB (configurados desde `/whatsapp/configuracion/`) tienen **prioridad** sobre el `.env`.
Si el campo en DB está vacío, cae al `.env`.

---

## 4. Configuración desde el CRM

Ir a **WhatsApp → Configuración** (`/whatsapp/configuracion/`):

| Campo | Valor |
|---|---|
| Evolution API URL | `http://evolution-api:8080` (o la URL pública si está expuesta) |
| API Key | La misma que `EVOLUTION_API_KEY` en `.env` |
| Nombre de instancia | `crm-supreg` (o el que hayas elegido) |
| Token de webhook | La misma que `EVOLUTION_WEBHOOK_TOKEN` en `.env` |

Después de guardar, hacer clic en **"Configurar webhook"** para que Evolution API apunte al CRM.

---

## 5. Conectar WhatsApp (escanear QR)

1. Ir a **WhatsApp → Configuración**
2. Panel de estado muestra: `close` (desconectado) o `open` (conectado)
3. Si está `close`, aparece el QR — escanearlo con el teléfono (igual que WhatsApp Web)
4. El estado cambia a `open`
5. Desde ese momento los mensajes entrantes llegan al inbox del CRM

**Si el QR no aparece o expira:**
- Hacer clic en "Forzar nuevo QR" o "Reconectar"
- Si persiste, hacer clic en "Desconectar" y volver a conectar

---

## 6. Configuración del webhook

Evolution API debe enviar los webhooks al CRM. El endpoint es:

```
POST https://tu-dominio.com/whatsapp/webhook/
```

El header que envía Evolution API:
```
apikey: <EVOLUTION_WEBHOOK_TOKEN>
```

Eventos que el CRM procesa:
- `messages.upsert` — mensaje entrante (texto, imagen, audio, documento, etc.)
- `messages.update` — actualización de estado de envío (sent, delivered, read)
- `connection.update` — cambio de estado de la instancia (open/close)

El webhook se configura automáticamente al guardar la configuración. También se puede configurar manualmente
desde el panel de Evolution API o con este curl:

```bash
curl -X POST http://tu-servidor:8080/webhook/set/crm-supreg \
  -H "apikey: TU_EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "https://tu-dominio.com/whatsapp/webhook/",
      "webhook_by_events": false,
      "events": ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "CONNECTION_UPDATE"]
    }
  }'
```

---

## 7. Proxy (solo si el VPS tiene IP de datacenter bloqueada)

WhatsApp puede bloquear IPs de datacenter reconocidas (AWS, DigitalOcean, Hetzner, etc.).
Si el QR se escanea pero la conexión se cae en segundos, agregar proxy residencial en `.env`:

```env
PROXY_HOST=proxy.proveedor.com
PROXY_PORT=8080
PROXY_PROTOCOL=http
PROXY_USERNAME=usuario
PROXY_PASSWORD=password
```

Y configurarlo en el servicio Evolution API en `docker-compose.yml`:
```yaml
environment:
  PROXY_HOST: ${PROXY_HOST}
  PROXY_PORT: ${PROXY_PORT}
  PROXY_PROTOCOL: ${PROXY_PROTOCOL}
  PROXY_USERNAME: ${PROXY_USERNAME}
  PROXY_PASSWORD: ${PROXY_PASSWORD}
```

---

## 8. Estructura del payload webhook entrante

Para referencia al debugear o integrar con n8n:

```json
// Mensaje entrante (event: messages.upsert)
{
  "event": "messages.upsert",
  "instance": "crm-supreg",
  "data": {
    "key": {
      "remoteJid": "5491112345678@s.whatsapp.net",
      "fromMe": false,
      "id": "MSG_ID_UNICO"
    },
    "pushName": "Nombre del contacto",
    "messageType": "conversation",
    "message": {
      "conversation": "Texto del mensaje"
    },
    "messageTimestamp": 1234567890
  }
}

// Actualización de estado (event: messages.update)
{
  "event": "messages.update",
  "instance": "crm-supreg",
  "data": [
    {
      "key": { "id": "MSG_ID_UNICO" },
      "update": { "status": "DELIVERY_ACK" }
    }
  ]
}
```

**Tipos de mensajes soportados:**
| `messageType` | Descripción |
|---|---|
| `conversation` | Texto plano |
| `extendedTextMessage` | Texto con preview de URL |
| `imageMessage` | Imagen (con o sin caption) |
| `audioMessage` | Audio / nota de voz |
| `documentMessage` | Documento (PDF, etc.) |
| `videoMessage` | Video |
| `buttonsResponseMessage` | Respuesta a botón interactivo |
| `listResponseMessage` | Respuesta a lista interactiva |
| `stickerMessage` | Sticker |

---

## 9. API del CRM que consume Evolution API (`sender.py`)

El CRM se comunica con Evolution API vía estas funciones en `apps/whatsapp/sender.py`:

| Función | Endpoint Evo | Descripción |
|---|---|---|
| `send_text_message(to, body)` | `POST /message/sendText/{instance}` | Texto plano |
| `send_media_message(to, url, type, ...)` | `POST /message/sendMedia/{instance}` | Imagen/video/doc/audio |
| `send_interactive_message(to, body, buttons, ...)` | `POST /message/sendButtons/{instance}` | Hasta 3 botones |
| `get_connection_state()` | `GET /instance/connectionState/{instance}` | `open`/`close`/`connecting` |
| `get_qr_code(force=False)` | `GET /instance/connect/{instance}` | Base64 del QR |
| `logout_instance()` | `DELETE /instance/logout/{instance}` | Desconectar |
| `reset_instance()` | logout + restart | Reconexión limpia |
| `ensure_instance_exists()` | `GET /instance/fetchInstances` + `POST /instance/create` | Crear instancia si no existe |
| `setup_instance_webhook(url)` | `POST /webhook/set/{instance}` | Configurar webhook |

**Formato del teléfono:** la API de Evolution recibe el número **sin** el `+` inicial.
El CRM normaliza automáticamente: `'+5491112345678'` → `'5491112345678'`.

---

## 10. Pasos de deploy en el VPS

```bash
# 1. Actualizar código
cd /opt/crmsalud/crmsalud
git pull

# 2. Crear la base de datos de Evolution API (solo la primera vez)
docker compose exec db psql -U crm_user -c "CREATE DATABASE evolution_api;"

# 3. Levantar todo
docker compose up -d --build

# 4. Verificar que todos los servicios estén corriendo
docker compose ps

# 5. Ver logs de Evolution API
docker compose logs evolution-api --tail=50

# 6. Ver logs del CRM (Django)
docker compose logs web --tail=50
```

---

## 11. Diagnóstico rápido

| Síntoma | Causa probable | Solución |
|---|---|---|
| QR no aparece | Instancia no creada | Ir a Configuración → guardar → el CRM crea la instancia automáticamente |
| QR se escanea y se cae | IP de datacenter bloqueada | Configurar proxy residencial |
| Mensajes no llegan al inbox | Webhook mal configurado | Hacer clic en "Configurar webhook" en la página de Configuración |
| `403 Forbidden` en webhook | Token incorrecto | Verificar que `EVOLUTION_WEBHOOK_TOKEN` en `.env` coincida con lo configurado en el CRM |
| `evolution-api` no arranca | Base de datos `evolution_api` no existe | `docker compose exec db psql -U crm_user -c "CREATE DATABASE evolution_api;"` |
| Mensajes enviados no llegan al destinatario | Número mal formateado | Verificar que el teléfono en el Lead tenga el código de país (ej: `+54911...`) |
