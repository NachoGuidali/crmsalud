# 🔍 Auditoría Completa — CRM Obra Social

**Fecha:** 25/05/2026  
**Versión analizada:** commit `9f53a19`  
**Equipo de análisis:** QA Senior · Arquitecto de Software · Ingeniero Senior · Analista DEER · Usuario Final

---

## 1. 🏗️ ARQUITECTURA E INFRAESTRUCTURA

**Patrón arquitectónico:** Monolito Django con workers asíncronos (Celery + Redis). Apropiado para un CRM en etapa inicial/media. No hay microservicios ni necesidad de ellos a esta escala.

**Estructura de apps:**
```
apps/users · leads · tasks · quotes · whatsapp
     campaigns · reports · automations · integrations · clientes
```
✅ Buena separación por dominio. Cada app tiene su propio `models/views/urls`. La dependencia entre apps es razonable (`tasks → leads`, `campaigns → whatsapp`, etc.).

**Configuración de entornos:** ✅ `config/settings/base.py` + `production.py`. La producción apaga `DEBUG`, configura HSTS, cookies seguras y `SECURE_PROXY_SSL_HEADER` correctamente (nginx como proxy SSL).

⚠️ **`CSRF_TRUSTED_ORIGINS`** está hardcodeado en `production.py` (`https://crm.supregsolutions.com`). Si el dominio cambia hay que tocar código en vez de `.env`.

⚠️ **Secrets sin validación al arrancar.** Si `DJANGO_SECRET_KEY` no está seteado en `.env`, usa `'change-me-in-production'` — Django arranca igualmente en producción con esa key.

**Docker / Deploy:**
- ✅ `docker-compose.yml` con healthchecks en db y redis
- ✅ Bind mount para staticfiles (correcto para nginx en host)
- ⚠️ El comando de inicio incluye `makemigrations --noinput` en producción. Peligroso: si hay conflictos de migración o modelos rotos, el contenedor no levanta. Las migraciones deberían estar commiteadas y solo correr `migrate`, nunca `makemigrations` en producción.
- ⚠️ `--reload` en gunicorn en producción (`gunicorn ... --reload`). Este flag recarga código cuando detecta cambios en archivos — es para desarrollo, en producción agrega overhead de inotify y puede causar reloads inesperados.
- 🔴 No hay CI/CD configurado (ni GitHub Actions ni similar). Deploy manual.
- 🔴 No hay healthcheck para el contenedor `web`.

**Logging:** ✅ Configurado para `apps.whatsapp` y `apps.campaigns` con handler a archivo. ⚠️ El archivo de log (`BASE_DIR / 'logs' / 'django.log'`) no tiene rotación configurada — puede crecer indefinidamente. El directorio `logs/` no está en el repo ni se crea automáticamente al iniciar.

**Monitoreo:** 🔴 No hay monitoreo de aplicación (Sentry, Datadog, etc.). En producción, los errores 500 solo se ven revisando logs de Docker manualmente.

> **Resumen:** Arquitectura sólida para el tamaño del proyecto. Los problemas críticos son el `makemigrations` en producción, el `--reload` de gunicorn, y la ausencia total de monitoreo y CI/CD.

---

## 2. 🔒 SEGURIDAD

**Autenticación y roles:** ✅ Django sessions + `AbstractUser` con roles (`superadmin/supervisor/agente`). La propiedad `can_see_all_leads` centraliza el control de visibilidad:

```python
# apps/users/models.py
@property
def can_see_all_leads(self):
    return self.role in (self.ROLE_SUPERADMIN, self.ROLE_SUPERVISOR)
```

⚠️ La autorización se hace en cada vista con `UserPassesTestMixin` o checks manuales. No hay un decorador/mixin centralizado reutilizable para todos los casos — si alguien agrega una vista nueva y olvida el check, queda expuesto.

**API externa (integraciones):** ✅ `ApiKey` usa UUID v4 (`uuid.uuid4`) como token — no predecible. ⚠️ La validación del API key en las vistas de integración debería verificar `activa=True` al momento del lookup — una key desactivada podría seguir funcionando si el filtro no lo incluye.

**CSRF:** ✅ Habilitado. `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True` en producción.

**XSS:** ✅ Django auto-escapa templates. No se usa `mark_safe` en ningún lugar visible.

**SQL Injection:** ✅ ORM de Django, no hay queries raw.

**Datos sensibles en logs:** ⚠️ `WebhookLog.request_body` guarda el body completo de cada llamada entrante al API (`apps/integrations/models.py`). Si un formulario externo manda DNI, número de tarjeta u otros datos sensibles, quedan logueados en base de datos.

**Rate limiting:** 🔴 No existe. El endpoint de webhook de WhatsApp (`/whatsapp/webhook/`) y los endpoints de API (`/api/v1/`) no tienen throttling. Un atacante puede spamear leads o intentar fuerza bruta en login sin límite.

**WhatsApp webhook signature:** ⚠️ `WHATSAPP_APP_SECRET` está configurado en settings pero hay que verificar si el webhook valida la firma HMAC-SHA256 de Meta. Si no lo hace, cualquiera puede hacer POST a `/whatsapp/webhook/` e inyectar mensajes falsos.

**Headers de seguridad:** ✅ `SECURE_HSTS_SECONDS = 31536000`. ⚠️ No se configuran `X-Content-Type-Options`, `Referrer-Policy`, ni `Permissions-Policy` explícitamente.

**Contraseñas:** ✅ Django `AbstractUser` usa PBKDF2 por defecto. Los 4 validadores de contraseña están activos en `base.py`.

> **Resumen:** Base de seguridad sólida para Django. Los gaps críticos son la falta de rate limiting, la validación de firma del webhook de WhatsApp, y datos sensibles en `WebhookLog.request_body`.

---

## 3. 📊 ANÁLISIS DEER

### Desempeño

**🔴 N+1 en dashboard** — `DashboardView` (`apps/reports/views.py`) hace un query por cada estado del pipeline en un loop:
```python
leads_por_estado = {
    estado: lead_qs.filter(estado=estado).count()
    for estado, _ in Lead.ESTADO_CHOICES
}
```
Son 7 queries COUNT separadas. Debería ser un solo `values('estado').annotate(total=Count('id'))`.

**🔴 ContactListView carga todo en memoria** — `list(leads_qs) + list(clientes_qs)` antes de paginar. Con 10.000 leads + 5.000 clientes, esto instancia 15.000 objetos ORM en memoria en cada request de la página de contactos. El Paginator recibe una lista Python, no un queryset, por lo que no hace LIMIT/OFFSET en SQL.

**⚠️ select_related inconsistente** — algunas vistas usan `select_related` correctamente, otras acceden a relaciones en templates dentro de loops sin haberlo declarado, generando queries implícitas.

**✅ Paginación:** La mayoría de las listas paginan (25 leads, 50 mensajes por página según `base.py`).

**✅ Celery:** Jobs pesados (envío de campaña, automatizaciones) se ejecutan en background.

**⚠️ Caching:** Redis está configurado como backend de cache (`CACHES`) pero no se usa ningún `@cache_page` ni `cache.get/set` explícito en vistas. El cache existe pero está ocioso.

**⚠️ WeasyPrint para PDF** — sincrónico en el request. Generar un PDF de cotización bloquea el worker de gunicorn. Debería ser una tarea Celery.

### Estabilidad

**⚠️ `dict_key` template filter devuelve `0` para claves faltantes:**
```python
# apps/leads/templatetags/crm_tags.py
def dict_key(d, key):
    if isinstance(d, dict):
        return d.get(key, 0)  # ← devuelve 0, no ''
    return 0
```
En un campo tipo "texto" vacío va a mostrar `0` en la UI en lugar de `—` o vacío.

**⚠️ `AutomatizacionLog.unique_together = [('regla', 'lead')]`** — Significa que cada regla solo puede ejecutarse **una vez por lead en toda su vida**. Si un lead "resetea" su estado, la regla no se vuelve a disparar nunca.

**⚠️ Tarea.is_vencida es una `@property` sin persistencia** — El estado `vencida` se calcula en runtime pero `Tarea.status` en DB puede seguir siendo `pendiente`. Hay un mismatch entre lo que se ve en UI y lo que está en DB, lo que puede generar bugs en filtros y reportes.

**🔴 Migración faltante para `CampoPersonalizado` y `Cliente`** — Los modelos existen en código pero no hay archivos de migración commiteados. El contenedor web corre `makemigrations` al arrancar y genera los archivos, pero si hay un deploy fresco o un conflicto, el sistema falla.

### Escalabilidad

**⚠️ ContactListView (ya mencionado)** — No escala más allá de ~5.000 registros combinados sin rediseño.

**✅ Celery + Beat** — Workers separados para tareas y scheduler. Bien configurado para escalar horizontalmente los workers.

**⚠️ 2 workers de gunicorn hardcodeados** (`--workers 2`). Para mayor carga debería ser dinámico (`$(( 2 * $(nproc) + 1 ))`).

**⚠️ PostgreSQL en el mismo compose que la app** — Para escalar en producción real, la DB debería estar en un servicio gestionado separado (RDS, Cloud SQL).

### Resiliencia

**⚠️ Sin backups configurados** — No hay dump automático de PostgreSQL ni política de backup definida en el repo.

**✅ `restart: unless-stopped`** en todos los servicios — Los contenedores se recuperan solos si crashean.

**⚠️ Sin circuit breaker para la API de WhatsApp** — Si Meta's API está caída, las tareas Celery de envío van a fallar y reintentar indefinidamente. No hay `max_retries` ni `retry_backoff` configurados en las tareas.

**⚠️ Redis como broker de Celery sin persistencia de mensajes configurada** — Si Redis cae sin AOF/RDB habilitado, las tareas en cola se pierden.

> **Resumen:** El problema de desempeño más urgente es `ContactListView` cargando todo en memoria. En estabilidad, la migración faltante y el `unique_together` de automatizaciones son los más riesgosos. La resiliencia es básica pero funcional para escala pequeña.

---

## 4. 🧱 CALIDAD DE CÓDIGO E INGENIERÍA

**SOLID:**
- ✅ Single Responsibility: cada app tiene su dominio bien delimitado
- ⚠️ `apps/leads/views.py` tiene **750 líneas** con 20+ clases. Las vistas de `CampoPersonalizado` podrían vivir en un archivo `campo_views.py` separado
- ⚠️ `LeadQuerysetMixin` mezcla la lógica de filtro de agente con la vista — aceptable pero podría ser un manager de modelo

**DRY:**
- ✅ `LeadQuerysetMixin` centraliza la visibilidad de leads por rol
- ⚠️ La lógica de "agente solo ve sus registros" se repite en `DashboardView`, `ContactListView`, `ReporteConversionView`, `ReporteMensajesView` — un queryset base haría esto más DRY

**Deuda técnica identificada:**
- `makemigrations` en producción en `docker-compose.yml`
- `gunicorn --reload` en producción en `docker-compose.yml`
- `dict_key` devuelve `0` en vez de `''` en `crm_tags.py`
- `Tarea.status` vs `is_vencida` desincronizados en `apps/tasks/models.py`
- `ContactListView` con paginación en memoria en `apps/leads/views.py`

**Complejidad ciclomática:**
- ⚠️ `LeadImportView` — la función más compleja del proyecto. Parsea, valida, deduplica, crea/actualiza leads y registra historial en un solo método. Sin tests específicos para esta lógica.

**Naming:**
- ✅ Consistente en español (nombres de modelo, verbose_name, campos)
- ⚠️ `_tipo` como atributo de instancia dinámico en `ContactListView` (`obj._tipo = 'lead'`) — prefijo `_` indica privado/interno pero se usa en templates. Mejor sin underscore.

**Comentarios:** ✅ Pocos y útiles cuando existen.

**TODOs/FIXMEs:** No se detectaron en el código.

> **Resumen:** Código limpio y bien organizado para el tamaño del proyecto. La deuda principal es `leads/views.py` monolítico, la paginación en memoria en contactos, y varios estados desincronizados entre modelo y lógica de negocio.

---

## 5. 🧪 TESTING

**Tests existentes:**

`apps/leads/tests.py` — ✅ Significativo:
- Validación de DNI y teléfono (model level)
- Control de acceso por rol (agente vs supervisor)
- Endpoint kanban

`apps/whatsapp/tests.py` — ✅ Significativo:
- Parsing de webhook (incluyendo caso vacío)
- Mock de `requests.post` para el sender
- Extracción de contenido de audio

**Cobertura estimada: ~15-20%**

**🔴 Sin tests en:**
- `apps/clientes/` — app nueva, sin un solo test
- `apps/campaigns/` — lógica de envío masivo sin cobertura
- `apps/automations/` — la ejecución de reglas es lógica de negocio crítica sin test
- `apps/reports/` — los reportes y el dashboard no se testean
- `apps/quotes/` — generación de PDF sin test
- `apps/integrations/` — el endpoint público de API (el más expuesto) sin test de integración
- `LeadImportView` — la lógica más compleja del proyecto sin test

**Calidad de los tests existentes:** ✅ Los tests de leads usan fixtures en `setUp`, testean comportamiento real (no mocks de ORM), y cubren casos borde reales. Los tests de WhatsApp mockean correctamente la capa HTTP.

**Qué debería testearse urgente:**
1. `apps/integrations/` — API pública, endpoint más crítico para seguridad
2. `LeadImportView` — manejo de CSV malformados, duplicados, encoding
3. `apps/automations/` — que las reglas se disparen y se logueen correctamente
4. `LeadConvertirView` — que la conversión crea el Cliente y borra el Lead

> **Resumen:** Base de testing sólida en leads y whatsapp, pero cobertura muy baja en el resto. Las apps de integración, campañas y automatizaciones — todas con lógica crítica — no tienen ningún test.

---

## 6. 🎨 DISEÑO UX/UI

**Navegación:** ✅ Navbar consistente con Bootstrap 5. Los badges de mensajes no leídos y tareas pendientes en el menú son muy útiles para un CRM.

**Formularios:**
- ⚠️ Sin validación en tiempo real (client-side). Los errores aparecen solo después de submit.
- ⚠️ El formulario de lead tiene todos los campos en una sola página sin agrupación visual por secciones (datos personales / datos comerciales / CRM). Con 14 campos es visualmente denso.

**Feedback visual:**
- ✅ Django messages para confirmaciones (success, error)
- ⚠️ Los botones de formulario no tienen estado de loading — el usuario puede hacer doble-clic y duplicar envíos
- ⚠️ El Kanban no muestra feedback visual mientras mueve una tarjeta — solo después de la respuesta AJAX

**Información visible sin scroll:**
- ✅ Dashboard muestra KPIs en cards superiores
- ⚠️ El detalle de un lead tiene tabs (Campos, Historial, Tareas, etc.) pero el tab activo no se persiste en la URL — si recargás la página, siempre volvés al primer tab

**Responsive / Mobile:**
- ✅ Bootstrap 5 con breakpoints `col-md-*`. Las tablas tienen `table-responsive`.
- ⚠️ El Kanban (`lead_kanban.html`) probablemente no sea usable en móvil — columnas side-by-side no colapsan bien en pantallas chicas
- ⚠️ La pantalla de conversación WhatsApp con scroll de mensajes puede ser confusa en mobile

**Accesibilidad:**
- ⚠️ Los botones de icono (`<a href="..."><i class="bi bi-eye"></i></a>`) no tienen `aria-label` descriptivo en todos los casos
- ⚠️ El badge `bg-secondary` sobre fondo blanco puede tener bajo contraste (WCAG AA)

**Estados vacíos:** ✅ La mayoría de las tablas tienen un `{% empty %}` con mensaje e ícono.

**Consistencia visual:** ✅ Bootstrap 5 como base garantiza consistencia. Los badges de estado tienen colores semánticos bien mapeados.

> **Resumen:** UI funcional y consistente. Los gaps más notorios son la falta de validación client-side, estados de loading en acciones, y la usabilidad del Kanban en mobile.

---

## 7. 👤 PERSPECTIVA DE USUARIO FINAL

Usando este CRM como agente comercial de obra social día a día:

**✅ Lo que funciona bien:**
- El pipeline Kanban es intuitivo para ver en qué estado está cada lead
- Las tareas con fecha programada y badge en el menú evitan que se olviden seguimientos
- El inbox de WhatsApp integrado es una feature diferenciadora real
- Los campos personalizados permiten adaptar el CRM a distintos tipos de datos

**🔴 Flujos engorrosos:**

1. **Convertir un lead a cliente borra el historial de tareas y cotizaciones.** Si trabajé semanas con ese lead y cotizé 3 veces, al convertirlo a cliente pierdo todo el registro. Las tareas solo están relacionadas con `Lead` — cuando el lead se convierte y se borra, las tareas desaparecen en cascada.

2. **No puedo registrar que hice una llamada.** Hay tipos de tarea (llamada, reunión), pero no hay un log rápido de "llamé hoy, atendió, dije X". La agenda obliga a crear una tarea previamente — no puedo logear una interacción espontánea.

3. **No puedo enviar email desde el CRM.** Tengo WhatsApp pero si el lead prefiere email, debo salir al cliente de correo y volver.

4. **No puedo ver el historial completo de un lead de un vistazo.** El historial de estados está en un tab, las tareas en otro, los mensajes WhatsApp en otro, las cotizaciones en otro. No hay un timeline unificado de "todo lo que pasó con este contacto".

5. **El dashboard no muestra tendencias.** Veo el número de leads por estado hoy, pero no si estoy mejorando semana a semana. No hay gráficos de evolución temporal.

**🔴 Datos que no puedo registrar fácilmente:**
- Resultado de una llamada (no hay campo de resultado rápido en tarea completada)
- Fuente específica dentro de "web" (¿qué formulario? ¿qué landing page?)
- Documentación adjunta (no hay upload de archivos por lead, solo en cotizaciones)
- Motivo de pérdida cuando un lead pasa a "Perdido"

**⚠️ Reportes que necesitaría:**
- Tasa de conversión Lead → Cliente por agente y por período
- Tiempo promedio de conversión (cuántos días tarda un lead en afiliarse)
- Leads nuevos vs afiliados por semana/mes (gráfico de tendencia)
- Rendimiento de campañas (cuántos leads vinieron de cada campaña, cuántos se afiliaron)

> **Resumen:** El CRM tiene las piezas fundamentales pero falta "pegamento" entre ellas. La conversión que elimina historial, la ausencia de timeline unificado y la falta de registro rápido de interacciones son los pain points más frustrantes para uso diario.

---

## 8. 📦 FUNCIONALIDADES FALTANTES (por impacto)

| Prioridad | Feature | Impacto |
|-----------|---------|---------|
| 🔴 Alta | **Timeline unificado** por contacto (llamadas, mensajes, estado, notas en cronología) | Visibilidad del historial completo |
| 🔴 Alta | **Tareas vinculadas a Clientes** (actualmente solo a Leads) | Seguimiento post-conversión |
| 🔴 Alta | **Motivo de pérdida** en estado "Perdido" (campo obligatorio) | Análisis de por qué se pierden leads |
| 🔴 Alta | **Adjuntos/documentos** por lead (DNI, contrato, autorización) | Obra social necesita documentación |
| ⚠️ Media | **Gráficos de tendencia** en dashboard (Chart.js o similar) | Visibilidad gerencial |
| ⚠️ Media | **Log rápido de interacción** (botón "Registrar llamada/nota" desde el detalle) | Velocidad de carga de trabajo |
| ⚠️ Media | **Filtros guardados / vistas personalizadas** en lista de leads | Eficiencia diaria |
| ⚠️ Media | **Notificaciones push/email** cuando se asigna un lead o vence una tarea | No perder seguimientos |
| ⚠️ Media | **Búsqueda global** (atajo de teclado, busca en leads+clientes+tareas) | Velocidad de navegación |
| 💡 Baja | **Integración con Google Calendar** para sincronizar tareas | Evitar doble carga |
| 💡 Baja | **Importación de clientes** (además de leads) | Migración de datos existentes |
| 💡 Baja | **Cotizaciones vinculadas a Clientes** (actualmente solo a Leads) | Coherencia del modelo |

---

## 9. 🗄️ BASE DE DATOS Y MODELO DE DATOS

**Esquema general:** ✅ Bien normalizado. FKs correctas, uso apropiado de `SET_NULL` para relaciones opcionales.

**Índices presentes:** ✅ `db_index=True` en `Lead.dni`, `Lead.telefono`, `Lead.estado`, `ApiKey.key`, `ApiKey.activa`, `ReglaAutomatizacion.activa`.

**🔴 Índices faltantes:**
- `Conversacion.telefono` — se busca por teléfono en cada mensaje entrante de WhatsApp (`get_or_create(telefono=...)`). Sin índice, con 10k conversaciones cada webhook hace un full table scan.
- `Mensaje.conversacion_id` + `Mensaje.timestamp` — las queries de polling de mensajes nuevos necesitan este índice compuesto.
- `AutomatizacionLog.lead_id` — se consulta para ver si una regla ya se aplicó a un lead.

**Relaciones problemáticas:**

🔴 **`Tarea.lead` es FK no-nullable con `on_delete=CASCADE`** — Cuando un Lead se convierte a Cliente y se borra, las tareas pendientes **se borran en cascada** (`apps/tasks/models.py`). Un agente puede tener tareas programadas para los próximos días y desaparecen sin aviso.

⚠️ **`Conversacion.lead` es `SET_NULL`** — La conversación de WhatsApp sobrevive a la conversión (correcto), pero queda huérfana sin vínculo al nuevo Cliente. No hay `conversacion.cliente_id`.

⚠️ **`CampoPersonalizado` + `datos_extra: JSONField`** — Si se cambia el slug de un campo personalizado, todos los valores guardados en `datos_extra` con la clave vieja quedan huérfanos silenciosamente.

**Migraciones:**
- 🔴 No hay migración commiteada para `CampoPersonalizado` (modelo en `leads/models.py`)
- 🔴 No hay migración commiteada para `Cliente` (app `clientes/` solo tiene `migrations/__init__.py`)
- El sistema depende de `makemigrations` en runtime para generarlas — esto no es reproducible ni seguro

**Normalización:**
- ✅ `Plan` es entidad separada (no string libre)
- ⚠️ `Lead.localidad` y `Lead.provincia` son `CharField` libres — con el tiempo habrá "Buenos Aires", "Bs As", "bs.as." sin forma de agrupar correctamente

> **Resumen:** El esquema es sólido pero tiene tres problemas críticos: la falta de migraciones commiteadas, la pérdida en cascada de tareas al eliminar leads, y los índices faltantes en `Conversacion.telefono` que afectan directamente al webhook de WhatsApp.

---

## 10. 📋 RESUMEN EJECUTIVO Y PRIORIDADES

### Nivel de madurez: **6.5 / 10**

Las funcionalidades core están implementadas y funcionando (pipeline, WhatsApp, tareas, automatizaciones, campañas, cotizaciones, API externa). El código es limpio y la arquitectura es apropiada. Lo que baja el puntaje son: las migraciones sin commitear, la ausencia de monitoreo, la pérdida de datos en conversión Lead→Cliente, y la cobertura de tests del ~15%.

---

### 🔴 Top 5 Problemas Críticos (resolver ya)

| # | Problema | Ubicación |
|---|----------|-----------|
| 1 | **Migraciones sin commitear** — el sistema en producción genera migraciones en runtime | `apps/leads/migrations/`, `apps/clientes/migrations/` |
| 2 | **Tareas se borran en cascada** al eliminar un Lead en la conversión | `apps/tasks/models.py` — `lead FK on_delete=CASCADE` |
| 3 | **ContactListView carga todo en memoria** — no escala | `apps/leads/views.py` — `ContactListView` |
| 4 | **`gunicorn --reload` en producción** | `docker-compose.yml` línea 53 |
| 5 | **Sin índice en `Conversacion.telefono`** — full scan en cada webhook | `apps/whatsapp/models.py` |

---

### ⚠️ Top 5 Mejoras de Alto Impacto (para el usuario)

| # | Mejora |
|---|--------|
| 1 | **Timeline unificado** por lead/cliente (historial + tareas + mensajes + notas en una vista) |
| 2 | **Tareas vinculadas a Clientes** (no solo a Leads) |
| 3 | **Motivo de pérdida** como campo obligatorio al marcar estado "Perdido" |
| 4 | **Gráficos de tendencia** en dashboard (leads nuevos/afiliados por semana) |
| 5 | **Adjuntos por lead** (documentación, contrato, foto de DNI) |

---

### 🗺️ Roadmap sugerido

**Fase 1 — Estabilización (1-2 semanas)**
- Commitear migraciones de `CampoPersonalizado` y `Cliente`
- Cambiar `Tarea.lead` a nullable con `on_delete=SET_NULL`
- Mantener tareas al convertir Lead→Cliente (reasignar al cliente o marcar como huérfanas)
- Quitar `--reload` de gunicorn en producción
- Mover `makemigrations` fuera del startup (solo `migrate`)
- Agregar índice en `Conversacion.telefono`
- Fix de `dict_key` para devolver `''` en vez de `0`
- Configurar Sentry (o similar) para errores en producción

**Fase 2 — Crecimiento (1-2 meses)**
- Timeline unificado por contacto
- Tareas vinculadas a Clientes
- Motivo de pérdida en estado "Perdido"
- Paginación real en ContactListView (via queryset, no lista Python)
- Adjuntos/documentos por lead
- Gráficos de tendencia en dashboard (Chart.js)
- Rate limiting en endpoints públicos
- Tests para `integrations`, `automations`, `clientes`

**Fase 3 — Escala (3-6 meses)**
- Separar PostgreSQL a servicio gestionado externo
- CI/CD (GitHub Actions con tests automáticos + deploy)
- Notificaciones push o email para tareas vencidas
- Búsqueda global con pg_trgm o Elasticsearch
- Exportación de reportes a Excel/PDF
- Integración con Google Calendar
- PWA / mejoras mobile

---

### ⚠️ Riesgos principales en producción tal como está

1. **Pérdida silenciosa de datos**: convertir un lead borra sus tareas. Un agente no se va a enterar hasta que las busque.
2. **Deploy frágil**: si `makemigrations` falla al arrancar (por conflicto o error de modelo), el contenedor no levanta y el sistema está caído.
3. **Sin alertas de errores**: los 500 solo se ven revisando `docker compose logs` manualmente. Un error puede estar ocurriendo horas sin que nadie lo sepa.
4. **Sin backups configurados**: una sola instancia de PostgreSQL sin backup automatizado. Un fallo de disco = pérdida total de datos.
5. **WhatsApp webhook sin validación de firma**: cualquiera que conozca la URL puede inyectar mensajes falsos en el sistema.
