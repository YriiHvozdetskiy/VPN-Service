from django.urls import path, re_path

from sites import views

app_name = 'sites'

urlpatterns = [
    path('', views.site_list, name='list'),
    path('add/', views.add_site, name='add'),
    path('statistics/<str:site_name>/', views.site_statistics, name='statistics'),
    re_path(r'^(?P<site_name>[\w-]+)(?P<path>/.*)?$', views.proxy_view, name='proxy_view'),
]
