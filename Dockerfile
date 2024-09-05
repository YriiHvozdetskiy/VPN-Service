# Етап збірки для Node.js
FROM node:20-alpine AS build
WORKDIR /service

# Встановлення pnpm
RUN npm install -g pnpm

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Основний етап
FROM python:3.11-slim
WORKDIR /service

# Встановлення залежностей для psycopg2 та інших необхідних пакетів
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    gcc \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Встановлення pnpm в основному образі
RUN npm install -g pnpm

# Копіювання файлів проекту
COPY . .

# Копіювання node_modules з етапу збірки
COPY --from=build /service/node_modules ./node_modules

# Встановлення Python залежностей та оновлення pip
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Встановлення Node.js залежностей за допомогою pnpm
RUN pnpm install --frozen-lockfile

# Збір статичних файлів
RUN python manage.py collectstatic --noinput