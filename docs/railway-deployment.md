# Перенос существующего приложения в Railway

Цель: сервис `anashym` проекта `ravishing-emotion` запускает UI и Django из корневого
Dockerfile. Старый Vercel остается доступен до проверки Railway. Данные остаются в
существующих Supabase PostgreSQL (схема `bakery`) и приватном bucket `bakery-private-media`.
Не создавать пустую базу, не выполнять seed/flush и не загружать локальные данные.

## Настройки web-сервиса

- Repository: `almaz-svg/anashym`, branch `main`, root `/`, Dockerfile `Dockerfile`.
- Pre-deploy: `python manage.py migrate --noinput`.
- Start command: команда из Dockerfile (`python -m config.railway`).
- Healthcheck: `/ready`; endpoint `/live` проверяет процесс.
- Variables: `DATABASE_URL` со значением действующего `POSTGRES_URL`, действующие
  `DJANGO_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (либо `SUPABASE_SECRET_KEY`).
  Секреты вводятся только в Variables провайдера, не в репозиторий или чат.
- Создать Railway public domain. `RAILWAY_PUBLIC_DOMAIN` автоматически разрешается
  как host и HTTPS CSRF origin. UI и API работают на одном домене, фото выдаются через API.

Сборка UI происходит в Docker build, отдельно от сервера. Waitress обслуживает
Django, WhiteNoise — только собранный frontend и admin static. Media не публикуется.
Описание WhiteNoise: https://whitenoise.readthedocs.io/en/latest/base.html

## После установки переменных

1. Применить staged configuration и выполнить deploy актуального commit.
2. Проверить `/ready`, главную страницу, `/api/v1/auth/csrf`, вход и сохранение сессии.
3. Проверить сохранность прежних записей и доступность существующего приватного фото.
4. Создать отдельный cron-service с тем же image/env и командой
   `python manage.py run_background_jobs`, расписание `*/5 * * * *`.
5. Проверить два последовательных запуска, отсутствие дубликатов и `status=completed`.
6. Выполнить cloud backup/restore drill из `production-operations.md`.

## Фактический статус 18 октября 2026

Новый проект отклонен Railway из-за лимита бесплатного тарифа. Пользователь разрешил
использовать существующий `ravishing-emotion`. Настройки Dockerfile, pre-deploy и
healthcheck подготовлены как staged changes. Применение и рабочий deploy не подтверждены:
сервис пока не имеет переменных базы/хранилища, сохраненная Vercel API-авторизация отклонена.
Облачное расписание и резервное копирование пока не включены.

Рабочие аккаунты еще не созданы. Нужны приглашения для предоставленных пользователем
трех логинов; каждый сотрудник устанавливает свой пароль через одноразовый код.
Демонстрационные аккаунты отключать после подтвержденного входа нового администратора.
