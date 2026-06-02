# CRM Supreg — Obra Social

Sistema CRM completo para agentes comerciales de obras sociales argentinas. Gestiona el ciclo de vida completo del prospecto: captación, seguimiento, cotización, afiliación y comunicación por WhatsApp (vía **Evolution API**, protocolo QR — sin API oficial de Meta).

---

## Índice

- [Stack tecnológico](#stack-tecnológico)
- [Servicios Docker](#servicios-docker)
- [Instalación y puesta en marcha](#instalación-y-puesta-en-marcha)
- [Variables de entorno](#variables-de-entorno)
- [WhatsApp — Evolution API (QR)](#whatsapp--evolution-api-qr)
- [Roles y permisos](#roles-y-permisos)
- [Módulos del sistema](#módulos-del-sistema)
  - [Leads](#leads)
  - [Clientes](#clientes)
  - [Contactos](#contactos)
  - [Negociaciones (Deals)](#negociaciones-deals)
  - [Agenda / Tareas](#agenda--tareas)
  - [Cotizaciones](#cotizaciones)
  - [WhatsApp Inbox](#whatsapp-inbox)
  - [Plantillas de Mensaje](#plantillas-de-mensaje)
  - [Bot WhatsApp](#bot-whatsapp)
  - [Chatbot Visual](#chatbot-visual)
  - [Campañas masivas](#campañas-masivas)
  - [Automatizaciones](#automatizaciones)
  - [Integraciones API](#integraciones-api)
  - [Campos personalizados](#campos-personalizados)
  - [Reportes](#reportes)
  - [Usuarios](#usuarios)
- [Filtros dinámicos (Leads y Clientes)](#filtros-dinámicos-leads-y-clientes)
- [Importación masiva de leads](#importación-masiva-de-leads)
- [Importación / Exportación de Deals](#importación--exportación-de-deals)
- [Tareas asíncronas (Celery)](#tareas-asíncronas-celery)
- [Comandos útiles](#comandos-útiles)
- [Estructura del proyecto](#estructura-del-proyecto)
- [URLs principales](#urls-principales)
- [Trabajo pendiente / en curso](#trabajo-pendiente--en-curso)

---

## Stack tecnológico

| Componente | Tecnología |
|---|---|
| Framework | Django 5.1.4 |
| Base de datos | PostgreSQL 15 |
| Cache / Broker | Redis 7 |
| Cola de tareas | Celery 5.4 + Django Celery Beat |
| Servidor WSGI | Gunicorn 22 |
| Archivos estáticos | WhiteNoise |
| PDF | WeasyPrint 62 |
| Excel | OpenPyXL 3.1 |
| Imágenes | Pillow 10 |
| Frontend | Bootstrap 5.3.3 + Bootstrap Icons 1.11 |
| Editor de flujos | Drawflow (CDN) |
| WhatsApp bridge | Evolution API v2 (self-hosted, QR code) |

---

## Servicios Docker

```
web             → Django + Gunicorn (puerto 8002 en host → 8000 interno)
db              → PostgreSQL 15 (puerto 5434 en host → 5432 interno)
redis           → Redis 7 (128 MB LRU)
celery          → Worker (concurrencia 2)
celery-beat     → Scheduler de tareas periódicas
evolution-api   → WhatsApp bridge via QR (puerto 8080)
```

El servicio `evolution-api` usa la misma base de datos PostgreSQL del CRM pero en una base separada (`evolution_api`). Persiste instancias en un volumen Docker (`evolution_instances`).

---

## Instalación y puesta en marcha

```bash
git clone <repo>
cd crmsupreg
cp .env.example .env          # completar variables (ver sección siguiente)
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py collectstatic --noinput
# Opcional: cargar planes de ejemplo
docker compose exec web python manage.py loaddata apps/leads/fixtures/planes_iniciales.json
```

Acceder en: `http://localhost:8002`  
Django Admin: `http://localhost:8002/admin`

---

## Variables de entorno

Copiar `.env.example` como `.env` y completar:

```env
# Django
DJANGO_SECRET_KEY=tu-secret-key-larga-y-segura
DJANGO_DEBUG=False

# PostgreSQL
POSTGRES_DB=crm_obra_social
POSTGRES_USER=crm_user
POSTGRES_PASSWORD=password_seguro
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis / Celery
REDIS_URL=redis://redis:6379/0

# Evolution API (WhatsApp via QR — sin API oficial de Meta)
EVOLUTION_API_URL=http://evolution-api:8080
EVOLUTION_API_KEY=tu_api_key_segura
EVOLUTION_INSTANCE_NAME=crm-supreg
EVOLUTION_WEBHOOK_TOKEN=token_secreto_para_validar_webhooks
EVOLUTION_SERVER_URL=http://localhost:8080   # URL pública para QR callback

# Proxy residencial (opcional — si el VPS tiene IP de datacenter bloqueada por WA)
PROXY_HOST=
PROXY_PORT=
PROXY_PROTOCOL=http
PROXY_USERNAME=
PROXY_PASSWORD=

ALLOWED_HOSTS=localhost 127.0.0.1 your-domain.com
```

> **IMPORTANTE:** Ya NO hay variables de Meta Cloud API (`WHATSAPP_ACCESS_TOKEN`, etc.). El sistema usa exclusivamente Evolution API.

---

## WhatsApp — Evolution API (QR)

El CRM **no usa la API oficial de Meta**. Usa [Evolution API v2](https://evolution-api.com/) como bridge, que opera con el protocolo de WhatsApp Web (QR code), igual que WAZZUP.

### Ventajas sobre Meta Cloud API
- Sin cuentas Business de Meta
- Sin plantillas HSM aprobadas (texto libre siempre)
- Sin ventana de 24h (texto libre en cualquier momento)
- Sin límite de 1000 conversaciones/día en tier gratuito

### Configuración inicial
1. Ir a `/whatsapp/configuracion/`
2. Ingresar: Evolution API URL, API Key, nombre de instancia, token de webhook
3. El panel QR aparece automáticamente — escanear con el teléfono
4. Una vez conectado, el estado cambia a "Conectado"

### Webhook
Evolution API envía webhooks al CRM en: `https://tu-dominio.com/whatsapp/webhook/`

Formato de eventos:
```json
// Mensaje entrante:
{"event": "messages.upsert", "instance": "crm-supreg",
 "data": {"key": {"remoteJid": "5491112345678@s.whatsapp.net", "fromMe": false, "id": "..."},
          "pushName": "Nombre", "message": {"conversation": "texto"},
          "messageType": "conversation", "messageTimestamp": 1234567890}}

// Actualización de estado:
{"event": "messages.update", "instance": "crm-supreg",
 "data": [{"key": {"id": "MSG_ID"}, "update": {"status": "DELIVERY_ACK"}}]}
```

Tipos de mensaje soportados: `conversation`, `imageMessage`, `documentMessage`, `audioMessage`, `videoMessage`, `buttonsResponseMessage`, `listResponseMessage`, `stickerMessage`.

### Funciones disponibles en sender.py
| Función | Descripción |
|---|---|
| `send_text_message(to, body)` | Texto plano |
| `send_media_message(to, media_url, mediatype, filename, caption)` | Imagen/doc/video por URL |
| `send_interactive_message(to, body_text, buttons, header_text, footer_text)` | Botones interactivos |
| `get_connection_state()` | Estado: `open` / `close` / `connecting` |
| `get_qr_code()` | Base64 PNG del QR o None si ya conectado |

---

## Roles y permisos

El permiso clave es `user.can_see_all_leads` (True para Supervisores y Superadmins).

| Funcionalidad | Agente | Supervisor | Superadmin |
|---|:---:|:---:|:---:|
| Ver sus propios leads/clientes | ✅ | ✅ | ✅ |
| Ver todos los leads/clientes | ❌ | ✅ | ✅ |
| Asignación masiva de agentes | ❌ | ✅ | ✅ |
| Importar / exportar leads | ❌ | ✅ | ✅ |
| Convertir lead a cliente | ❌ | ✅ | ✅ |
| Importar clientes | ❌ | ✅ | ✅ |
| Campañas masivas | ❌ | ✅ | ✅ |
| Automatizaciones | ❌ | ✅ | ✅ |
| Plantillas de mensaje | ❌ | ✅ | ✅ |
| Chatbot visual | ❌ | ✅ | ✅ |
| Integraciones API | ❌ | ✅ | ✅ |
| Gestión de usuarios | ❌ | ✅ | ✅ |
| Campos personalizados | ❌ | ✅ | ✅ |
| Configurar WhatsApp API | ❌ | ✅ | ✅ |

---

## Módulos del sistema

### Leads

Pipeline principal de ventas. Un lead es un prospecto no convertido a cliente.

**Estados:**
```
Nuevo → Contactado → Interesado → Doc. Pendiente → En Revisión → Afiliado
                                                              ↘ Perdido
```

**Campos principales:** nombre completo, DNI (7-8 dígitos), fecha de nacimiento, teléfono (formato `+54...`), email, localidad, provincia, plan de interés (FK a Plan), grupo familiar, origen, prioridad (Alta/Media/Baja), agente asignado, motivo de pérdida, datos_extra (JSONField).

**Funcionalidades:**
- Filtro dinámico multi-campo (ver [Filtros dinámicos](#filtros-dinámicos-leads-y-clientes))
- Exportación a CSV
- Importación masiva CSV/Excel
- Asignación masiva con checkboxes (supervisor+)
- Conversión a cliente (supervisor+)
- Documentos adjuntos por tipo (recibo, DNI, contrato, otro)
- Historial de cambios de estado con nota y usuario
- Vista Kanban con drag & drop

---

### Clientes

Leads convertidos / afiliados. Comparten el modelo base pero con campos extra:
- Número de afiliado, plan contratado (FK), fecha de alta
- `datos_extra` JSONField igual que leads

**Funcionalidades:**
- Filtro dinámico multi-campo (igual que leads)
- Importación masiva CSV/Excel (supervisor+)
- Edición de campos personalizados en detalle
- Tareas relacionadas
- WhatsApp directo desde el listado

---

### Contactos

Vista unificada leads + clientes en una sola tabla. URL: `/leads/contactos/`

---

### Negociaciones (Deals)

Módulo de gestión de oportunidades/negocios con múltiples pipelines.

**Modelos:**
- `Pipeline`: nombre, descripción, activo
- `PipelineStage`: pertenece a un Pipeline, tiene nombre, orden, color (Bootstrap)
- `Deal`: título, pipeline, etapa, valor, lead/cliente asociado, agente, descripción, fecha de cierre estimada
- `DealHistory`: historial de cambios de etapa

**Vistas:**
- **Kanban** (`/negociaciones/`): tablero drag & drop por etapa, con buscador (q + agente), filtro de pipeline
- **Lista** (`/negociaciones/lista/`): tabla con filtros, paginación
- **Import** (`/negociaciones/importar/`): CSV con columnas: titulo, pipeline, etapa, valor, contacto, agente, descripcion, fecha_cierre_estimada
- **Export** (`/negociaciones/exportar/`): CSV descarga, respeta filtros activos (pipeline, q, agente)
- CRUD completo (crear, ver, editar, eliminar)
- Gestión de pipelines y etapas (`/negociaciones/pipelines/`)
- Mover deal de etapa vía AJAX (`/negociaciones/<pk>/mover/`)

---

### Agenda / Tareas

**Tipos:** Llamada, WhatsApp, Reunión, Documentación, Seguimiento  
**Estados:** Pendiente / Completada / Vencida

- Vista de agenda semanal
- Badge en navbar con tareas pendientes del día
- Registro de resultado al completar
- Celery marca vencidas automáticamente cada 15 min

---

### Cotizaciones

- Vinculadas a un lead
- Integrantes familiares (nombre, DNI, fecha nacimiento, parentesco)
- PDF generado con WeasyPrint (guardado en `media/cotizaciones/pdf/`)
- Envío directo por WhatsApp al lead

---

### WhatsApp Inbox

Bandeja estilo WhatsApp Web (panel dual: lista de conversaciones + chat).

- Polling: mensajes cada 4s, inbox cada 8s
- Texto libre **siempre disponible** (sin restricción de ventana 24h — Evolution API)
- Mensajes con botones interactivos
- Historial completo con estados: pendiente / enviado / entregado / leído / fallido
- Filtro por estado de conversación y no leídos
- Inicio de conversación desde leads, contactos y clientes

> **Nota:** El campo `ventana_activa` y `ventana_expira_at` fueron eliminados del modelo `Conversacion` en la migración a Evolution API.

---

### Plantillas de Mensaje

Mensajes pre-configurados con variables. Ya **no requieren aprobación de Meta**.

**Campos:**
- nombre, cuerpo con `{{1}}`, `{{2}}`..., variables (lista JSON de nombres)
- header (none/text/image/document/video), footer, botones (reply/url/phone)
- activa (bool) — no hay campo `status` de aprobación Meta

**Uso:** campañas masivas, automatizaciones, bot, envío manual desde inbox.  
**Preview:** método `plantilla.preview(valores=[...])` reemplaza variables.

---

### Bot WhatsApp

Reglas de auto-respuesta configurables.

**Triggers:** primer mensaje (bienvenida), palabra clave (case-insensitive, coincidencia parcial)  
**Respuestas:** texto libre, plantilla, botones interactivos  
**Acciones opcionales:** cambiar estado/prioridad del lead, solo sin agente, solo una vez por conversación

---

### Chatbot Visual

Editor visual con Drawflow. Flujos JSON guardados en BD. Nodos: inicio, mensaje, pregunta, botones, lista, condición, actualizar atributo, asignar etiqueta/agente/equipo, suscribir/desuscribir campaña.

---

### Campañas masivas

Envío masivo usando plantillas. Asíncrono via Celery, ~800 msg/min.

**Destinatarios:** por filtro (plan, provincia, estado, días sin contacto, tipo lead/cliente) o selección manual.  
**Variables:** se mapean a campos del contacto (`nombre_completo`, `email`, `plan`, `localidad`, `provincia`, `telefono`, campos personalizados).

---

### Automatizaciones

Reglas que se ejecutan cada hora.

**Triggers (tiempo):** N días desde creación, N días sin actividad, N días sin respuesta de WA.  
**Condiciones:** estado, prioridad, origen del lead.  
**Acciones:** cambiar estado, cambiar prioridad, enviar plantilla por WA (como texto via `preview()`), crear tarea.

---

### Integraciones API

API REST para recibir leads de sistemas externos.

```
POST /api/v1/leads/            → Crear lead (auth: header "Authorization: Api-Key <key>")
GET  /api/v1/leads/<id>/       → Consultar estado
POST /api/v1/webhook/<source>/ → Webhook genérico
```

Gestión de API Keys con log completo (IP, request/response, duración).

---

### Campos personalizados

Modelo `CampoPersonalizado` (en `apps/leads/`).

**Tipos:** texto, numero, fecha, booleano, lista  
**Alcance:** solo leads, solo clientes, ambos  
**Almacenamiento:** valores en `datos_extra` JSONField (texto/numero/fecha como string, booleano como bool)  
**Soporte de reglas condicionales:** `CampoRegla` — campo visible/oculto/obligatorio/solo_lectura según estado del lead

Los campos personalizados aparecen en:
- Detalle de lead/cliente (sección editable)
- Filtros dinámicos (ver abajo)
- Mapeo de variables en campañas
- Importación masiva (columnas extra)
- Automatizaciones (descripción de tarea)

---

### Reportes

- **Dashboard** (`/`): conteo por estado, tareas del día, conversaciones no leídas, actividad reciente, ranking agentes, leads esta semana
- **Conversión** (`/reportes/conversion/`): funnel completo, por origen, por agente
- **Mensajes** (`/reportes/mensajes/`): enviados/recibidos por rango de fechas
- **Exportar CSV** (`/reportes/exportar/`)

---

### Usuarios

**Roles:** Superadmin / Supervisor / Agente  
**Campos:** nombre, apellido, email (login), rol, teléfono interno, avatar, activo/inactivo

---

## Filtros dinámicos (Leads y Clientes)

Implementación en `utils/dynamic_filter.py`. Reemplaza los filtros fijos anteriores.

### Patrón URL
```
?q=texto&fc=campo1&fo=op1&fv=val1&fc=campo2&fo=op2&fv=val2
```
- `q`: búsqueda de texto libre (nombre, DNI, teléfono, email)
- `fc[]`: nombre del campo
- `fo[]`: operador
- `fv[]`: valor (siempre presente, incluso vacío `""` para operadores sin valor como `today`)

### Tipos de campo soportados
| Tipo | Operadores disponibles |
|---|---|
| `text` | contiene, no contiene, es igual a, empieza con |
| `choices` | es |
| `fk` | es (match por `_id`) |
| `number` | igual a, ≥, ≤, >, < |
| `date` | hoy, ayer, esta semana, este mes, últimos 7/30 días, en fecha exacta, desde, hasta |
| `extra_text` | igual que `text` (busca en `datos_extra__slug`) |
| `extra_num` | igual que `number` (usa `Cast + KeyTextTransform`) |
| `extra_fecha` | en fecha exacta, desde, hasta (comparación lexicográfica de ISO strings) |
| `extra_bool` | es (true/false) |
| `extra_lista` | es (match exacto) |

### Campos disponibles en Leads
nombre, DNI, teléfono, email, localidad, provincia, estado, prioridad, origen, plan (FK), grupo familiar, agente (FK, supervisor+), fecha de creación, última actualización + todos los `CampoPersonalizado` activos con alcance `leads` o `ambos`.

### Campos disponibles en Clientes
nombre, DNI, teléfono, email, localidad, provincia, plan (FK), N° afiliado, grupo familiar, agente (FK, supervisor+), fecha de creación, última actualización + todos los `CampoPersonalizado` activos con alcance `clientes` o `ambos`.

### Bug histórico corregido
El filtro de fechas tipo `hoy/ayer/esta semana/etc.` no funcionaba porque el JS no emitía ningún input `fv` para esos operadores. El `zip()` del backend cortaba en la lista más corta → el filtro se ignoraba.

**Fix aplicado:**
1. JS (`filter_builder.html`): cuando el operador no requiere valor, se emite un `<input type="hidden" name="fv" value="">` para mantener el alineamiento de listas.
2. Backend (`dynamic_filter.py`): `zip()` reemplazado por `zip_longest(..., fillvalue='')` como segunda defensa.

### Partial template
`templates/includes/filter_builder.html` — incluir con:
```html
{% include "includes/filter_builder.html" with clear_url="/leads/" %}
```
Requiere en contexto: `filter_fields` (JSON string), `active_filters` (lista de tuplas fc/fo/fv), `q`.

---

## Importación masiva de leads

**Formatos:** CSV (UTF-8 o Latin-1) y Excel (.xlsx, .xls)  
**Plantilla:** Leads → Importar → Descargar plantilla

### Columnas reconocidas
| Campo | Nombres aceptados |
|---|---|
| Nombre | `nombre_completo`, `nombre`, `name`, `full_name`, `apellido` |
| Teléfono | `telefono`, `phone`, `tel`, `celular`, `movil` |
| Código de país | `codigo_pais`, `codigopais`, `country_code`, `cod_pais` |
| Email | `email`, `correo`, `mail` |
| DNI | `dni`, `documento`, `cedula`, `rut` |
| Localidad | `localidad`, `ciudad`, `city` |
| Provincia | `provincia`, `province`, `region` |
| Estado | `estado`, `status`, `estado_lead` |
| Prioridad | `prioridad`, `priority` |
| Plan | `plan`, `plan_interes` |
| Origen | `origen`, `origin`, `source`, `fuente` |
| Notas | `notas`, `notes`, `observaciones`, `comentarios` |
| Agente | `agente`, `agent`, `vendedor`, `asesor` |
| Grupo familiar | `grupo_familiar`, `grupo` |

**Columnas extra** no reconocidas se guardan en `datos_extra` (JSON).

**Deduplicación:** busca por teléfono → por DNI. Si existe y "actualizar existentes" está activo, completa campos vacíos.

**Columna Agente:** acepta nombre completo, username o email. Tiene prioridad sobre el checkbox "asignarme los leads".

---

## Importación / Exportación de Deals

**Export** (`/negociaciones/exportar/`): CSV con BOM (Excel-compatible). Columnas: titulo, pipeline, etapa, valor, contacto, agente, descripcion, fecha_cierre_estimada, creado. Respeta filtros activos de la URL.

**Import** (`/negociaciones/importar/`): sube CSV, matchea pipeline/etapa/agente por nombre (case-insensitive). Errores reportados por fila.

---

## Tareas asíncronas (Celery)

| Tarea | Frecuencia | Descripción |
|---|---|---|
| `marcar_tareas_vencidas` | Cada 15 min | Marca como vencidas tareas pendientes con fecha pasada |
| `notificar_tareas_proximas` | Cada hora | Registra tareas en próximos 30 min |
| `ejecutar_automatizaciones` | Cada hora | Aplica reglas de automatización activas |
| `ejecutar_campana` | On-demand | Envío de campaña con rate limiting |
| `process_incoming_message` | On-demand | Procesa mensajes del webhook (3 reintentos) |
| `send_whatsapp_message_task` | On-demand | Envío de mensajes salientes |

> **Eliminadas en la migración a Evolution API:** `expire_24h_windows` y `sync_plantillas_status`. Si aparecen en `django_celery_beat` hay que eliminarlas desde `/admin/django_celery_beat/periodictask/`.

---

## Comandos útiles

```bash
# Ver logs en tiempo real
docker compose logs -f web
docker compose logs -f celery
docker compose logs -f evolution-api

# Reiniciar solo el web
docker compose restart web

# Shell de Django
docker compose exec web python manage.py shell

# Migraciones
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate

# Deploy estándar (servidor)
cd /opt/crmsalud/crmsalud && git pull && docker compose restart web

# Reiniciar Celery también (si hubo cambios en tasks)
docker compose restart celery celery-beat
```

---

## Estructura del proyecto

```
crmsupreg/
├── docker-compose.yml          # 5 servicios: web, db, redis, celery, celery-beat, evolution-api
├── .env.example
└── crm_obra_social/
    ├── Dockerfile
    ├── config/
    │   ├── settings/
    │   │   ├── base.py         # Settings base — incluye EVOLUTION_API_* vars
    │   │   ├── development.py
    │   │   └── production.py
    │   ├── urls.py
    │   └── celery.py
    ├── apps/
    │   ├── users/              # Usuarios, roles, autenticación (User.can_see_all_leads)
    │   ├── leads/              # Leads, pipeline, importación, CampoPersonalizado, Plan
    │   ├── clientes/           # Clientes afiliados (importación CSV/Excel)
    │   ├── deals/              # Negociaciones — Pipeline, PipelineStage, Deal, DealHistory
    │   ├── tasks/              # Agenda y tareas vinculadas a leads/clientes
    │   ├── quotes/             # Cotizaciones con PDF (WeasyPrint)
    │   ├── whatsapp/           # Inbox, webhook Evolution API, plantillas, bot, campaigns
    │   ├── campaigns/          # Campañas masivas vía Celery
    │   ├── automations/        # Reglas de automatización con triggers de tiempo
    │   ├── integrations/       # API pública con API Keys
    │   ├── chatbot/            # Editor visual de flujos (Drawflow)
    │   └── reports/            # Dashboard y reportes
    ├── utils/
    │   ├── dynamic_filter.py   # Filtros dinámicos multi-campo (Leads, Clientes)
    │   └── phone.py            # Normalización de teléfonos AR
    ├── templates/
    │   ├── base.html
    │   ├── includes/
    │   │   └── filter_builder.html  # Partial de filtros dinámicos (reutilizable)
    │   └── <app>/              # Templates por módulo
    ├── static/css/main.css
    └── media/                  # Documentos, avatares, PDFs de cotizaciones
```

---

## URLs principales

| Sección | URL |
|---|---|
| Dashboard | `/` |
| Leads — Lista | `/leads/` |
| Leads — Kanban | `/leads/kanban/` |
| Leads — Importar | `/leads/importar/` |
| Leads — Exportar | `/leads/exportar/` |
| Leads — Asignación masiva | `/leads/asignar-masivo/` |
| Leads — Campos personalizados | `/leads/campos/` |
| Contactos (unificado) | `/leads/contactos/` |
| Clientes | `/clientes/` |
| Clientes — Importar | `/clientes/importar/` |
| Negociaciones — Kanban | `/negociaciones/` |
| Negociaciones — Lista | `/negociaciones/lista/` |
| Negociaciones — Exportar | `/negociaciones/exportar/` |
| Negociaciones — Importar | `/negociaciones/importar/` |
| Negociaciones — Pipelines | `/negociaciones/pipelines/` |
| Agenda | `/tareas/agenda/` |
| Cotizaciones | `/cotizaciones/` |
| WhatsApp Inbox | `/whatsapp/inbox/` |
| WhatsApp Webhook | `/whatsapp/webhook/` |
| WhatsApp Config | `/whatsapp/configuracion/` |
| WhatsApp QR | `/whatsapp/qr/` |
| WhatsApp Estado conexión | `/whatsapp/estado/` |
| Plantillas de Mensaje | `/whatsapp/plantillas/` |
| Bot WhatsApp | `/whatsapp/bot/` |
| Chatbot Visual | `/chatbot/` |
| Campañas | `/campanas/` |
| Automatizaciones | `/automatizaciones/` |
| Integraciones API | `/integraciones/` |
| API Pública | `/api/v1/` |
| Reportes — Conversión | `/reportes/conversion/` |
| Reportes — Mensajes | `/reportes/mensajes/` |
| Usuarios | `/usuarios/` |
| Django Admin | `/admin/` |

---

## Trabajo pendiente / en curso

### Migración Evolution API — Templates (en progreso)

La migración de WhatsApp de Meta Cloud API a Evolution API está casi completa. Los cambios de backend ya fueron aplicados (modelos, sender, webhook, tasks, views, urls). Lo que falta:

**Templates HTML por actualizar:**

1. **`templates/whatsapp/config.html`** — reemplazar formulario Meta por:
   - Campos Evolution API (URL, API key, instance name, webhook token)
   - Panel de estado de conexión + QR con polling JS (GET `/whatsapp/qr/` y `/whatsapp/estado/`)

2. **`templates/whatsapp/inbox.html`** — eliminar:
   - Badge/indicador de ventana 24h activa/expirada
   - Lógica JS que bloqueaba el input de texto según ventana
   - El input de texto debe estar **siempre habilitado**

3. **`templates/whatsapp/plantilla_list.html`** — eliminar:
   - Columna "Estado" (PENDING/APPROVED/REJECTED)
   - Columna "Último sync"
   - Botones "Enviar a Meta" y "Sincronizar"
   - Alert explicando flujo de aprobación Meta

4. **`templates/whatsapp/plantilla_form.html`** — eliminar campos:
   - `nombre_meta`, `status`, `meta_template_id`, `ultimo_sync_at`

5. **`templates/base.html`** — cambiar:
   - "Plantillas HSM" → "Plantillas"
   - "Configurar WhatsApp" visible para supervisores (no solo superadmin)

**Configuración Docker:**
- `docker-compose.yml`: ya tiene el servicio `evolution-api` agregado ✅
- `.env.example`: ya tiene las variables de Evolution API ✅
- `config/settings/base.py`: verificar que tenga las vars `EVOLUTION_*` y no las de Meta

### Convención de deploy
El proyecto corre en `/opt/crmsalud/crmsalud/` en el servidor. Deploy estándar:
```bash
cd /opt/crmsalud/crmsalud && git pull && docker compose restart web
```
Si hay cambios en Celery tasks también: `docker compose restart celery celery-beat`
