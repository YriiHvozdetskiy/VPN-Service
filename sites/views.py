from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import HttpResponse, HttpResponseNotFound, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from fake_useragent import UserAgent
import logging

from sites.forms import SiteForm
from sites.models import Site, SiteStatistics

logger = logging.getLogger(__name__)


def get_user_agent():
    cached_ua = cache.get('user_agent')
    if cached_ua:
        return cached_ua

    try:
        ua = UserAgent()
        new_ua = ua.random
        cache.set('user_agent', new_ua, 3600)  # Кешуємо на 1 годину
        return new_ua
    except Exception as e:
        logger.error(f"Помилка при отриманні User-Agent: {str(e)}")
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"


@login_required
def site_list(request):
    sites = Site.objects.filter(user=request.user)
    form = SiteForm()
    return render(request, 'site_list.html', {'sites': sites, 'form': form})


@login_required
@require_http_methods(["GET", "POST"])
def add_site(request):
    if request.method == 'POST':
        form = SiteForm(request.POST, user=request.user)
        if form.is_valid():
            site = form.save(commit=False)
            site.user = request.user
            site.save()
            messages.success(request, 'Сайт успішно додано.')
            return redirect('sites:list')
    else:
        form = SiteForm(user=request.user)
    return render(request, 'add_site.html', {'form': form})


@login_required
def proxy_view(request, site_name, path=''):
    try:
        site_name = site_name.replace(' ', '-')
        site = get_object_or_404(Site, user=request.user, name=site_name)
        url = urljoin(site.url, path or '')
    except Http404:
        return HttpResponseNotFound(f"Сайт з ім'ям '{site_name}' не знайдено.")

    headers = {'User-Agent': get_user_agent()}

    try:
        response = requests.get(url, headers=headers)
        content = response.content
    except requests.RequestException as e:
        logger.error(f"Помилка при запиті до {url}: {str(e)}")
        return HttpResponse("Сталася помилка при спробі доступу до сайту", status=500)

    soup = BeautifulSoup(content, 'html.parser')

    # Оновлення статистики
    stats, _ = SiteStatistics.objects.get_or_create(site=site, path=path)
    stats.visits = F('visits') + 1
    stats.data_sent = F('data_sent') + len(request.body)
    stats.data_received = F('data_received') + len(content)
    stats.save()

    # Додаємо кнопку "Повернутися"
    back_button = soup.new_tag("a", href=request.build_absolute_uri('/sites/'))
    back_button.string = "Повернутися до списку сайтів"
    back_button['style'] = """
        position: fixed;
        top: 10px;
        left: 10px;
        padding: 10px 15px;
        background-color: #007bff;
        color: white;
        text-decoration: none;
        border-radius: 5px;
        z-index: 9999;
    """
    soup.body.insert(0, back_button)

    # Оновлюємо всі посилання
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('/'):
            # Абсолютний шлях на оригінальному сайті
            a['href'] = f'/{site_name}{href}'
        elif not href.startswith(('http://', 'https://', '//')):
            # Відносний шлях
            a['href'] = f'/{site_name}/{href}'
        else:
            # Зовнішнє посилання або повний URL
            parsed = urlparse(href)
            if parsed.netloc == urlparse(site.url).netloc:
                path = parsed.path
                if parsed.query:
                    path += f'?{parsed.query}'
                a['href'] = f'/{site_name}{path}'

    # Оновлюємо ресурси (CSS, JS, зображення)
    for tag in soup.find_all(['link', 'script', 'img']):
        for attr in ['src', 'href']:
            if tag.has_attr(attr):
                value = tag[attr]
                if value.startswith('/'):
                    # Абсолютний шлях на оригінальному сайті
                    tag[attr] = urljoin(site.url, value)
                elif not value.startswith(('http://', 'https://', '//')):
                    # Відносний шлях
                    tag[attr] = urljoin(url, value)

    return HttpResponse(str(soup))


@login_required
def proxy_resource(request, site_name, resource_path):
    site = get_object_or_404(Site, user=request.user, name=site_name)
    url = urljoin(site.url, resource_path)

    headers = {'User-Agent': get_user_agent()}

    try:
        response = requests.get(url, headers=headers)
    except requests.RequestException as e:
        logger.error(f"Помилка при запиті ресурсу {url}: {str(e)}")
        return HttpResponse("Помилка при завантаженні ресурсу", status=500)

    django_response = HttpResponse(
        content=response.content,
        status=response.status_code,
        content_type=response.headers.get('Content-Type')
    )

    # Копіюємо всі заголовки
    for header, value in response.headers.items():
        if header.lower() not in ['content-encoding', 'transfer-encoding', 'content-length']:
            django_response[header] = value

    return django_response


@login_required
def site_statistics(request, site_name):
    site = get_object_or_404(Site, user=request.user, name=site_name)
    statistics = site.statistics.all().order_by('-visits')
    return render(request, 'site_statistics.html', {'site': site, 'statistics': statistics})
