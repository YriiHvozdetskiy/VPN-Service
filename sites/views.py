from datetime import timedelta
from urllib.parse import urljoin, urlparse

import requests
import logging
import random
import time
from bs4 import BeautifulSoup
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum, Avg
from django.http import HttpResponse, HttpResponseNotFound, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from fake_useragent import UserAgent
from django.utils import timezone

from sites.forms import SiteForm
from sites.models import Site, SiteStatistics

logger = logging.getLogger(__name__)


def get_user_agent(request):
    session_ua = request.session.get('user_agent')
    if session_ua:
        return session_ua

    cached_uas = cache.get('user_agents')
    if not cached_uas:
        try:
            ua = UserAgent()
            cached_uas = [ua.random for _ in range(10)]
            # Кешуємо цей список на 24 години
            cache.set('user_agents', cached_uas, 60 * 60 * 24)
        except Exception as e:
            logger.error(f"Помилка при генерації User-Agent: {str(e)}")
            cached_uas = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
                "Mozilla/5.0 (X11; Linux x86_64)"
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X)"
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
            ]

    user_agent = random.choice(cached_uas)

    request.session['user_agent'] = user_agent

    return user_agent


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

    headers = {'User-Agent': get_user_agent(request)}

    start_time = time.time()
    try:
        response = requests.get(url, headers=headers)
        content = response.content
    except requests.RequestException as e:
        logger.error(f"Помилка при запиті до {url}: {str(e)}")
        return HttpResponse("Сталася помилка при спробі доступу до сайту", status=500)
    end_time = time.time()

    soup = BeautifulSoup(content, 'html.parser')

    # Оновлення статистики
    stats, _ = SiteStatistics.objects.get_or_create(site=site, path=path)
    stats.visits = F('visits') + 1
    stats.data_sent = F('data_sent') + len(request.body)
    stats.data_received = F('data_received') + len(content)
    stats.response_time = (stats.response_time * (stats.visits - 1) + (end_time - start_time)) / stats.visits
    stats.status_code = response.status_code
    stats.content_type = response.headers.get('Content-Type', '')
    stats.user_agent = headers['User-Agent']
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

    headers = {'User-Agent': get_user_agent(request)}

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

    # Отримуємо дати з GET-параметрів або використовуємо значення за замовчуванням
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date and end_date:
        start_date = timezone.datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = timezone.datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)

    statistics = site.statistics.filter(
        last_visit__date__gte=start_date,
        last_visit__date__lte=end_date
    ).order_by('-visits')

    # Агреговані дані
    total_visits = statistics.aggregate(Sum('visits'))['visits__sum'] or 0
    total_data_sent = statistics.aggregate(Sum('data_sent'))['data_sent__sum'] or 0
    total_data_received = statistics.aggregate(Sum('data_received'))['data_received__sum'] or 0
    avg_response_time = statistics.aggregate(Avg('response_time'))['response_time__avg'] or 0

    # Топ-5 найпопулярніших сторінок
    top_pages = statistics.order_by('-visits')[:5]

    context = {
        'site': site,
        'statistics': statistics,
        'total_visits': total_visits,
        'total_data_sent': total_data_sent,
        'total_data_received': total_data_received,
        'avg_response_time': avg_response_time,
        'top_pages': top_pages,
        'start_date': start_date,
        'end_date': end_date,
    }

    return render(request, 'site_statistics.html', context)
