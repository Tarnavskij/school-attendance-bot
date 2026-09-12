# Инструкция по продакшн-развёртыванию

## 1. Веб-панель — НЕ запускать через `python web_viewer.py` в проде

Команда `app.run(...)` — это dev-сервер, не подходит для постоянной работы
(однопоточный, блокируется на SSE-соединениях).

Использовать gunicorn с gevent-воркером (нужен для корректной работы `/stream`):

    pip install gunicorn gevent
    gunicorn -k gevent -w 2 -b 127.0.0.1:5001 web_viewer:app

## 2. TLS/HTTPS — обязательно

Basic Auth передаёт пароль в base64 (НЕ шифрование). Без HTTPS пароль
перехватывается в открытом виде в локальной сети школы.

Поставить nginx перед gunicorn, настроить TLS-сертификат (Let's Encrypt
через certbot, либо внутренний сертификат школьного сервера), проксировать
запросы с nginx на gunicorn (127.0.0.1:5001).

Пример минимального nginx-конфига (адаптировать домен/пути к сертификатам):

    server {
        listen 443 ssl;
        server_name attendance.school.local;

        ssl_certificate     /etc/ssl/certs/school.crt;
        ssl_certificate_key /etc/ssl/private/school.key;

        location / {
            proxy_pass http://127.0.0.1:5001;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_read_timeout 60s;
        }
    }

    server {
        listen 80;
        server_name attendance.school.local;
        return 301 https://$host$request_uri;
    }

## 3. После настройки HTTPS — включить SESSION_COOKIE_SECURE=True

Уже добавлено в код (см. задачу 9). Убедиться, что оно активно после того,
как HTTPS настроен, иначе браузер будет отказываться сохранять cookie.

## 4. Резервное копирование БД PostgreSQL

Настроить ежедневный дамп БД (`pg_dump`) с шифрованием бэкапа и хранением
отдельно от сервера, так как в БД есть данные о причинах отсутствия детей
(в т.ч. по болезни) — это чувствительные данные.

## 5. Мониторинг зависимостей на уязвимости

Периодически (например, раз в месяц) запускать:

    pip install pip-audit
    pip-audit

и обновлять пакеты с найденными критичными CVE.

## 6. Развёртывание на Windows-сервере

Раздел добавлен, потому что `gunicorn` не работает на Windows (требует
`fork()`, которого в Windows нет). Для Windows использовать `waitress`:

    pip install waitress
    waitress-serve --listen=127.0.0.1:5001 web_viewer:app

`waitress` — чистый Python WSGI-сервер, работает на Windows из коробки,
поддерживает SSE (многопоточный).

TLS на Windows — через nginx-for-Windows или IIS + ARR + URL Rewrite
(проксируют с HTTPS на `http://127.0.0.1:5001`). Самоподписанный сертификат
подходит, если панель доступна только внутри школьной сети.

После `git pull` на сервере:

1. `pip install -r requirements.txt` (в нём появились `flask-wtf` и др.)
2. Проверить, что в `.env` есть строка `SIGUR_DB_PASSWORD=<реальный_пароль>`
   (иначе бот не запустится — это поведение по задаче 12).
3. Перезапустить бота и веб-панель.