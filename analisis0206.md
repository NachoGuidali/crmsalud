# Análisis Experto del CRM — Tester + Arquitecto + Usuario
**Fecha:** 02/06/2026  
**Roles:** QA Engineer Senior · Arquitecto de Software · Ingeniero de Infraestructura · Diseñador de Producto / UX · Usuario Final

---

## 1. DEER — Revisión de requerimientos (Req 1 al 24)

### Req 1 — Modelo unificado de contactos con tipos
**[CRÍTICO]** La implementación actual usa modelos **separados** (`Lead` y `Cliente` como tablas distintas). El DEER especifica un único modelo `Contacto` con `tipo` como atributo. Esta es una contradicción arquitectónica fundamental — no un gap menor, sino un rediseño completo del modelo de datos.

**[CRÍTICO]** El tipo `Proveedor` no tiene campos, vistas ni flujos definidos en ninguna parte del documento. Se menciona y desaparece.

**[IMPORTANTE]** "Relación flexible N-N" entre contacto y otros módulos — no hay esquema de tablas intermedias definido. ¿Un contacto puede estar vinculado a 3 leads distintos? ¿A un lead Y un deal simultáneamente?

**Complejidad real:** Alta-Crítica. La marcada como "media" subestima la migración de datos existentes, el rediseño de todas las vistas, y la reescritura de la lógica de permisos.

---

### Req 2 — Usuarios con roles y permisos
**[IMPORTANTE]** "Permisos granulares por módulo y acción" — no hay tabla de permisos. ¿Qué acciones? ¿Ver? ¿Editar? ¿Eliminar? ¿Exportar? ¿Por módulo (leads, deals, comisiones, whatsapp)?

**[IMPORTANTE]** El DEER dice que los usuarios son "un tipo de contacto con rol adicional". En el sistema actual son un modelo completamente separado (`AbstractUser`). Fusionarlos implica que un cliente podría tener cuenta de usuario. ¿Es eso intencional?

**Complejidad real:** Alta. Permisos granulares reales (no solo `can_see_all_leads`) requieren un sistema tipo `django-guardian` o una tabla de ACLs propia.

---

### Req 3 — Normalización de teléfonos (+549)
**[CRÍTICO]** La especificación dice "todos los números con prefijo +549". El `+549` es exclusivamente Argentina móvil. Esto es incorrecto para:
- Números fijos argentinos (`+5411...`)
- Números de otros países (`+5511...` Brasil, `+5719...` Colombia)
- Números de WhatsApp Business (pueden ser fijos)

La función actual `normalize_ar_phone()` hardcodea `+549` como prefijo universal, lo que corrompe cualquier número no-argentino. Si el negocio escala o tiene un solo cliente internacional, falla.

**[IMPORTANTE]** Condición de borde no contemplada: ¿qué pasa si el mismo número existe con y sin el `9` (`+5411...` vs `+54911...`)? Son el mismo número en Argentina pero el sistema los trataría como contactos distintos.

---

### Req 4 — Enlace de contactos a cualquier elemento
**[IMPORTANTE]** "Relación flexible N-N" — completamente indefinida en términos de modelo de datos. No hay especificación de tabla intermedia `ContactoElementoVinculo(contacto_id, elemento_tipo, elemento_id)`. ¿Cómo se ve esto en la UI? ¿Con qué rol/tipo puede vincularse?

**[IMPORTANTE]** "Ningún vínculo es obligatorio" contradice los flujos actuales donde un Lead necesita datos mínimos para existir. Si un Deal puede existir sin contacto, ¿cómo se activa una automatización que envíe un WhatsApp?

---

### Req 5 — Campos personalizados
**[IMPORTANTE]** El tipo `moneda` no está en el modelo actual `CampoPersonalizado` (que tiene: texto, numero, fecha, booleano, lista). Agregarlo no es trivial: requiere símbolo de moneda, formato de visualización, conversión de tipos en filtros.

**[IMPORTANTE]** "Aplicar a todas [las entidades]" — actualmente el alcance es `leads/clientes/ambos`. Los campos personalizados para Deals, Tareas, Comisiones no están contemplados en el modelo actual.

**[MEJORA]** Las condiciones de `CampoRegla` (visible/obligatorio según estado) están parcialmente implementadas pero no soportan "obligatorio al llegar a etapa X" como gatillo de validación en el formulario.

---

### Req 6 — Constructor visual de reglas (no-code)
**[CRÍTICO]** No implementado. El sistema actual tiene `AutomatizacionRegla` con formulario básico de tiempo (N días sin actividad). El DEER pide un constructor tipo Bitrix24 con UI drag-and-drop, AND/OR, grupos de condiciones, múltiples acciones.

**[CRÍTICO]** Esto requiere: motor de evaluación de condiciones compilado en runtime, renderer de acciones extensible, UI builder (React/Vue/Drawflow adaptado), persistencia del árbol de reglas como JSON serializable + ejecutable.

---

### Req 7 — Triggers sobre cualquier campo
**[CRÍTICO]** "El sistema escucha cambios sobre cualquier campo de cualquier entidad" — con Django signals, el `post_save` se dispara pero **no sabe qué campo cambió**. Para saber qué campo específico cambió hay que guardar el estado previo en `pre_save` y comparar en `post_save`, o usar `django-model-utils FieldTracker`. Sin protección, hay riesgo real de **loops infinitos**.

**[CRÍTICO]** "El usuario selecciona el campo desde un desplegable completo" requiere un registro dinámico de todos los campos de todas las entidades (incluyendo campos personalizados creados en runtime). Esta introspección dinámica no existe.

---

### Req 8 — Condiciones evaluables
**[IMPORTANTE]** El ejemplo del documento usa "si edad = 21" — no hay campo `edad` en el modelo `Lead`. Hay `fecha_nacimiento`. Calcular edad en runtime dentro de una condición requiere lógica adicional.

**[IMPORTANTE]** "Campos del contacto vinculado" — si un Deal no tiene contacto obligatorio (Req 4), ¿qué pasa cuando la condición intenta evaluar un campo del contacto vinculado y no hay contacto?

**[MEJORA]** AND/OR con agrupación anidada requiere un árbol de expresiones, no un array plano de condiciones. El DEER no define la profundidad máxima de anidado.

---

### Req 9 — Movimiento entre embudos vía automatización
**[CRÍTICO]** "Leads → Deals" son entidades completamente distintas con campos distintos. Mover un Lead a un Deal implica:
- Crear un Deal con datos del Lead — ¿cuál es el mapeo de campos?
- ¿El Lead original se elimina? ¿Se archiva? ¿Queda en estado "ganado"?
- ¿Los campos específicos del Lead (DNI, grupo familiar) se pierden en el Deal?

El DEER no define el mapeo de campos entre entidades — prácticamente no implementable sin esa especificación.

**Complejidad real:** Crítica. La marcada como "alta" sigue siendo subestimada.

---

### Req 10 — Log de ejecuciones y modo test
**[CRÍTICO]** "Modo test: ejecutar sobre un elemento real sin efectos reales" — los side effects incluyen mensajes de WhatsApp enviados (irreversibles), webhooks a sistemas externos, comisiones calculadas, cambios de estado, emails enviados. Para un verdadero dry-run necesitarías rollback de DB + mocking de todas las llamadas externas.

**Complejidad real:** Alta. El documento dice "media" — incorrecto.

---

### Req 11 — Pipeline con etapas personalizadas
**[IMPORTANTE]** El DEER dice etapas fijas: "Nuevo", "Ganado", "Perdido". El sistema actual tiene 7 etapas hardcodeadas: nuevo, contactado, interesado, doc_pendiente, en_revision, afiliado, perdido. Contradicción directa — las etapas intermedias actuales deberían volverse configurables.

**[IMPORTANTE]** Si las etapas son completamente configurables, la lógica de badges de color, filtros del kanban y condiciones de automatización basadas en estado necesitan ser dinámicos, no hardcodeados.

---

### Req 12 — Vista Kanban y lista
**[IMPORTANTE]** "Preferencia de vista persistente por usuario" — no implementado. No hay `UserPreference` ni storage de estado por usuario.

**[MEJORA]** "Columnas configurables" en lista — no implementado. Las columnas son fijas en todos los listados actuales.

---

### Req 13 — Conversión automática Lead → Cliente
**[CRÍTICO]** "Dispara trigger de comisiones" — el módulo de comisiones no está implementado.

**[CRÍTICO]** La conversión actual no es atómica. Si el proceso falla a mitad (crea el `Cliente` pero falla al actualizar el estado del `Lead`), queda un estado inconsistente sin mecanismo de rollback.

**[IMPORTANTE]** ¿Puede un Lead convertirse a Cliente dos veces? No hay `unique_together` en `Cliente` que prevenga duplicados por el mismo `Lead.pk`. Con concurrencia (dos supervisores), podrían crearse dos `Cliente` del mismo Lead.

---

### Req 14 y 17 — Automatizaciones en pipeline de leads y deals
**[CRÍTICO]** Dependencia circular: ambos requerimientos dependen del "motor de automatizaciones" (Req 6-10) que aún no existe en su forma completa. No pueden implementarse antes que el motor.

---

### Req 15 — Múltiples embudos con etapas personalizadas
**[IMPORTANTE]** "Cada embudo tiene sus propias reglas de automatización independientes" — actualmente no hay FK de `AutomatizacionRegla` a `Pipeline`. Una regla creada para "Pipeline A" podría dispararse en "Pipeline B" si están en el mismo módulo.

---

### Req 18 — Configuración parametrizable de comisiones
**[CRÍTICO]** Completamente no implementado. Ambigüedades:
- ¿Qué pasa si ninguna regla hace match? ¿Comisión = 0? ¿Error?
- "Campo de valor seleccionable" — ¿en qué modelo vive el valor? ¿`Lead`? ¿`Deal`? ¿Campo personalizado?
- Si el Lead se revierte de Ganado a Perdido después del cálculo de comisión, ¿la comisión se anula automáticamente?

---

### Req 19 y 20 — Vista y estado de comisiones
**[FALTANTE]** Módulo completo ausente. Sin modelo de datos, sin vistas, sin lógica.

---

### Req 21 — Editor visual de chatbot con condiciones sobre campos
**[IMPORTANTE]** El editor Drawflow existe pero los nodos de condición no pueden acceder a los datos reales del CRM. La evaluación "en tiempo real contra datos actuales del contacto" requiere consultas a la base de datos durante la ejecución del flujo — no implementado.

**[IMPORTANTE]** Los flujos en Drawflow se guardan como JSON estático. No hay motor de ejecución de flujos que procese ese JSON paso a paso durante una conversación.

---

### Req 22 — Variables de respuesta en el flujo
**[CRÍTICO]** "La respuesta se guarda como variable nombrada y puede escribirse en un campo del contacto" — no existe en el editor Drawflow actual. No hay nodo de "Pregunta" que capture la respuesta y la asigne a `lead.email` por ejemplo.

**[IMPORTANTE]** ¿Dónde viven las variables durante la ejecución del flujo? ¿En Redis con TTL? ¿En `datos_extra` del lead? ¿En memoria del worker? No especificado.

---

### Req 23 — n8n, actualizar contacto sin duplicar
**[IMPLEMENTADO ✅]** Cubierto con los endpoints `/api/v1/leads/buscar/`, `/api/v1/leads/actualizar/`, y la lógica upsert en `/api/v1/leads/`. Complejidad "baja" es acertada.

---

### Req 24 — Control de bot por conversación
**[IMPLEMENTADO ✅]** `Conversacion.bot_crm_activo` y `bot_n8n_activo` implementados. Toggle en inbox y en vista de conversación. Complejidad "baja" es acertada.

---

## 2. Análisis de arquitectura y diseño

### Modelo "todo es Contacto"
**[CRÍTICO]** El enfoque del DEER (modelo unificado) y el enfoque actual (modelos separados `Lead`/`Cliente`) son arquitecturas fundamentalmente distintas.

**Modelo unificado (DEER):**
- ✅ Una sola búsqueda para encontrar cualquier contacto
- ✅ Historial unificado (un contacto puede pasar de Lead a Cliente sin crear nuevo registro)
- ❌ Queries más complejas con filtros por tipo
- ❌ Un campo `tipo` como string no garantiza integridad de los campos específicos de cada tipo
- ❌ Permisos más complejos

**Modelos separados (actual):**
- ✅ Cada modelo tiene sus campos propios con tipos correctos
- ✅ Queries simples y performantes
- ❌ "Contacto" puede existir en dos tablas simultáneamente
- ❌ No hay vista unificada real

**Recomendación:** Dado el estado actual y la complejidad de migrar, pragmáticamente conviene mantener la separación y agregar una API/vista unificada (`/contactos/` ya existe) en lugar de rediseñar el modelo de datos completo.

---

### Motor de automatizaciones — Riesgo de loops infinitos
**[CRÍTICO]** Con Django signals event-driven:

```
Lead se guarda → post_save signal → evalúa regla "al cambiar estado"
→ acción "actualizar campo" → Lead.save() → post_save signal → evalúa regla
→ acción "actualizar campo" → Lead.save() → ... (loop infinito)
```

**Mitigaciones necesarias:**
1. Flag thread-local: `_automation_in_progress = True` antes de ejecutar, verificar antes de disparar el signal
2. Tracking: `(regla_id, elemento_id, campo, valor_nuevo)` para detectar ciclos
3. Profundidad máxima de cadena (hardcoded, ej: máx 10 acciones)

---

### Integridad referencial al eliminar entidades

| Entidad eliminada | Impacto |
|---|---|
| `Lead` | `HistorialEstado` CASCADE ✅ · `Documento` CASCADE (archivo en disco **NO** eliminado ❌) · `Conversacion.lead` SET_NULL (conversación queda huérfana) |
| `User` (agente) | `Lead.agente` SET_NULL · `Deal.agente` SET_NULL · conversación queda sin responsable |
| `PipelineStage` | `Deal` PROTECT — correcto |

**[IMPORTANTE]** Los archivos de documentos (`Documento.archivo`) no se eliminan del filesystem cuando se elimina el modelo — acumulación de archivos huérfanos en `media/documentos/`.

---

### Módulo de comisiones — Integridad de datos
**[CRÍTICO]** Tres escenarios no contemplados en el DEER:

1. **Lead revertido:** Lead marcado como Ganado → comisión calculada → Lead vuelve a "En revisión". ¿La comisión se anula automáticamente?
2. **Valor editado post-conversión:** Si el campo base de la comisión se edita después del cálculo, ¿se recalcula? ¿Se notifica al admin?
3. **Reasignación del vendedor:** Si se cambia el agente del lead antes de la conversión, ¿quién recibe la comisión?

---

### Aislamiento de automatizaciones entre embudos
**[IMPORTANTE]** Actualmente `AutomatizacionRegla` no tiene FK a `Pipeline`. Una regla definida para "Etapa 2 del Pipeline A" podría dispararse en "Etapa 2 del Pipeline B" si tienen el mismo nombre de etapa. El scope de la regla debe ser `(pipeline_id, stage_id)` no solo `stage_id`.

---

## 3. Análisis de infraestructura y resiliencia

### Evolution API — Pérdida de conexión
**[CRÍTICO]** Si Evolution API se desconecta:
- **Mensajes entrantes:** Evolution deja de hacer webhooks → mensajes no llegan al CRM → **pérdida de datos permanente**. No hay reconciliación posterior.
- **Mensajes salientes:** `send_text_message()` lanza excepción → Celery retry (3 intentos) → si fallan todos, el mensaje se pierde silenciosamente.
- **Sesión de WhatsApp:** La sesión QR puede expirar. No hay health check periódico que detecte `connectionState = close` y alerte.
- **No hay queue de mensajes pendientes.** Si el agente envía mensajes mientras Evolution está caído, ninguno se envía ni se reintenta.

**Mitigación recomendada:** Health check cada 60s · Alerta visible en UI cuando `state != 'open'` · Queue Redis para mensajes salientes pendientes.

---

### Race condition en creación de leads vía webhook
**[CRÍTICO]** El código actual para evitar duplicados:

```python
existing = Lead.objects.filter(telefono=phone).first()
if existing:
    # update
else:
    Lead.objects.create(...)  # ← ventana de race condition aquí
```

Este patrón **no es atómico**. Entre el `filter` y el `create`, un segundo request concurrente puede insertar el mismo teléfono. Resultado: dos Leads con el mismo número.

**Fix:** `Lead.objects.get_or_create(telefono=phone, defaults={...})` que es atómico, o `unique_constraint` en `telefono` + manejo de `IntegrityError`.

---

### Webhooks entrantes sin rate limiting
**[IMPORTANTE]** Los endpoints `/api/v1/leads/`, `/api/v1/webhook/<source>/` y `/api/v1/leads/actualizar/` no tienen rate limiting. Un n8n mal configurado puede saturar los 2 workers de Gunicorn, llenar la tabla `WebhookLog`, y causar timeouts para todos los demás usuarios.

**Fix:** `django-ratelimit` o rate limiting a nivel de nginx/reverse proxy.

---

### Automatizaciones diferidas — Persistencia
**[IMPORTANTE]** Las acciones diferidas (N horas) van como tareas Celery con `eta`. Si el worker se reinicia, las tareas en memoria se pierden.

El `docker-compose.yml` usa Redis con `allkeys-lru` (eviction). Si Redis queda sin memoria, **puede eliminar tareas pendientes** para liberar espacio. Esto es incompatible con tareas diferidas críticas como "enviar WhatsApp en 2 horas".

**Fix:** Redis configurado con `maxmemory-policy noeviction` para la queue de Celery, o usar PostgreSQL como broker/backend.

---

### Concurrencia — Doble conversión Lead → Cliente
**[CRÍTICO]** Dos supervisores pueden ver el mismo lead simultáneamente y ambos hacer click en "Convertir a Cliente" antes de que la primera conversión se complete. No hay:
- `select_for_update()` en el Lead antes de convertir
- Check de "ya existe un Cliente con este lead.pk"
- Transacción atómica que falle si el Cliente ya existe

Resultado potencial: dos registros `Cliente` vinculados al mismo `Lead`, con posiblemente dos comisiones calculadas.

---

### Normalización de teléfonos en Evolution API
**[IMPORTANTE]** Evolution API envía el número en formato `5491112345678@s.whatsapp.net`. El código extrae `5491112345678` y le agrega `+`. Si el número es un fijo argentino sin el `9` (`541112345678`), el lookup falla y se crea un contacto duplicado.

---

## 4. Análisis del Motor de Automatizaciones

### Triggers simultáneos sobre el mismo elemento
**[CRÍTICO]** Escenario: agente guarda un Lead cambiando el estado Y completando un campo vacío. Django llama a `post_save` una vez pero el handler evalúa TODAS las reglas activas:

- Regla A: "al completarse email → asignar agente X"
- Regla B: "al cambiar estado a interesado → asignar agente Y"

Ambas se ejecutan. La última "gana". Sin logging granular, es imposible saber por qué el agente cambió.

**Mitigación:** Prioridad por regla + política "primera regla gana" documentada y configurable.

---

### Loops — Análisis técnico
**[CRÍTICO]** El stack actual: Django signals → Celery task → `Lead.save()` → Django signal.

El loop se forma porque `Lead.save()` dentro de una Celery task dispara el signal igualmente. Opciones técnicas:
1. `threading.local()` para marcar que estamos en una automation chain
2. Debounce por elemento: no disparar la misma regla para el mismo elemento dentro de X segundos
3. Versión del elemento: guardar `version` en el log y no re-disparar si `version` no cambió

---

### Modo test — Análisis de complejidad
**[IMPORTANTE]** Para implementar "dry run real" sin efectos:

```
Acción: enviar WhatsApp  → mock de send_text_message()       (no reversible realmente)
Acción: ejecutar webhook → mock de requests.post()           (no reversible realmente)
Acción: cambiar estado   → transaction con ROLLBACK          (factible)
Acción: calcular comisión→ transaction con ROLLBACK          (factible)
```

Una transacción con `ROLLBACK` al final cubre los cambios en DB. Pero los calls a Evolution API y webhooks externos **no se pueden revertir**. La única implementación honesta del "modo test" para WhatsApp es no llamar a la API y mostrar "hubiera enviado: `<contenido>`".

---

### Acciones encadenadas con elemento eliminado entre medio
**[IMPORTANTE]** Cadena: acción A (inmediata) → acción B (+2h) → acción C (+1día).

Acción A se ejecuta. Lead se elimina. 2 horas después la tarea Celery para B se dispara y lanza `DoesNotExist`.

**Fix:** Al eliminar un Lead, hacer `revoke()` de todas las tareas Celery pendientes para ese `lead_id`. Requiere almacenar los `task_id` de las tareas programadas.

---

### Frecuencia "una vez por elemento"
**[IMPORTANTE]** Requiere una tabla: `(regla_id, elemento_tipo, elemento_id)` con unique constraint. Si Celery ejecuta la misma tarea dos veces (retry), puede registrarse dos ejecuciones y enviarse dos mensajes al mismo contacto.

---

## 5. Análisis de la integración WhatsApp + Inbox

### Asignación automática de conversaciones
**[FALTANTE]** Actualmente todas las conversaciones nuevas quedan `agente=NULL`. No hay round-robin, asignación por carga, ni regla configurable por horario. Un supervisor tiene que asignar manualmente cada conversación nueva.

---

### Un contacto, dos números de WhatsApp
**[IMPORTANTE]** Si la misma persona escribe desde un número nuevo, el sistema crea una `Conversacion` separada y potencialmente un `Lead` nuevo. No hay UI para fusionar conversaciones, ni capacidad de asociar dos números al mismo lead.

---

### Diferenciación bot vs humano en historial
**[MEJORA]** Actualmente `Mensaje.enviado_por` es `NULL` para mensajes del bot y para mensajes entrantes. No hay distinción visual entre "el bot respondió esto" y "el agente respondió esto" en el historial del chat. Los supervisores no pueden auditar si el bot respondió correctamente.

---

### Media en el timeline
**[IMPORTANTE]** `Mensaje.media_url` almacena la URL tal como la entrega Evolution API. Dependiendo de la configuración, estas URLs pueden ser temporales (expiración de minutos). Si son temporales, los mensajes de imagen/audio en el historial mostrarán broken links después de poco tiempo. No hay mecanismo de descarga y almacenamiento local de archivos recibidos.

---

### Error en envío desde automatización
**[IMPORTANTE]** Flujo actual cuando Evolution API falla:
1. `send_whatsapp_message_task` intenta 3 veces (Celery retry)
2. Los 3 fallan → tarea queda en `FAILURE`
3. El agente **no recibe notificación**
4. El mensaje **nunca se entregó**

No hay mecanismo de alertas para "estas automatizaciones fallaron en las últimas X horas".

---

## 6. Gaps y funcionalidades faltantes

### [FALTANTE] Búsqueda global
No hay búsqueda que cruce todos los módulos. Si el supervisor quiere encontrar a "María García" no sabe si está en Leads, Clientes o Contactos. Debe buscar en cada módulo por separado.

### [FALTANTE] Notificaciones en tiempo real para agentes
- Nuevo lead asignado → sin notificación
- Mensaje de WhatsApp entrante → solo visible si el agente está en `/whatsapp/inbox/`
- Tarea vencida → badge en navbar, solo se actualiza al navegar
- Automatización fallida → invisible para el agente

Sin WebSockets o SSE, el sistema es reactivo solo para quien está mirando la pantalla correcta en ese momento.

### [FALTANTE] Módulo de comisiones completo
El módulo 5 es completamente ausente. Para una empresa comercial con vendedores y supervisores, esto es un gap de negocio directo. Los vendedores no tienen visibilidad de su rendimiento económico en el sistema.

### [FALTANTE] Auditoría completa
- `Lead`: solo cambios de estado (`HistorialEstado`). No hay log de "quién cambió el email", "quién cambió el agente", "quién editó las notas".
- `Cliente`: ningún audit trail.
- `Deal`: solo cambios de etapa. Sin historial de cambios de valor, agente, contacto.
- Usuarios: sin log de acciones (quién exportó datos, quién eliminó qué lead).

Para un negocio del rubro salud/obra social, la ausencia de auditoría puede ser un riesgo de compliance.

### [FALTANTE] Soft delete
`Lead.delete()` es un hard delete. Si un agente elimina un lead por error, no hay papelera de reciclaje ni mecanismo de recuperación (excepto backup de DB). Los documentos adjuntos quedan huérfanos en el filesystem.

### [FALTANTE] Motor de ejecución de flujos de chatbot
El editor Drawflow permite diseñar flujos visualmente pero no hay backend que los ejecute durante una conversación real. Los nodos de "Pregunta", "Condición", y "Actualizar atributo" son UX sin implementación.

### [FALTANTE] Multi-instancia WhatsApp
Una sola instancia de Evolution API (`crm-supreg`). Si el negocio tiene dos líneas (ventas y soporte), o si se usa como plataforma para múltiples cuentas, no hay soporte.

### [FALTANTE] Backup automático
El `docker-compose.yml` no tiene configuración de backup. La base de datos PostgreSQL en un volumen Docker sin backup es un riesgo crítico de pérdida total de datos ante falla del servidor.

### [MEJORA] API pública incompleta
Falta:
- Endpoints para Clientes (solo hay para Leads)
- Endpoint para crear/consultar Deals desde n8n
- Endpoint para marcar tareas como completadas
- Webhooks del CRM hacia sistemas externos (ej: "cuando se convierte un lead, notificar a ERP")

---

## 7. Riesgos críticos en producción

*Ordenados por Probabilidad × Impacto*

---

### Riesgo 1 — Sesión de WhatsApp caída sin detección
**Probabilidad:** Alta (las sesiones WhatsApp Web se desconectan regularmente — por timeout, por escaneo de QR en otro dispositivo, por ban temporal)

**Impacto:** Catastrófico — todos los mensajes entrantes se pierden silenciosamente. Los agentes no saben que no están recibiendo mensajes. El negocio no se entera hasta que un cliente llama a quejarse.

**Causa:** No hay health check activo contra `/instance/connectionState/`. La UI no refleja el estado de conexión de Evolution API en tiempo real.

**Mitigación:**
- Health check cada 60s con alerta visible en toda la UI (banner rojo "WhatsApp desconectado")
- Notificación push al supervisor cuando `state != 'open'`
- Auto-reconnect attempt si la instancia está configurada correctamente

---

### Riesgo 2 — Duplicación de leads por race condition
**Probabilidad:** Media (cualquier sistema que genere dos eventos simultáneos del mismo número — n8n + webhook de Evolution, o doble clic en formulario externo)

**Impacto:** Alto — leads duplicados corrompen métricas, pueden generar comisiones duplicadas, confunden a agentes, llevan a contactar al mismo cliente dos veces.

**Causa:** El patrón `filter().first()` + `create()` no es atómico. Hay una ventana de tiempo entre ambas operaciones.

**Mitigación:**
- `unique_together` en `Lead.telefono` (con manejo de `IntegrityError`)
- `get_or_create` en lugar de `filter` + `create`
- `select_for_update()` en el bloque de creación

---

### Riesgo 3 — Pérdida de mensajes por reinicio del worker Celery
**Probabilidad:** Media (deploys, reinicios programados, crashes por OOM)

**Impacto:** Alto — mensajes entrantes procesados por `process_incoming_message` se pierden si el worker muere durante el procesamiento.

**Causa:** Celery con `ACKS_LATE=False` (default) hace ACK del mensaje al recibirlo, no al completar. Si muere antes de completar, el mensaje se considera procesado y no se reintenta.

**Mitigación:**
- `task_acks_late = True` en configuración de Celery
- `task_reject_on_worker_lost = True`
- Idempotency key en webhook processing (guardar `whatsapp_message_id` y verificar antes de procesar)

---

### Riesgo 4 — Loop de automatizaciones al implementar el motor completo
**Probabilidad:** Alta (una vez implementado el motor event-driven, este escenario es casi inevitable en producción si no se previene)

**Impacto:** Crítico — CPU al 100%, Celery saturado, mensajes de WhatsApp enviados en loop al mismo contacto, potencial ban del número por spam.

**Causa:** `post_save` signal → ejecuta acción → `Lead.save()` → `post_save` signal → loop.

**Mitigación:**
- Thread-local flag `_automations_processing` verificado en signal handler
- Profundidad máxima de cadena (hardcoded, ej: 10)
- Rate limiting por (regla_id, elemento_id): máx 1 ejecución por N segundos

---

### Riesgo 5 — Conversión Lead→Cliente sin atomicidad
**Probabilidad:** Baja (requiere error del servidor exactamente a mitad de la conversión)

**Impacto:** Alto — estado inconsistente en DB: `Cliente` creado sin `Lead` actualizado, o `Lead` marcado como afiliado sin `Cliente` correspondiente. Difícil de detectar y corregir manualmente.

**Causa:** La vista de conversión realiza múltiples operaciones sin `transaction.atomic()` explícito.

**Mitigación:**
- Envolver todo el proceso de conversión en `with transaction.atomic():`
- Unique constraint: `Cliente.lead` debe ser único (un Lead no puede convertirse dos veces)
- Log de conversión con estado (iniciada, completada, fallida)

---

## 8. Evaluación del DEER como documento

### Fortalezas
- Cobertura de módulos amplia (6 módulos bien identificados)
- Catálogo exhaustivo de triggers y acciones
- Diferenciación "Base" vs "PROPIO" (útil para priorización)
- Indicadores de complejidad presentes (aunque varios son incorrectos)

### Debilidades críticas

**[CRÍTICO] Sin modelo de datos.** El documento describe comportamientos pero no hay un diagrama ER, no hay definición de tablas, no hay especificación de tipos de campos ni constraints. "Todo parte de Contacto" necesita un esquema concreto para implementarse.

**[CRÍTICO] Sin criterios de aceptación por requerimiento.** Cada requerimiento es una descripción narrativa sin definición de "qué se considera implementado". Un QA no puede escribir casos de prueba a partir de este documento.

**[CRÍTICO] Sin casos de uso end-to-end.** No hay un flujo completo como "agente recibe mensaje → lead creado → bot pregunta nombre → lead actualizado → automatización envía cotización → lead convierte → comisión calculada". Sin estos flujos, es imposible detectar dependencias entre módulos.

**[IMPORTANTE] Contradicción central no resuelta.** El Req 1 dice "todo parte de Contacto" (modelo unificado). El Módulo 4 dice "los deals no requieren contacto vinculado obligatoriamente". Estas dos afirmaciones son arquitectónicamente incompatibles.

**[IMPORTANTE] Dependencias entre módulos no declaradas.** El Módulo 5 (Comisiones) depende del Módulo 2 (Motor de Automatizaciones) que depende del Módulo 1 (modelo unificado). Esta cadena no está documentada. Sin ella, un equipo podría implementar Comisiones antes que el Motor y tener que reescribir todo.

**[IMPORTANTE] Complejidades incorrectas:**

| Requerimiento | Marcada | Real |
|---|---|---|
| Req 1 — Modelo unificado | Media | **Crítica** |
| Req 2 — Permisos granulares | Media | **Alta** |
| Req 9 — Mover entre embudos | Alta | **Crítica** |
| Req 10 — Modo test | Media | **Alta** |

**[IMPORTANTE] Sin SLAs ni escala.** ¿Cuántos contactos? ¿Cuántos mensajes/día? ¿Cuántos agentes concurrentes? ¿Tiempo de respuesta máximo? Sin estos números, es imposible dimensionar la infraestructura.

**[MEJORA] Sin priorización / MVP.** Todo aparece al mismo nivel de importancia. No hay una sección "qué entra en la primera versión" vs "qué es v2".

**[MEJORA] Los requerimientos no son testeables.** "El sistema escucha cambios sobre cualquier campo" no define qué campos, con qué latencia, en qué condiciones. Un QA no puede escribir un test automatizado para eso.

---

## Resumen ejecutivo — Top 10 hallazgos por severidad

| # | Severidad | Hallazgo |
|---|---|---|
| 1 | 🔴 **Crítico** | La sesión de WhatsApp (Evolution API) puede caerse silenciosamente sin que nadie lo note — pérdida permanente de mensajes entrantes sin alerta ni reconciliación |
| 2 | 🔴 **Crítico** | Race condition en creación de leads: dos eventos simultáneos del mismo número crean dos leads. No hay unicidad atómica en el código |
| 3 | 🔴 **Crítico** | El motor de automatizaciones del DEER (visual, event-driven, por campo) no existe. El módulo actual es una versión básica de tiempo. Todo el Módulo 2 está pendiente |
| 4 | 🔴 **Crítico** | El módulo de comisiones (Módulo 5) no está implementado. Gap de negocio directo para el equipo comercial |
| 5 | 🔴 **Crítico** | El editor de chatbot visual (Drawflow) no tiene backend de ejecución. Los flujos diseñados no se ejecutan durante conversaciones reales |
| 6 | 🟠 **Importante** | La conversión Lead→Cliente no está envuelta en `transaction.atomic()` — riesgo de estado inconsistente ante falla de servidor |
| 7 | 🟠 **Importante** | No hay auditoría de cambios de campos en Lead/Cliente/Deal. Solo se registran cambios de estado. Un cambio de email, agente o valor pasa sin traza |
| 8 | 🟠 **Importante** | La normalización a `+549` rompe números internacionales y números fijos argentinos. Cualquier contacto no-AR-móvil falla |
| 9 | 🟠 **Importante** | Sin backup automatizado de PostgreSQL configurado en docker-compose. Pérdida total de datos ante falla del volumen |
| 10 | 🟡 **Mejora** | El DEER carece de modelo de datos, criterios de aceptación y casos de uso end-to-end — varios requerimientos son prácticamente no implementables sin especificación adicional |
