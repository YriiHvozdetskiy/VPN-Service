from django.urls import path

from authentication import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('profile/edit/', views.ProfileEditView.as_view(), name='profile_edit'),
]
