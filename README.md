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
- Пакет языковых данных `tesseract-ocr-rus` для распознавания русского текста (устанавливается в Dockerfile)

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
- `POST /api/receipts/preview` — распознать чек без сохранения в БД (отладка OCR).
- `GET /health` — проверка готовности.

## Развёртывание

- Образ собирается из `Dockerfile` (Python 3.11 slim, Tesseract, OpenCV).
- При старте контейнера автоматически выполняется `alembic upgrade head`, затем запускается Gunicorn+Uvicorn workers.
- Данные БД сохраняются в volume `db_data`, медиа — в `media_data`.

## Troubleshooting

### `KeyError: 'ContainerConfig'` during `docker-compose up`

The legacy `docker-compose` (Python, hyphenated) client can raise `KeyError: 'ContainerConfig'` when used with newer Docker Engine versions. Use the Compose V2 plugin instead:

1. Verify you have Compose V2: `docker compose version` (note the space).
2. If you only have the legacy binary, [install the Docker Compose plugin](https://docs.docker.com/compose/install/), or upgrade Docker to a version that ships it by default.
3. Clean up any previously created containers/volumes after upgrading: `docker compose down --volumes --remove-orphans`.
4. Rebuild and start the stack again: `docker compose up -d --build`.

## Резервное копирование и обновления

- Бэкап БД: `docker compose exec db pg_dump -U postgres receipt > backup.sql`
- Восстановление: `cat backup.sql | docker compose exec -T db psql -U postgres receipt`
- Обновление приложения: `git pull` → `docker compose build --no-cache app` → `docker compose up -d`

## Health-check

- `GET /health` возвращает `{"status":"ok"}` при готовности приложения.
