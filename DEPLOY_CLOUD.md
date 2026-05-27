# Deploy en Cloud — Linux Server

## Requisitos del servidor

- Ubuntu 22.04 LTS o Debian 12 (recomendado)
- 2 vCPU / 4 GB RAM mínimo (recomendado 4 vCPU / 8 GB para producción)
- Docker 24+ y Docker Compose v2 plugin
- Puerto 80 y 443 abiertos en el firewall
- Dominio apuntando al servidor (ej: `crm.tuempresa.com`)

---

## Paso 1 — Instalar Docker en el servidor

```bash
# Actualizar paquetes
sudo apt-get update && sudo apt-get upgrade -y

# Instalar dependencias
sudo apt-get install -y ca-certificates curl gnupg

# Agregar clave GPG de Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Agregar repositorio
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Instalar Docker + Compose plugin
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Agregar tu usuario al grupo docker (para no usar sudo)
sudo usermod -aG docker $USER
newgrp docker

# Verificar
docker --version
docker compose version
```

---

## Paso 2 — Subir el código al servidor

**Opción A — desde tu máquina local (scp/rsync):**
```bash
# Desde tu máquina local WSL
rsync -avz --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
  ~/crmsupreg/ usuario@IP_DEL_SERVIDOR:/opt/crmsupreg/
```

**Opción B — con Git (recomendado para producción):**
```bash
# En el servidor
git clone https://github.com/tu-usuario/crmsupreg.git /opt/crmsupreg
cd /opt/crmsupreg
```

---

## Paso 3 — Configurar el archivo `.env` de producción

```bash
cd /opt/crmsupreg
cp .env .env.backup  # Backup del .env de desarrollo

# Editar el .env para producción
nano .env
```

Cambiar/completar los siguientes valores:

```env
# ─── Django ───────────────────────────────────────────────
DJANGO_SECRET_KEY=genera-una-clave-larga-y-aleatoria-aqui-minimo-50-chars
DJANGO_DEBUG=False
ALLOWED_HOSTS=crm.tuempresa.com www.crm.tuempresa.com

# ─── Base de datos ────────────────────────────────────────
POSTGRES_DB=crm_obra_social
POSTGRES_USER=crm_user
POSTGRES_PASSWORD=password-seguro-aqui

# ─── Redis ────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ─── Meta WhatsApp Business API ───────────────────────────
WHATSAPP_ACCESS_TOKEN=tu-token-de-meta
WHATSAPP_PHONE_NUMBER_ID=tu-phone-number-id
WHATSAPP_WEBHOOK_VERIFY_TOKEN=token-secreto-para-el-webhook
WHATSAPP_BUSINESS_ACCOUNT_ID=tu-waba-id
WHATSAPP_APP_SECRET=tu-app-secret-de-meta

# ─── Hosts ────────────────────────────────────────────────
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

**Generar una SECRET_KEY segura:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## Paso 4 — Configurar `docker-compose.yml` para producción

Editar el `docker-compose.yml` para cambiar la variable de settings:

```bash
nano /opt/crmsupreg/docker-compose.yml
```

Cambiar en los servicios `web`, `celery` y `celery-beat`:
```yaml
environment:
  DJANGO_SETTINGS_MODULE: config.settings.production  # ← cambiar de local a production
```

---

## Paso 5 — Configurar Nginx como reverse proxy

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

Crear el archivo de configuración:
```bash
sudo nano /etc/nginx/sites-available/crm
```

Contenido:
```nginx
server {
    listen 80;
    server_name crm.tuempresa.com;

    # Redirigir HTTP → HTTPS (después de obtener el certificado)
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name crm.tuempresa.com;

    # SSL — Certbot lo completa automáticamente
    # ssl_certificate ...
    # ssl_certificate_key ...

    client_max_body_size 20M;

    # Archivos estáticos
    location /static/ {
        alias /opt/crmsupreg/crm_obra_social/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Archivos de media
    location /media/ {
        alias /opt/crmsupreg/crm_obra_social/media/;
        expires 7d;
    }

    # Django/Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
    }
}
```

Activar el sitio:
```bash
sudo ln -s /etc/nginx/sites-available/crm /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Paso 6 — Certificado SSL (HTTPS gratis con Let's Encrypt)

```bash
# Obtener certificado
sudo certbot --nginx -d crm.tuempresa.com

# Verificar renovación automática
sudo certbot renew --dry-run
```

---

## Paso 7 — Levantar el sistema

```bash
cd /opt/crmsupreg

# Primera vez — construir y levantar
docker compose up --build -d

# Ver que todos los contenedores estén corriendo
docker compose ps

# Ver logs en tiempo real
docker compose logs -f web
```

Esperar hasta ver:
```
web-1  | [INFO] Listening at: http://0.0.0.0:8000
```

---

## Paso 8 — Crear el superusuario

```bash
docker compose exec web python manage.py createsuperuser
```

---

## Paso 9 — Cargar datos iniciales (opcional)

```bash
# Planes de obra social de ejemplo
docker compose exec web python manage.py loaddata apps/leads/fixtures/planes_iniciales.json
```

---

## Paso 10 — Verificar que todo funciona

```bash
# Probar que el sistema responde
curl -I https://crm.tuempresa.com

# Verificar Celery Beat (tareas programadas)
docker compose logs celery-beat | tail -20

# Verificar worker Celery
docker compose logs celery | tail -20
```

---

## Comandos útiles en producción

```bash
# Ver todos los logs
docker compose logs -f

# Reiniciar solo el web (después de cambios en código)
docker compose restart web

# Actualizar el código (con git)
git pull && docker compose up --build -d

# Backup de la base de datos
docker compose exec db pg_dump -U crm_user crm_obra_social > backup_$(date +%Y%m%d).sql

# Restaurar backup
cat backup_20260520.sql | docker compose exec -T db psql -U crm_user crm_obra_social

# Abrir shell de Django
docker compose exec web python manage.py shell

# Ver espacio en disco
docker system df
```

---

## Actualizar el sistema (deploy de nueva versión)

```bash
cd /opt/crmsupreg

# 1. Bajar el código nuevo
git pull

# 2. Reconstruir y reiniciar en background (sin downtime)
docker compose up --build -d

# 3. Verificar que levantó bien
docker compose ps
docker compose logs web --tail 20
```

---

## Configurar webhook de WhatsApp con el dominio real

Una vez que el servidor esté con HTTPS, en Meta for Developers configurar:

- **Callback URL:** `https://crm.tuempresa.com/whatsapp/webhook/`
- **Verify Token:** el valor de `WHATSAPP_WEBHOOK_VERIFY_TOKEN` en tu `.env`

---

## Monitoreo básico

```bash
# Alertas de recursos
sudo apt-get install -y htop

# Ver uso de recursos de los contenedores
docker stats

# Logs del sistema
sudo journalctl -u nginx -f
```

---

## Firewall (UFW)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

---

## Notas importantes

- **Nunca** subas el archivo `.env` a Git. Está en `.gitignore`.
- Los archivos de media (imágenes, PDFs) persisten en el volumen Docker `media_data`.
- La base de datos persiste en el volumen `postgres_data`. No se borra al hacer `docker compose up --build`.
- Para borrar todo (reset total): `docker compose down -v` ⚠️ destruye la DB.
- Mantener backups diarios de la base de datos.
