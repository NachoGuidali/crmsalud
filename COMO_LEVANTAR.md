# Cómo levantar el CRM Obra Social en local

## Requisitos previos

- Docker 29.x instalado y corriendo (`docker --version` para verificar)
- Docker Compose v2 plugin instalado (`docker compose version` para verificar)
- WSL2 (Ubuntu) en Windows, o Linux nativo

### Si `docker compose` no funciona (plugin no instalado)

El repo de Ubuntu no incluye el plugin. Descargalo directo de GitHub:

```bash
# Crear carpeta de plugins de Docker CLI
mkdir -p ~/.docker/cli-plugins

# Descargar el binario de Compose v2
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o ~/.docker/cli-plugins/docker-compose

# Darle permisos de ejecución
chmod +x ~/.docker/cli-plugins/docker-compose

# Verificar
docker compose version
# Debe mostrar: Docker Compose version v2.x.x
```

---

## Paso 1 — Clonar / ubicarse en la carpeta del proyecto

```bash
cd ~/crmsupreg
```

La estructura debe verse así:
```
crmsupreg/
├── docker-compose.yml
├── .env
└── crm_obra_social/
    ├── Dockerfile
    ├── manage.py
    ├── requirements.txt
    └── apps/
```

---

## Paso 2 — Verificar el archivo `.env`

El archivo `.env` ya existe en la raíz del proyecto. Para desarrollo local no hace falta cambiar nada.

```bash
cat .env
```

Las variables de WhatsApp (`WHATSAPP_ACCESS_TOKEN`, etc.) pueden quedar vacías para probar sin Meta.

---

## Paso 3 — Construir y levantar los contenedores

```bash
docker compose up --build
```

Esto hace automáticamente:
1. Construye la imagen Docker (instala dependencias, WeasyPrint, etc.)
2. Levanta PostgreSQL 15 y espera a que esté sano
3. Levanta Redis 7
4. Corre `makemigrations` + `migrate` (crea todas las tablas)
5. Corre `collectstatic`
6. Arranca Gunicorn en el puerto 8000
7. Arranca el worker Celery
8. Arranca Celery Beat (tareas programadas)

La primera vez tarda 2-5 minutos. Cuando veas esto, está listo:
```
web-1  | [INFO] Listening at: http://0.0.0.0:8000
```

---

## Paso 4 — Crear el superusuario

En otra terminal (sin cerrar la que tiene `docker compose up`):

```bash
docker compose exec web python manage.py createsuperuser
```

Completá los datos que pide:
- Username: `admin` (o el que quieras)
- Email: (puede quedar vacío)
- Password: mínimo 8 caracteres

---

## Paso 5 — Cargar los planes iniciales (opcional pero recomendado)

```bash
docker compose exec web python manage.py loaddata apps/leads/fixtures/planes_iniciales.json
```

Esto carga 5 planes de obra social de ejemplo (Individual, Familiar, Empresa PyME, Maternidad, Senior).

---

## Paso 6 — Acceder al sistema

Abrí el navegador en:

| URL | Descripción |
|-----|-------------|
| http://localhost:8000 | Dashboard principal |
| http://localhost:8000/admin/ | Admin de Django |
| http://localhost:8000/leads/ | Lista de leads |
| http://localhost:8000/leads/kanban/ | Vista Kanban |
| http://localhost:8000/whatsapp/inbox/ | Bandeja WhatsApp |
| http://localhost:8000/tareas/agenda/ | Agenda de tareas |

Iniciá sesión con el usuario que creaste en el paso 4.

---

## Comandos útiles del día a día

### Apagar los contenedores
```bash
docker compose down
```

### Apagar y borrar la base de datos (reset total)
```bash
docker compose down -v
```

### Ver los logs en tiempo real
```bash
docker compose logs -f web        # logs del servidor Django
docker compose logs -f celery     # logs de Celery worker
docker compose logs -f celery-beat
```

### Abrir una consola Django dentro del contenedor
```bash
docker compose exec web python manage.py shell
```

### Correr los tests
```bash
docker compose exec web python manage.py test
```

### Reiniciar solo el servidor web (sin reconstruir)
```bash
docker compose restart web
```

---

## Flujo básico de uso del CRM

1. **Crear leads** → `/leads/nuevo/` — ingresá nombre, DNI, teléfono (+54...)
2. **Ver pipeline** → `/leads/kanban/` — arrastrá los leads entre columnas
3. **Asignar tareas** → desde el detalle del lead, botón "Tarea"
4. **Cotizaciones** → desde el detalle del lead, botón "Cotización" → genera PDF
5. **WhatsApp** → sin credenciales reales, el webhook no recibe mensajes, pero podés crear conversaciones manualmente desde el admin
6. **Campañas** → solo superadmin/supervisor, requiere plantillas HSM aprobadas

---

## Roles de usuario

| Rol | Permisos |
|-----|----------|
| `superadmin` | Todo: leads de todos, campañas, usuarios, reportes |
| `supervisor` | Ve todos los leads, reportes, campañas |
| `agente` | Solo ve y gestiona sus propios leads asignados |

Para cambiar el rol de un usuario: Admin → Users → seleccioná el usuario → campo "Role".

---

## Probar el webhook de WhatsApp sin Meta

Podés simular mensajes entrantes con curl:

```bash
curl -X POST http://localhost:8000/whatsapp/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "5491112345678",
            "id": "wamid.test123",
            "type": "text",
            "timestamp": "1700000000",
            "text": {"body": "Hola, quiero información"}
          }],
          "contacts": [{
            "wa_id": "5491112345678",
            "profile": {"name": "Juan Prueba"}
          }]
        }
      }]
    }]
  }'
```

Esto crea automáticamente un Lead y una Conversación. El mensaje aparece en `/whatsapp/inbox/`.

---

## Problemas frecuentes

### Error: "Cannot connect to the Docker daemon"
```bash
sudo service docker start   # En WSL2
# o
sudo systemctl start docker
```

### Error: "port 8000 already in use"
```bash
# Ver qué proceso usa el puerto
sudo lsof -i :8000
# Cambiar el puerto en docker-compose.yml: "8001:8000"
```

### Las migraciones fallan por dependencia circular
```bash
docker compose exec web python manage.py makemigrations --noinput
docker compose exec web python manage.py migrate --noinput
```

### Quiero borrar todo y empezar desde cero
```bash
docker compose down -v          # Borra contenedores y volúmenes
docker compose up --build       # Reconstruye todo
```
