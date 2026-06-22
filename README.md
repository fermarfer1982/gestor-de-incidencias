# Incidencias

Aplicación interna en Django para gestionar incidencias de:

- devoluciones
- pedidos
- transporte

La aplicación es server-rendered, usa PostgreSQL como base de datos principal y consulta SQL Server externo en solo lectura para buscar albaranes del ERP.

## Stack técnico

- Python 3.12
- Django 6
- PostgreSQL
- SQL Server externo con `mssql-python`
- Gunicorn
- Bootstrap en plantillas server-rendered

## Apps del proyecto

- `core`
  - autenticación por email
  - permisos por rol y alcance
  - dashboard
  - utilidades comunes
- `devoluciones`
  - incidencias de devoluciones
  - selección de líneas de albarán
  - cantidades de incidencia
  - adjuntos
  - exportación listado y detalle
- `pedidos`
  - incidencias de pedidos
  - selección de líneas de albarán
  - nota por línea
  - adjuntos
  - exportación listado y detalle
- `transporte`
  - incidencias de transporte con o sin albarán
  - adjuntos
  - exportación listado y detalle
- `erp`
  - integración de solo lectura con SQL Server
  - búsqueda de albaranes por número y representante

## Funcionalidad actualmente implementada

- login/logout con usuarios Django
- autenticación por email
- permisos por grupos Django:
  - `comercial`
  - `administracion`
  - `almacen`
- perfiles de acceso por representante:
  - `UserAccessProfile`
  - `UserRepresentativeScope`
- acceso total para:
  - `superuser`
  - `almacen`
- acceso por alcance de representantes para:
  - `administracion`
  - `comercial`
- solo `superuser` puede borrar registros
- búsqueda de albarán en ERP
- creación de incidencias con adjuntos
- listado, detalle, cambio de estado y resolución
- exportación de listados a CSV y Excel
- exportación individual del detalle en vista imprimible y PDF
- administración interna con Django admin
- tests automáticos con `manage.py test` y `pytest`

## Estados de incidencia

Los tres módulos usan el mismo patrón funcional:

- `pending` -> `Abierta`
- `in_progress` -> `En trámite`
- `closed` -> `Cerrada`

Al cerrar una incidencia:

- `resolution_notes` es obligatorio
- se rellenan `closed_at` y `closed_by`

## Variables de entorno

Crear un fichero `.env` en la raíz del proyecto:

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_LOG_LEVEL=INFO
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

ALLOW_STAFF_REPRESENTATIVE_BYPASS=False
```

Notas:

- `ERP_SQLSERVER_CONNECTION_STRING` permite usar una connection string completa.
- Si no se usa connection string completa, la configuración se compone con `HOST`, `PORT`, `NAME`, `USER` y `PASSWORD`.
- `DJANGO_USE_SQLITE=True` está pensado solo para pruebas locales rápidas.

## Instalación local

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
python manage.py migrate
python manage.py createsuperuser
python manage.py load_initial_representatives
python manage.py test
pytest
python manage.py collectstatic --noinput
./scripts/restart_app.sh dev
./scripts/restart_app.sh systemd <django_service> [nginx_service] [postgres_service]
```

Para validar la app con SQLite:

```bash
DJANGO_USE_SQLITE=True python manage.py check
DJANGO_USE_SQLITE=True python manage.py test
```

## Carga inicial de representantes

Existe un management command idempotente para cargar:

- representantes iniciales
- usuarios por email
- relación usuario-representante histórica
- perfiles y alcances del sistema de permisos actual
- grupos Django necesarios

Ejecución:

```bash
python manage.py load_initial_representatives
```

## Estructura funcional resumida

### Devoluciones

Flujo principal:

1. Buscar albarán
2. Ver cabecera y líneas
3. Seleccionar líneas
4. Informar cantidad de incidencia
5. Crear incidencia con observaciones, destino y adjuntos
6. Gestionar estado y resolución

### Pedidos

Flujo principal:

1. Buscar albarán
2. Ver cabecera y líneas
3. Seleccionar líneas
4. Informar nota por línea
5. Crear incidencia con observación general y adjuntos
6. Gestionar estado y resolución

### Transporte

Flujo principal:

1. Crear incidencia con o sin albarán
2. Si hay albarán, asociarlo desde ERP
3. Informar datos de transporte
4. Adjuntar archivos
5. Gestionar estado y resolución

## Exportaciones

### Listados

Los tres módulos permiten:

- exportar CSV
- exportar Excel `.xlsx`

La exportación respeta:

- filtros aplicados
- alcance del usuario

### Detalle individual

Los tres módulos permiten:

- vista imprimible
- exportación PDF

## Autenticación y permisos

La autenticación usa `EmailBackend` y permite login por email.

Reglas actuales:

1. `superuser`
   - acceso total
   - único con permiso de borrado
2. `almacen`
   - acceso global de lectura, creación y edición
   - sin borrado
3. `administracion`
   - acceso por representantes asignados
   - acceso global solo si `all_representatives=True`
   - sin borrado
4. `comercial`
   - acceso por representantes asignados
   - sin borrado

## SQL Server ERP

La app no usa ORM contra SQL Server.

La integración ERP:

- usa `mssql-python`
- hace consultas parametrizadas
- centraliza la conexión en un cliente reutilizable
- devuelve DTOs claros
- maneja logging y errores

La búsqueda de albaranes se usa desde servicios, no directamente desde vistas.

## Tests

Hay cobertura automática para:

- modelos
- permisos
- integración ERP mockeada
- búsquedas de albarán
- creación de incidencias
- adjuntos
- cambio de estado y resolución
- exportaciones

Ejecución:

```bash
python manage.py test
pytest
```

## Reinicio

Para desarrollo local con `runserver`:

```bash
./scripts/restart_app.sh dev
```

Para despliegue con `systemd`:

```bash
./scripts/restart_app.sh systemd devoluciones nginx postgresql
```

## Archivos clave

- `config/settings.py`
- `core/access.py`
- `core/models.py`
- `core/exporting.py`
- `core/printable.py`
- `erp/client.py`
- `erp/services.py`
- `devoluciones/views.py`
- `pedidos/views.py`
- `transporte/views.py`

## Estado del proyecto

El proyecto ya no está en fase de base inicial. Actualmente dispone de:

- tres módulos funcionales
- integración ERP operativa para albaranes
- sistema de permisos por roles y representantes
- administración interna
- exportaciones
- tests automáticos

Lo pendiente, si se sigue ampliando, sería evolución funcional y no arranque técnico.
