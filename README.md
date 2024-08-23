# Django VPN Service

Цей проект реалізує простий VPN-сервіс на базі Django.

## Вимоги

- Python 3.11+
- Docker і Docker Compose

## Налаштування проекту

1. Клонуйте репозиторій:
   ```
   git clone <url-репозиторію>
   cd <назва-проекту>
   ```

2. Створіть файл `.env` на основі `.env.example`:
   ```
   cp .env.example .env
   ```

3. Відредагуйте `.env` файл, встановивши власні значення для змінних середовища.

## Запуск проекту

1. Збудуйте та запустіть контейнери:
   ```
   docker-compose up --build
   ```

2. Застосуйте міграції:
   ```
   docker-compose exec web python manage.py migrate
   ```

3. Створіть суперкористувача (опціонально):
   ```
   docker-compose exec web python manage.py createsuperuser
   ```

4. Відкрийте браузер і перейдіть за адресою `http://localhost:8000`

## Розробка

Для запуску Tailwind CSS в режимі розробки:

```
pnpm run dev
```

## Структура проекту

- `authentication/`: Додаток для аутентифікації користувачів
- `sites/`: Додаток для управління сайтами та проксі-функціональністю
- `templates/`: HTML шаблони
- `static/`: Статичні файли (CSS, JavaScript)
- `djangoVpnService/`: Основні налаштування проекту
