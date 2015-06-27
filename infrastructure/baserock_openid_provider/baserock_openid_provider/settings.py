"""
Django settings for baserock_openid_provider project.

For more information on this file, see
https://docs.djangoproject.com/en/1.7/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.7/ref/settings/
"""

import yaml

import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.7/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
secret_key_file = '/etc/baserock_openid_provider.secret_key.yml'
with open(secret_key_file) as f:
    data = yaml.load(f)
    SECRET_KEY = data['baserock_openid_provider_secret_key']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = [
    'openid.baserock.org',
]

# All connections for openid.baserock.org are forced through HTTPS by HAProxy.
# This line is necessary so that the Django code generates https:// rather than
# http:// URLs for internal redirects.
#
# You MUST remove this line if this application is not running behind a proxy
# that forces all traffic through HTTPS.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Application definition

INSTALLED_APPS = (
    'baserock_openid_provider',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'openid_provider',
    'registration'
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'baserock_openid_provider.urls'

WSGI_APPLICATION = 'baserock_openid_provider.wsgi.application'


# Logging

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(asctime)s %(message)s'
        }
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'formatter': 'simple',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/baserock_openid_provider/debug.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 0,
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'openid_provider.views': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        }
    }
}


# Database
# https://docs.djangoproject.com/en/1.7/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'openid_provider',
        'USER': 'openid',
        'PORT': '3306',

        # You must change this to the correct IP address when
        # deploying to production! For development deployments this
        # gets the IP of the 'baserock-database' container from the
        # environment, which Docker will have set if you passed it
        # `--link=baseock-database:db`.
        'HOST': os.environ.get('DB_PORT_3306_TCP_ADDR', '192.168.222.30')
    }
}


pw_file = '/etc/baserock_openid_provider.database_password.yml'
with open(pw_file) as f:
    data = yaml.load(f)
    password = data['baserock_openid_provider_password']
    DATABASES['default']['PASSWORD'] = password

# Internationalization
# https://docs.djangoproject.com/en/1.7/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.7/howto/static-files/

STATIC_URL = '/static/'

STATIC_ROOT = '/var/www/static'

TEMPLATE_DIRS = [os.path.join(BASE_DIR, 'templates')]


# Other stuff

LOGIN_REDIRECT_URL = '/'


# We get mailed when stuff breaks.
ADMINS = (
    ('Sam Thursfield', 'sam.thursfield@codethink.co.uk'),
)

# FIXME: this email address doesn't actually exist.
DEFAULT_FROM_EMAIL = 'openid@baserock.org'

EMAIL_HOST = 'localhost'
EMAIL_PORT = 25


# django-registration-redux settings

ACCOUNT_ACTIVATION_DAYS = 3
