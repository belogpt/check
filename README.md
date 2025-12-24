# Receipt Check Splitter

Веб-приложение для распознавания ресторанных чеков и разделения позиций между участниками. Пользователь загружает изображение, корректирует позиции и публикует комнату оплаты, где участники закрывают юниты полностью или частично.

## Возможности

- Загрузка изображений чеков (JPG/PNG/WEBP) до 20 МБ.
- Предобработка через OpenCV и OCR с Tesseract (rus+eng).
- Ручная правка: редактирование, удаление и добавление позиций.
- Генерация комнаты `/r/{token}` без авторизации.
- Оплата юнитов целиком или частично с транзакционной блокировкой.
- WebSocket-обновления (fallback — polling).
- Docker/Docker Compose для production-развёртывания.

## Требования

- Docker и Docker Compose
- 4 CPU / 4 GB RAM рекомендованы для OCR
- Свободные порты: `8000` (приложение), `5432` (PostgreSQL)

## Быстрый старт

```bash
git clone <repo>
cd <repo>
cp .env.example .env
docker compose up -d --build
```

Приложение будет доступно на `http://localhost:8000`.

## Конфигурация окружения (`.env`)

| Переменная       | По умолчанию                                              | Описание                          |
| ---------------- | --------------------------------------------------------- | --------------------------------- |
| `DATABASE_URL`   | `postgresql+asyncpg://postgres:postgres@db:5432/receipt` | URL подключения к БД              |
| `MEDIA_ROOT`     | `/data/media`                                            | Каталог для загруженных файлов    |
| `UPLOAD_MAX_MB`  | `20`                                                     | Лимит размера файла в мегабайтах  |
| `TESSERACT_CMD`  | `/usr/bin/tesseract`                                     | Путь к бинарю tesseract           |
| `GUNICORN_WORKERS` | `3`                                                    | Количество workers в прод-режиме  |

## Структура API

- `POST /api/receipts` — загрузка изображения, возврат `receipt_id` и распознанных позиций.
- `GET /api/receipts/{id}/items` — получить позиции для проверки.
- `PUT /api/receipts/{id}/items` — сохранить исправленные позиции.
- `POST /api/receipts/{id}/finalize` — создать комнату и токен.
- `GET /api/receipts/{token}` — данные комнаты: позиции, юниты, платежи.
- `POST /api/receipts/{token}/pay` — оплатить юнит полностью или частично.
- `GET /health` — проверка готовности.

## Развёртывание

- Образ собирается из `Dockerfile` (Python 3.11 slim, Tesseract, OpenCV).
- При старте контейнера автоматически выполняется `alembic upgrade head`, затем запускается Gunicorn+Uvicorn workers.
- Данные БД сохраняются в volume `db_data`, медиа — в `media_data`.

## Резервное копирование и обновления

- Бэкап БД: `docker compose exec db pg_dump -U postgres receipt > backup.sql`
- Восстановление: `cat backup.sql | docker compose exec -T db psql -U postgres receipt`
- Обновление приложения: `git pull` → `docker compose build --no-cache app` → `docker compose up -d`

## Health-check

- `GET /health` возвращает `{"status":"ok"}` при готовности приложения.
