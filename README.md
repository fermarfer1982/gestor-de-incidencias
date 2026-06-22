# Gestión de incidencias de devoluciones

Base inicial en Django para una aplicación interna server-rendered con:

- `core` para configuración y layout común.
- `devoluciones` para el dominio funcional.
- `erp` para la integración futura de lectura de albaranes desde SQL Server.
- PostgreSQL como base de datos principal.
- Adjuntos a través de `MEDIA_ROOT`.

## Requisitos

- Python 3.12+
- PostgreSQL accesible desde la aplicación

## Variables de entorno

Crear un fichero `.env` en la raíz del proyecto:

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_USE_SQLITE=False

POSTGRES_DB=devoluciones
POSTGRES_USER=devoluciones
POSTGRES_PASSWORD=devoluciones
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

ERP_SQLSERVER_HOST=
ERP_SQLSERVER_PORT=1433
ERP_SQLSERVER_NAME=
ERP_SQLSERVER_USER=
ERP_SQLSERVER_PASSWORD=
ERP_SQLSERVER_TRUST_SERVER_CERTIFICATE=True
ERP_SQLSERVER_CONNECTION_STRING=
ERP_SQLSERVER_CONNECT_TIMEOUT=5
ERP_SQLSERVER_QUERY_TIMEOUT=15
```

## Arranque local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Comandos útiles

```bash
python manage.py test
pytest
python manage.py collectstatic --noinput
python manage.py load_initial_representatives
./scripts/restart_app.sh dev
./scripts/restart_app.sh systemd <django_service> [nginx_service] [postgres_service]
```

## Reinicio rápido

Para desarrollo local con `runserver`:

```bash
./scripts/restart_app.sh dev
```

Para un despliegue con `systemd`:

```bash
./scripts/restart_app.sh systemd devoluciones nginx postgresql
```

El modo `dev` mata procesos previos de `runserver` o `gunicorn` de este proyecto y vuelve a levantar Django en background, dejando el log en `/tmp/devoluciones-runserver.log`.

## Estado actual

Esta entrega deja preparada la base técnica:

- `settings` leyendo entorno con `python-dotenv`.
- Base de datos principal en PostgreSQL.
- URLs separadas por app.
- Plantillas base con Bootstrap.
- Login de Django y rutas iniciales.

No incluye todavía el modelo de incidencias, la relación usuario-representante ni la lectura real desde SQL Server.

`DJANGO_USE_SQLITE=True` solo está pensado como apoyo local para pruebas rápidas o validación básica sin PostgreSQL.
