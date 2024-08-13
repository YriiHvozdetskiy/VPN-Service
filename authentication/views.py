from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.views import View

from authentication.forms import CustomUserCreationForm, CustomAuthenticationForm, UserProfileEditForm
from sites.forms import SiteForm
from sites.models import Site


class RegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        form = CustomUserCreationForm()
        return render(request, 'register.html', {'form': form})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
        return render(request, 'register.html', {'form': form})


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        form = CustomAuthenticationForm()
        return render(request, 'login.html', {'form': form})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        form = CustomAuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
        return render(request, 'login.html', {'form': form})


@method_decorator(login_required, name='dispatch')
class ProfileEditView(View):
    def get(self, request):
        form = UserProfileEditForm(instance=request.user)
        return render(request, 'profile_edit.html', {'form': form})

    def post(self, request):
        form = UserProfileEditForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профіль успішно оновлено.')
            return redirect('dashboard')
        return render(request, 'profile_edit.html', {'form': form})


@method_decorator(login_required, name='dispatch')
class DashboardView(View):
    def get(self, request):
        user_sites = Site.objects.filter(user=request.user)
        site_form = SiteForm()
        context = {
            'user_sites': user_sites,
            'site_form': site_form,
        }
        return render(request, 'dashboard.html', context)

    def post(self, request):
        site_form = SiteForm(request.POST)
        if site_form.is_valid():
            site = site_form.save(commit=False)
            site.user = request.user
            site.save()
            messages.success(request, 'Сайт успішно додано.')
            return redirect('dashboard')

        user_sites = Site.objects.filter(user=request.user)
        context = {
            'user_sites': user_sites,
            'site_form': site_form,
        }
        return render(request, 'dashboard.html', context)


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect('login')
