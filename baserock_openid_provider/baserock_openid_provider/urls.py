from django.conf.urls import patterns, include, url
from django.contrib import admin

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'baserock_openid_provider.views.home', name='home'),
    # url(r'^blog/', include('blog.urls')),

    url(r'^accounts/', include('registration.backends.simple.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^openid/', include('openid_provider.urls')),
)
