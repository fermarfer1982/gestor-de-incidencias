import os
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def env(key, default=None):
    return os.getenv(key, default)

def env_bool(key, default=False):
    value = env(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_list(key, default=""):
    value = env(key, default)
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1")


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.humanize',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'devoluciones',
    'pedidos',
    'transporte',
    'erp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

if env_bool('DJANGO_USE_SQLITE', default=False):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env('POSTGRES_DB', 'devoluciones'),
            'USER': env('POSTGRES_USER', 'devoluciones'),
            'PASSWORD': env('POSTGRES_PASSWORD', 'devoluciones'),
            'HOST': env('POSTGRES_HOST', 'localhost'),
            'PORT': env('POSTGRES_PORT', '5432'),
        }
    }

# Configuracion base para futura integracion de solo lectura contra SQL Server.
ERP_SQLSERVER = {
    'HOST': env('ERP_SQLSERVER_HOST', ''),
    'PORT': env('ERP_SQLSERVER_PORT', '1433'),
    'NAME': env('ERP_SQLSERVER_NAME', ''),
    'USER': env('ERP_SQLSERVER_USER', ''),
    'PASSWORD': env('ERP_SQLSERVER_PASSWORD', ''),
    'TRUST_SERVER_CERTIFICATE': env_bool('ERP_SQLSERVER_TRUST_SERVER_CERTIFICATE', default=True),
}
ERP_SQLSERVER_CONNECTION_STRING = env('ERP_SQLSERVER_CONNECTION_STRING', '')
ERP_SQLSERVER_CONNECT_TIMEOUT = int(env('ERP_SQLSERVER_CONNECT_TIMEOUT', '5'))
ERP_SQLSERVER_QUERY_TIMEOUT = int(env('ERP_SQLSERVER_QUERY_TIMEOUT', '15'))


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'es-es'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

AUTHENTICATION_BACKENDS = [
    'core.auth_backends.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ALLOW_STAFF_REPRESENTATIVE_BYPASS = env_bool('ALLOW_STAFF_REPRESENTATIVE_BYPASS', default=False)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'erp': {
            'handlers': ['console'],
            'level': env('DJANGO_LOG_LEVEL', 'INFO'),
        },
    },
}
