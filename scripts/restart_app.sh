#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON_DEFAULT="$PROJECT_DIR/.venv/bin/python"
HOST_DEFAULT="0.0.0.0"
PORT_DEFAULT="8000"
LOG_DEFAULT="/tmp/devoluciones-runserver.log"

usage() {
  cat <<'EOF'
Uso:
  ./scripts/restart_app.sh dev
  ./scripts/restart_app.sh systemd <django_service> [nginx_service] [postgres_service]

Modos:
  dev
    Mata procesos previos de runserver/gunicorn de este proyecto y arranca runserver en background.

  systemd
    Reinicia servicios systemd. Ejemplo:
    ./scripts/restart_app.sh systemd devoluciones nginx postgresql

Variables opcionales para modo dev:
  DEV_HOST              Host para runserver. Por defecto: 0.0.0.0
  DEV_PORT              Puerto para runserver. Por defecto: 8000
  DEV_LOG               Fichero log. Por defecto: /tmp/devoluciones-runserver.log
  VENV_PYTHON           Python del entorno virtual. Por defecto: .venv/bin/python
EOF
}

restart_dev() {
  local host="${DEV_HOST:-$HOST_DEFAULT}"
  local port="${DEV_PORT:-$PORT_DEFAULT}"
  local log_file="${DEV_LOG:-$LOG_DEFAULT}"
  local python_bin="${VENV_PYTHON:-$VENV_PYTHON_DEFAULT}"
  local bind_target="${host}:${port}"

  echo "Reiniciando entorno local de Django..."
  pkill -f "$PROJECT_DIR/manage.py runserver" || true
  pkill -f "$PROJECT_DIR/.venv/bin/gunicorn .*config.wsgi:application" || true
  pkill -f "gunicorn .*config.wsgi:application --bind ${bind_target}" || true
  sleep 1

  if ss -ltnp 2>/dev/null | grep -q ":${port} "; then
    echo "El puerto ${port} sigue ocupado tras intentar reiniciar el modo dev." >&2
    echo "Si la aplicación corre con systemd o gunicorn gestionado externamente, usa:" >&2
    echo "  ./scripts/restart_app.sh systemd <django_service> [nginx_service] [postgres_service]" >&2
    exit 1
  fi

  if [[ ! -x "$python_bin" ]]; then
    echo "No se encontró el intérprete de la venv en: $python_bin" >&2
    echo "Configura VENV_PYTHON o crea la venv en $PROJECT_DIR/.venv" >&2
    exit 1
  fi

  (
    cd "$PROJECT_DIR"
    nohup "$python_bin" manage.py runserver "${host}:${port}" >"$log_file" 2>&1 &
  )

  echo "Aplicación reiniciada en http://${host}:${port}"
  echo "Log: $log_file"
}

restart_systemd() {
  local django_service="${1:-}"
  local nginx_service="${2:-}"
  local postgres_service="${3:-}"

  if [[ -z "$django_service" ]]; then
    echo "Debes indicar el nombre del servicio Django para el modo systemd." >&2
    usage
    exit 1
  fi

  echo "Reiniciando servicio Django: $django_service"
  sudo systemctl restart "$django_service"

  if [[ -n "$nginx_service" ]]; then
    echo "Reiniciando Nginx: $nginx_service"
    sudo systemctl restart "$nginx_service"
  fi

  if [[ -n "$postgres_service" ]]; then
    echo "Reiniciando PostgreSQL: $postgres_service"
    sudo systemctl restart "$postgres_service"
  fi

  echo "Estado del servicio Django:"
  sudo systemctl --no-pager --full status "$django_service" | sed -n '1,12p'
}

main() {
  local mode="${1:-}"

  case "$mode" in
    dev)
      restart_dev
      ;;
    systemd)
      shift
      restart_systemd "$@"
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      echo "Modo no reconocido: $mode" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
