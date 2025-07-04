"""
URL configuration for gigspot_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('api/connects/', include('connections.urls')),
    path('api/auth/', include('custom_auth.urls')),
    path('api/utils/', include('utils.urls')),
    path('api/users/', include('users.urls')),
    path('api/venues/', include('venues.urls')),
    path('api/notifications/', include('rt_notifications.urls')),
    path('api/carts/', include('carts.urls')),
    path('api/gigs/', include('gigs.urls')),
    path('api/subscriptions/', include('subscriptions.urls')),
    path('api/services/', include('services.urls')),
    path('api/artists/', include('artists.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/social_auth/', include('social_auth.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/fan/', include('fan.urls')),
    path('api/chat/', include('chat.urls'))
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
