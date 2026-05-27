# CRM Obra Social

Sistema CRM completo para agentes comerciales de obras sociales argentinas. Gestiona el ciclo de vida completo del prospecto: captación, seguimiento, cotización, afiliación y comunicación por WhatsApp.

---

## Índice

- [Stack tecnológico](#stack-tecnológico)
- [Servicios Docker](#servicios-docker)
- [Instalación y puesta en marcha](#instalación-y-puesta-en-marcha)
- [Variables de entorno](#variables-de-entorno)
- [Configuración del Webhook de WhatsApp](#configuración-del-webhook-de-whatsapp)
- [Roles y permisos](#roles-y-permisos)
- [Módulos del sistema](#módulos-del-sistema)
  - [Leads](#leads)
  - [Clientes](#clientes)
  - [Contactos](#contactos)
  - [Kanban](#kanban)
  - [Agenda / Tareas](#agenda--tareas)
  - [Cotizaciones](#cotizaciones)
  - [WhatsApp Inbox](#whatsapp-inbox)
  - [Plantillas HSM](#plantillas-hsm)
  - [Bot WhatsApp](#bot-whatsapp)
  - [Chatbot Visual](#chatbot-visual)
  - [Campañas masivas](#campañas-masivas)
  - [Automatizaciones](#automatizaciones)
  - [Integraciones API](#integraciones-api)
  - [Campos personalizados](#campos-personalizados)
  - [Reportes](#reportes)
  - [Usuarios](#usuarios)
- [Importación masiva de leads](#importación-masiva-de-leads)
- [Tareas asíncronas (Celery)](#tareas-asíncronas-celery)
- [Comandos útiles](#comandos-útiles)
- [Estructura del proyecto](#estructura-del-proyecto)
- [URLs principales](#urls-principales)

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

---

## Servicios Docker

```
web          → Django + Gunicorn (puerto 8000)
db           → PostgreSQL 15 (puerto 5433)
redis        → Redis 7 (128 MB LRU)
celery       → Worker (concurrencia 2)
celery-beat  → Scheduler de tareas periódicas
```

---

## Instalación y puesta en marcha

```bash
git clone <repo>
cd crmsupreg
cp .env.example .env          # completar variables
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py collectstatic --noinput
```

Acceder en: `http://localhost:8000`
Django Admin: `http://localhost:8000/admin`

---

## Variables de entorno

```env
# Django
SECRET_KEY=tu-secret-key-larga-y-segura
DEBUG=False
ALLOWED_HOSTS=tudominio.com,www.tudominio.com

# Base de datos
POSTGRES_DB=crmsupreg
POSTGRES_USER=crm_user
POSTGRES_PASSWORD=password_seguro
DB_HOST=db
DB_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/0

# WhatsApp Meta Cloud API
WHATSAPP_ACCESS_TOKEN=tu_token_de_meta
WHATSAPP_PHONE_NUMBER_ID=tu_phone_number_id
WHATSAPP_BUSINESS_ACCOUNT_ID=tu_waba_id
WHATSAPP_APP_SECRET=tu_app_secret
WHATSAPP_WEBHOOK_VERIFY_TOKEN=tu_token_verificacion
```

---

## Configuración del Webhook de WhatsApp

1. En Meta Business Manager → WhatsApp → Configuración → Webhooks
2. URL del webhook: `https://tu-dominio.com/whatsapp/webhook/`
3. Verify Token: el valor de `WHATSAPP_WEBHOOK_VERIFY_TOKEN` del `.env`
4. Suscribirse a los eventos: `messages`, `message_deliveries`, `message_reads`

En desarrollo podés usar **ngrok** para exponer el servidor local:
```bash
ngrok http 8000
```

Las credenciales también se pueden configurar desde el panel en `/whatsapp/configuracion/` (solo superadmin).

---

## Roles y permisos

El sistema tiene tres roles con niveles de acceso diferenciados:

| Funcionalidad | Agente | Supervisor | Superadmin |
|---|:---:|:---:|:---:|
| Ver sus propios leads | ✅ | ✅ | ✅ |
| Ver todos los leads | ❌ | ✅ | ✅ |
| Asignación masiva de agentes | ❌ | ✅ | ✅ |
| Importar / exportar leads | ❌ | ✅ | ✅ |
| Convertir lead a cliente | ❌ | ✅ | ✅ |
| Campañas masivas | ❌ | ✅ | ✅ |
| Automatizaciones | ❌ | ✅ | ✅ |
| Plantillas HSM | ❌ | ✅ | ✅ |
| Chatbot visual | ❌ | ✅ | ✅ |
| Integraciones API | ❌ | ✅ | ✅ |
| Gestión de usuarios | ❌ | ✅ | ✅ |
| Campos personalizados | ❌ | ✅ | ✅ |
| Configurar WhatsApp API | ❌ | ❌ | ✅ |

**Regla de visibilidad:** Los agentes solo ven los leads, clientes, tareas y conversaciones que tienen asignados. Los supervisores y superadmins ven todo.

---

## Módulos del sistema

### Leads

Pipeline principal de ventas. Un lead representa un prospecto que aún no se convirtió en cliente.

**Estados del pipeline:**

```
Nuevo → Contactado → Interesado → Doc. Pendiente → En Revisión → Afiliado
                                                              ↘ Perdido
```

**Campos:**
- Datos personales: nombre completo, DNI (7-8 dígitos), fecha de nacimiento, teléfono (formato `+54...`), email, localidad, provincia
- Comerciales: plan de interés, grupo familiar, origen, prioridad (Alta / Media / Baja)
- Agente asignado
- Motivo de pérdida (al marcar como Perdido)
- Datos extra: JSON para columnas personalizadas importadas o campos adicionales
- Documentos adjuntos: recibo de sueldo, DNI, contrato, otros
- Historial completo de cambios de estado con fecha, usuario y nota

**Funcionalidades:**
- Filtrado por nombre, DNI, teléfono, email, estado, prioridad, origen, plan, agente y rango de fechas
- Exportación a CSV con todos los campos
- Conversión a cliente (supervisor+)
- Carga de documentos por tipo con íconos automáticos
- Botón directo a WhatsApp desde el listado
- **Asignación masiva:** checkboxes para seleccionar múltiples leads y asignarlos a un agente en un clic (supervisor+)

---

### Clientes

Leads que completaron el proceso de afiliación.

**Campos adicionales respecto al lead:**
- Número de afiliado
- Plan contratado (FK)
- Fecha de alta

**Funcionalidades:**
- Listado con búsqueda por nombre, DNI, teléfono, número de afiliado y plan
- Importación masiva por CSV/Excel
- Edición de campos personalizados
- Ver tareas relacionadas
- Botón directo a WhatsApp desde el listado

---

### Contactos

Vista unificada que combina leads y clientes en una sola tabla. Permite filtrar por tipo (solo leads, solo clientes, o ambos) para tener una visión global sin cambiar de sección.

---

### Kanban

Vista de tablero del pipeline de leads. Columnas por estado con drag & drop para mover leads entre estados. Cada agente ve solo sus leads asignados; supervisores ven todos.

---

### Agenda / Tareas

Gestión de tareas vinculadas a leads o clientes.

**Tipos:** Llamada, WhatsApp, Reunión, Documentación, Seguimiento

**Estados:** Pendiente / Completada / Vencida

**Funcionalidades:**
- Vista de agenda semanal
- Filtro por tipo y estado
- Registro del resultado al completar
- Badge en el navbar con tareas pendientes del día
- Detección automática de tareas vencidas (Celery cada 15 min)

---

### Cotizaciones

Generación de propuestas comerciales en PDF.

**Campos:**
- Lead vinculado, plan, monto mensual, notas
- Integrantes familiares (nombre, DNI, fecha de nacimiento, parentesco: titular / cónyuge / hijo / otro)
- Estado: Borrador / Enviada / Aceptada / Rechazada

**Funcionalidades:**
- Generación de PDF con WeasyPrint (guardado en `media/cotizaciones/pdf/`)
- Descarga directa del PDF
- Envío de la cotización directamente por WhatsApp al lead

---

### WhatsApp Inbox

Bandeja de entrada estilo WhatsApp Web con panel dual: lista de conversaciones a la izquierda y chat a la derecha.

**Funcionalidades:**
- Polling automático (mensajes cada 4s, inbox cada 8s)
- Filtro por estado de conversación y no leídos
- Envío de texto libre (dentro de la ventana de 24h activa)
- Envío de plantillas HSM aprobadas (dentro y fuera de la ventana)
- Envío de mensajes con botones interactivos
- Envío de listas de opciones
- Indicador visual de ventana de 24h activa/expirada
- Historial completo con estado por mensaje (enviado / entregado / leído / error)
- Inicio de conversación desde los listados de leads, contactos y clientes

**Ventana de 24 horas (política Meta):**
- Dentro de la ventana: texto libre
- Fuera de la ventana: solo plantillas HSM aprobadas

---

### Plantillas HSM

Gestión del ciclo de vida completo de mensajes pre-aprobados por Meta.

**Campos:**
- Nombre, categoría (Marketing / Utilidad / Autenticación), idioma
- Cuerpo con variables `{{1}}`, `{{2}}`, etc.
- Encabezado: ninguno, texto, imagen, documento o video
- Pie de página (max 60 caracteres)
- Botones: respuesta rápida, URL o llamada telefónica

**Estados:** Pendiente → Aprobada / Rechazada

**Funcionalidades:**
- Crear plantilla en borrador
- Enviar a Meta para aprobación
- Sincronizar estado desde Meta
- Vista previa con variables de ejemplo
- Uso en campañas masivas y automatizaciones

---

### Bot WhatsApp

Reglas de auto-respuesta para mensajes entrantes sin intervención humana.

**Tipos de disparo:**
- Primer mensaje de un contacto nuevo (mensaje de bienvenida)
- Palabra clave detectada en el mensaje (case-insensitive)

**Tipos de respuesta:**
- Texto libre
- Plantilla HSM aprobada
- Mensaje interactivo con botones

**Acciones opcionales al disparar:**
- Cambiar estado del lead automáticamente
- Cambiar prioridad del lead
- Solo ejecutar si el lead no tiene agente asignado
- Solo ejecutar una vez por conversación (evita respuestas repetidas)

---

### Chatbot Visual

Editor visual de flujos de conversación drag & drop, similar a WATI/ManyChat. Permite diseñar bots complejos con lógica ramificada.

**Nodos disponibles:**

| Nodo | Descripción |
|---|---|
| Inicio | Punto de entrada del flujo |
| Enviar mensaje | Envía un texto al contacto |
| Hacer pregunta | Hace una pregunta y guarda la respuesta en una variable |
| Botones | Mensaje con hasta 3 botones interactivos (WhatsApp) |
| Lista de opciones | Menú desplegable con hasta 5 opciones |
| Condición | Ramifica el flujo según el valor de una variable (Sí / No) |
| Actualizar atributo | Actualiza un campo del lead (nombre, estado, plan, prioridad, etc.) |
| Asignar etiqueta | Agrega una etiqueta al contacto |
| Asignar agente | Asigna el lead a un agente específico |
| Asignar equipo | Asigna el lead a un equipo |
| Suscribir | Suscribe el contacto a campañas masivas |
| Desuscribir | Desuscribe el contacto de campañas masivas |

**Funcionalidades del editor:**
- Canvas con pan, zoom y conexiones entre nodos
- Panel izquierdo: librería de nodos por categoría
- Panel derecho: formulario de configuración del nodo seleccionado
- Historial de deshacer/rehacer (Ctrl+Z / Ctrl+Y)
- Guardado con Ctrl+S o botón, con indicador de estado
- Los flujos se almacenan como JSON en la base de datos

---

### Campañas masivas

Envío masivo de mensajes WhatsApp usando plantillas HSM aprobadas.

**Selección de destinatarios:**

*Por segmento (filtros automáticos):*
- Plan específico
- Provincia (búsqueda parcial)
- Estado del lead
- Días sin contacto (leads inactivos)
- Tipo: solo leads, solo clientes, o ambos

*Manual:*
- Búsqueda y selección individual de leads y clientes desde el formulario

**Preview en tiempo real:** muestra la cantidad exacta de destinatarios antes de lanzar.

**Variables de plantilla:** se mapean a campos del contacto:
- `nombre_completo`, `email`, `plan`, `localidad`, `provincia`, `telefono`
- Soporte para campos personalizados

**Ejecución:**
- Asíncrona vía Celery
- Rate limiting: ~800 mensajes/min (margen bajo el límite de 1000/min de Meta)
- Log individual por mensaje con estado (enviado / error)
- Estadísticas en tiempo real: enviados, entregados, leídos, errores

---

### Automatizaciones

Reglas que se ejecutan automáticamente cada hora sobre leads que cumplen determinados criterios de tiempo.

**Triggers (basados en tiempo):**
- N días desde que se creó el lead
- N días sin actividad (sin cambios registrados)
- N días sin respuesta de WhatsApp del contacto

**Condiciones opcionales:**
- Estado del lead (cualquiera o uno específico)
- Prioridad del lead
- Origen del lead

**Acciones disponibles:**
1. Cambiar estado del lead
2. Cambiar prioridad del lead
3. Enviar plantilla HSM de WhatsApp al lead
4. Crear tarea para el agente asignado (con plazo en días)

**Funcionalidades:**
- Activar/desactivar sin eliminar
- Ejecución manual para pruebas
- Log de cada ejecución por regla y lead
- Prevención de duplicados: la misma regla no se aplica dos veces al mismo lead

---

### Integraciones API

API REST pública para recibir leads desde sistemas externos (landing pages, formularios web, otros CRMs).

**Autenticación:** API Key en header `Authorization: Api-Key <key>`

**Endpoints disponibles:**

```
POST /api/v1/leads/            → Crear lead desde sistema externo
GET  /api/v1/leads/<id>/       → Consultar estado de un lead
POST /api/v1/webhook/<source>/ → Webhook genérico
```

**Campos al crear lead:**
- `nombre_completo` (requerido), `telefono` (requerido)
- `email`, `dni`, `localidad`, `provincia`, `codigo_pais`, `plan_id` (opcionales)

**Gestión de API Keys:**
- Nombre, descripción, estado activo/inactivo
- Agente por defecto, estado inicial y origen por defecto para los leads creados con esa key
- Estadísticas: última vez usada, total de usos
- Log completo de cada llamada: IP, request/response, duración, resultado

---

### Campos personalizados

Sistema de campos dinámicos para extender los modelos sin modificar la base de datos.

**Tipos de campo:** Texto libre, Número, Fecha, Booleano (Sí/No), Lista (dropdown con opciones)

**Alcance:** Solo leads, solo clientes, o ambos.

Los valores se almacenan en el campo JSON `datos_extra` del lead/cliente y se muestran como campos editables en el formulario de detalle. También se pueden usar en:
- Mapeo de variables en campañas masivas
- Plantillas de descripción en tareas de automatización
- Importación masiva (columnas extra del Excel)

---

### Reportes

**Dashboard principal (`/`):**
- Conteo de leads por cada estado del pipeline
- Tareas del día (lista de las 10 más próximas)
- Conversaciones con mensajes no leídos
- Actividad reciente (últimos 10 leads actualizados)
- Ranking de agentes por leads afiliados (supervisor+)
- Leads creados esta semana

**Reporte de conversión (`/reportes/conversion/`):**
- Funnel completo con conteos por estado
- Leads por origen (Web, Campaña, Referido, Llamada, WhatsApp)
- Leads por agente con métricas de conversión

**Reporte de mensajes (`/reportes/mensajes/`):**
- Mensajes enviados y recibidos filtrados por rango de fechas

**Exportación:** CSV del reporte de conversión desde `/reportes/exportar/`

---

### Usuarios

Gestión de cuentas del sistema (supervisor+).

**Campos:** nombre, apellido, email (usuario de login), rol, teléfono interno, avatar, estado activo/inactivo.

**Roles:** Superadmin / Supervisor / Agente

---

## Importación masiva de leads

Formatos soportados: **CSV** (UTF-8 o Latin-1) y **Excel** (`.xlsx`, `.xls`)

Descargar plantilla oficial: **Leads → Importar → Descargar plantilla**

### Columnas reconocidas automáticamente

| Campo | Nombres de columna aceptados |
|---|---|
| Nombre completo | `nombre_completo`, `nombre`, `name`, `full_name`, `apellido` |
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

### Columna Agente

Permite asignar cada lead a un agente diferente dentro del mismo archivo. Acepta:
- Nombre completo del agente (`Juan Pérez`)
- Username
- Email

Si el valor no coincide con ningún usuario activo, el lead queda sin agente (o con el valor por defecto del formulario). La columna `Agente` del archivo tiene prioridad sobre el checkbox "Asignarme los leads".

### Deduplicación

1. Busca por **teléfono**
2. Si no encuentra, busca por **DNI**
3. Si existe y "actualizar existentes" está activado → actualiza campos vacíos
4. Si existe y no está activado → omite la fila

### Columnas extra

Cualquier columna no reconocida se guarda en `datos_extra` como JSON. Si existe un campo personalizado con ese nombre, se asocia y valida automáticamente.

### Opciones del formulario de importación

- **Actualizar existentes:** si un lead ya existe, actualiza sus campos vacíos con los valores del archivo
- **Asignarme los leads:** asigna todos los leads importados al usuario que realiza la importación (la columna `Agente` del archivo tiene prioridad)

---

## Tareas asíncronas (Celery)

| Tarea | Frecuencia | Descripción |
|---|---|---|
| `marcar_tareas_vencidas` | Cada 15 min | Marca como vencidas las tareas pendientes con fecha pasada |
| `notificar_tareas_proximas` | Cada hora | Registra tareas en los próximos 30 min para alertas |
| `ejecutar_automatizaciones` | Cada hora | Aplica todas las reglas de automatización activas |
| `expire_24h_windows` | Cada hora | Expira ventanas de 24h de WhatsApp vencidas |
| `sync_plantillas_status` | Cada 30 min | Sincroniza estado de plantillas HSM desde Meta |
| `ejecutar_campana` | On-demand | Envío de campaña masiva con rate limiting |
| `process_incoming_message` | On-demand | Procesamiento de mensajes del webhook (3 reintentos) |
| `send_whatsapp_message_task` | On-demand | Envío de mensajes salientes de WhatsApp |

---

## Comandos útiles

```bash
# Ver logs en tiempo real
docker compose logs -f web
docker compose logs -f celery

# Shell de Django
docker compose exec web python manage.py shell

# Migraciones
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate

# Cargar fixtures de planes iniciales
docker compose exec web python manage.py loaddata apps/leads/fixtures/planes_iniciales.json

# Reiniciar solo el worker de Celery
docker compose restart celery celery-beat
```

---

## Estructura del proyecto

```
crmsupreg/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env
└── crm_obra_social/
    ├── config/
    │   ├── settings/
    │   │   ├── base.py
    │   │   ├── development.py
    │   │   └── production.py
    │   ├── urls.py
    │   └── celery.py
    ├── apps/
    │   ├── users/          # Usuarios, roles y autenticación
    │   ├── leads/          # Leads, pipeline, importación, campos personalizados
    │   ├── clientes/       # Clientes afiliados
    │   ├── tasks/          # Agenda y tareas
    │   ├── quotes/         # Cotizaciones con PDF
    │   ├── whatsapp/       # Inbox, webhook Meta, plantillas HSM, bot
    │   ├── campaigns/      # Campañas masivas
    │   ├── automations/    # Reglas de automatización
    │   ├── integrations/   # API Keys y webhooks externos
    │   ├── chatbot/        # Editor visual de flujos de chatbot
    │   └── reports/        # Dashboard y reportes
    ├── templates/          # Templates HTML (Bootstrap 5)
    ├── static/
    │   └── css/main.css
    └── media/              # Archivos subidos (documentos, avatares, PDFs)
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
| Contactos (unificado) | `/leads/contactos/` |
| Clientes | `/clientes/` |
| Agenda | `/tareas/agenda/` |
| Cotizaciones | `/cotizaciones/` |
| WhatsApp Inbox | `/whatsapp/inbox/` |
| WhatsApp Webhook | `/whatsapp/webhook/` |
| Plantillas HSM | `/whatsapp/plantillas/` |
| Bot WhatsApp | `/whatsapp/bot/` |
| Chatbot Visual | `/chatbot/` |
| Campañas | `/campanas/` |
| Automatizaciones | `/automatizaciones/` |
| Integraciones API | `/integraciones/` |
| API Pública | `/api/v1/` |
| Reportes — Conversión | `/reportes/conversion/` |
| Reportes — Mensajes | `/reportes/mensajes/` |
| Campos personalizados | `/leads/campos/` |
| Usuarios | `/usuarios/` |
| Configurar WhatsApp | `/whatsapp/configuracion/` |
| Django Admin | `/admin/` |
