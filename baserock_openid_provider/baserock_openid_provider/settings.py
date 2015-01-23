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
SECRET_KEY = '#k9g0dclqiqxomjk2=&fu+$n-(b$d4**5usy!%(b3#k8m)qpif'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = (
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
    'handlers': {
        'file': {
            'level': 'DEBUG',
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
        'HOST': os.environ['DB_PORT_3306_TCP_ADDR']
    }
}


# This file lives under /var/lib currently so that the user who runs
# this code can read it. That user is 'uwsgi'. Putting it in /srv would
# be fine except that it interferes with the way development deployments
# are done.
pw_file = '/var/lib/baserock_openid_provider.database_password.yml'
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

TEMPLATE_DIRS = [os.path.join(BASE_DIR, 'templates')]


# Other stuff

LOGIN_REDIRECT_URL = '/'
