import logging
import random
import re
import time
from datetime import timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import F, Sum, Avg
from django.http import HttpResponse, Http404, StreamingHttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from fake_useragent import UserAgent

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


@csrf_exempt
@login_required
def proxy_view(request, site_name, path=''):
    try:
        site = get_object_or_404(Site, user=request.user, name=site_name)
        url = urljoin(site.url, path or '')
    except Http404:
        messages.error(request, f"Сайт з ім'ям '{site_name}' не знайдено.")
        return redirect('sites:list')

    headers = {'User-Agent': get_user_agent(request)}

    start_time = time.time()
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        content = response.content
    except requests.Timeout:
        messages.error(request, "Час очікування відповіді від сайту вичерпано.")
        return redirect('sites:list')
    except requests.RequestException as e:
        logger.error(f"Помилка при запиті до {url}: {str(e)}")
        messages.error(request, "Виникла помилка при спробі доступу до сайту.")
        return redirect('sites:list')
    end_time = time.time()

    content_type = response.headers.get('Content-Type', '').split(';')[0].lower()

    # Оновлення статистики
    update_statistics(site, path, request, response, content, start_time, end_time)

    if content_type in ['text/html', 'application/xhtml+xml']:
        content = process_html(content, site_name, site.url, path)
    elif content_type.startswith('text/'):
        content = process_text(content, site_name)

    response = HttpResponse(content, content_type=response.headers.get('Content-Type'))

    # Копіюємо важливі заголовки
    for header in ['Content-Disposition', 'Cache-Control', 'Expires']:
        if header in response.headers:
            response[header] = response.headers[header]

    return response


def update_statistics(site, path, request, response, content, start_time, end_time):
    content_type = response.headers.get('Content-Type', '').split(';')[0].lower()
    content_length = len(content)

    stats, _ = SiteStatistics.objects.get_or_create(site=site, path=path)
    stats.visits = F('visits') + 1
    stats.data_sent = F('data_sent') + len(request.body)
    stats.data_received = F('data_received') + content_length
    stats.response_time = (stats.response_time * (stats.visits - 1) + (end_time - start_time)) / stats.visits
    stats.status_code = response.status_code
    stats.content_type = content_type
    stats.user_agent = request.headers.get('User-Agent', '')

    # Визначаємо, чи це перегляд сторінки
    stats.is_page_view = 'text/html' in content_type

    # Оновлюємо статистику за типами контенту
    if 'text/html' in content_type:
        stats.html_count = F('html_count') + 1
        stats.html_size = F('html_size') + content_length
    elif 'image/' in content_type:
        stats.image_count = F('image_count') + 1
        stats.image_size = F('image_size') + content_length
    elif 'javascript' in content_type:
        stats.js_count = F('js_count') + 1
        stats.js_size = F('js_size') + content_length
    elif 'css' in content_type:
        stats.css_count = F('css_count') + 1
        stats.css_size = F('css_size') + content_length
    else:
        stats.other_count = F('other_count') + 1
        stats.other_size = F('other_size') + content_length

    stats.save()


def process_html(content, site_name, site_url, path):
    soup = BeautifulSoup(content, 'html.parser')

    # Додаємо кнопку "Повернутися"
    if soup.body:
        back_button = soup.new_tag("a", attrs={
            "href": f"/sites/",
            "style": """
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
        })
        back_button.string = "Повернутися до списку сайтів"
        soup.body.insert(0, back_button)

    # Оновлення посилань та ресурсів
    tags_to_update = ['a', 'link', 'script', 'img', 'video', 'iframe', 'source']
    attrs_to_update = ['href', 'src', 'action']

    for tag in soup.find_all(tags_to_update):
        for attr in attrs_to_update:
            if tag.has_attr(attr):
                value = tag[attr]
                new_value = process_url(value, site_name, site_url, path)
                if new_value:
                    tag[attr] = new_value

    # Додавання мета-тегу для запобігання індексації
    if soup.head:
        meta_tag = soup.new_tag("meta", attrs={"content": "noindex, nofollow", "name": "robots"})
        soup.head.append(meta_tag)

    return str(soup)


def process_text(content, site_name):
    decoded_content = content.decode('utf-8')
    # Оновлюємо відносні шляхи в CSS або JavaScript файлах
    updated_content = re.sub(
        r'url\([\'"]?(/[^)\'"]+=?[^)\'"]*)[\'"]?\)',
        lambda m: f'url(/{site_name}{m.group(1)})',
        decoded_content
    )
    return updated_content.encode('utf-8')


def process_url(url, site_name, site_url, current_path):
    parsed = urlparse(url)
    if not parsed.netloc:  # Відносний URL
        if url.startswith('/'):
            # Видаляємо дублюючі слеші
            cleaned_url = re.sub(r'/+', '/', url)
            return f'/{site_name}{cleaned_url}'
        else:
            # Для відносних URL без початкового слешу
            base_path = '/'.join(current_path.split('/')[:-1]) + '/'
            full_path = urljoin(base_path, url)
            return f'/{site_name}{full_path}'
    elif parsed.netloc == urlparse(site_url).netloc:  # Внутрішній абсолютний URL
        # Видаляємо дублюючі слеши в шляху
        cleaned_path = re.sub(r'/+', '/', parsed.path)
        new_path = f'/{site_name}{cleaned_path}'
        if parsed.query:
            new_path += f'?{parsed.query}'
        return new_path
    return url  # Зовнішній URL, залишаємо без змін


@login_required
def proxy_resource(request, site_name, resource_path):
    site = get_object_or_404(Site, user=request.user, name=site_name)
    url = urljoin(site.url, resource_path)

    # Перевірка, чи ресурс є внутрішнім
    if not url.startswith(site.url):
        return HttpResponse("Доступ заборонено", status=403)

    headers = {'User-Agent': get_user_agent(request)}

    try:
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Помилка при запиті ресурсу {url}: {str(e)}")
        return HttpResponse("Помилка при завантаженні ресурсу", status=500)

    content_type = response.headers.get('Content-Type', '')

    # Створюємо StreamingHttpResponse для ефективної передачі великих файлів
    django_response = StreamingHttpResponse(
        streaming_content=response.iter_content(chunk_size=8192),
        content_type=content_type
    )

    # Копіюємо релевантні заголовки
    for header in ['Content-Length', 'Content-Disposition', 'Cache-Control']:
        if header in response.headers:
            django_response[header] = response.headers[header]

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

    # Отримуємо статистику тільки для переглядів сторінок
    page_statistics = site.statistics.filter(
        last_visit__date__gte=start_date,
        last_visit__date__lte=end_date,
        is_page_view=True
    ).order_by('-visits')

    # Топ-5 найпопулярніших сторінок
    top_pages = page_statistics.order_by('-visits')[:5]

    # Агреговані дані для всієї статистики (включаючи ресурси)
    aggregated_data = site.statistics.filter(
        last_visit__date__gte=start_date,
        last_visit__date__lte=end_date
    ).aggregate(
        total_visits=Sum('visits'),
        total_data_sent=Sum('data_sent'),
        total_data_received=Sum('data_received'),
        avg_response_time=Avg('response_time'),
        total_html_count=Sum('html_count'),
        total_image_count=Sum('image_count'),
        total_js_count=Sum('js_count'),
        total_css_count=Sum('css_count'),
        total_other_count=Sum('other_count'),
        total_html_size=Sum('html_size'),
        total_image_size=Sum('image_size'),
        total_js_size=Sum('js_size'),
        total_css_size=Sum('css_size'),
        total_other_size=Sum('other_size'),
    )

    context = {
        'site': site,
        'page_statistics': page_statistics,
        'aggregated_data': aggregated_data,
        'top_pages': top_pages,
        'start_date': start_date,
        'end_date': end_date,
    }

    return render(request, 'site_statistics.html', context)
