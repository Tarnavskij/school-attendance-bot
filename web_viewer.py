# web_viewer.py
import io
import functools
import json
import queue
import uuid
from datetime import date
from flask import (
    Flask, render_template_string, request, send_file,
    redirect, url_for, session, Response, jsonify,
)
from markupsafe import escape
from sqlalchemy.orm import joinedload
from database import SessionLocal, AttendanceSession, AttendanceRecord, RegistrationRequest, Teacher, Class
from database import MealRequest, MealRequestItem, Student
from config import DEFAULT_SCHOOL_ID, WEB_USERNAME, WEB_PASSWORD, FLASK_SECRET_KEY, SSE_PUBLISH_TOKEN
from import_students import import_from_excel
import threading

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# ── SSE subscribers ───────────────────────────────────────────────────────────
subscribers: list[queue.Queue] = []
subscribers_lock = threading.Lock()


def _notify_subscribers(event: str, data: dict | None = None) -> None:
    """Посылает событие всем текущим SSE‑подписчикам."""
    payload = f"event: {event}\ndata: {json.dumps(data or {})}\n\n"
    with subscribers_lock:
        for q in subscribers:
            q.put(payload)


# ── HTTP Basic Auth ───────────────────────────────────────────────────────────

def check_auth(username: str, password: str) -> bool:
    return username == WEB_USERNAME and password == WEB_PASSWORD


def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Требуется авторизация.",
                401,
                {"WWW-Authenticate": 'Basic realm="School Attendance"'},
            )
        return f(*args, **kwargs)
    return decorated


# ── HTML шаблон (полный, с разделом питания) ─────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Школьная Перекличка</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    min-height: 100vh;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif;
    color: #e8eaf6;
  }
  .nav {
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding: 16px 32px;
    display: flex;
    align-items: center;
    gap: 32px;
    position: sticky;
    top: 0;
    z-index: 100;
    flex-wrap: wrap;
  }
  .nav-brand {
    font-size: 18px; font-weight: 700;
    background: linear-gradient(135deg, #a78bfa, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .nav a {
    color: rgba(255,255,255,0.6); text-decoration: none;
    font-size: 14px; font-weight: 500;
    padding: 6px 14px; border-radius: 20px; transition: all 0.2s;
  }
  .nav a:hover, .nav a.active { color: #fff; background: rgba(255,255,255,0.1); }
  .nav select {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 12px; padding: 8px 14px;
    color: #e8eaf6; font-size: 14px; outline: none; cursor: pointer;
  }
  .container { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
  .page-title { font-size: 28px; font-weight: 700; margin-bottom: 24px; }
  .glass {
    background: rgba(255,255,255,0.07);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 20px; padding: 24px; margin-bottom: 20px;
  }
  .toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  input[type="date"], input[type="text"], input[type="file"] {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 12px; padding: 10px 16px;
    color: #e8eaf6; font-size: 14px; outline: none;
  }
  .btn {
    padding: 10px 20px; border-radius: 12px;
    font-size: 14px; font-weight: 600;
    border: none; cursor: pointer; text-decoration: none;
    display: inline-flex; align-items: center; gap: 6px; transition: all 0.2s;
  }
  .btn-primary { background: linear-gradient(135deg, #a78bfa, #60a5fa); color: #fff; }
  .btn-primary:hover { opacity: 0.85; transform: translateY(-1px); }
  .btn-success {
    background: rgba(52,199,89,0.2); color: #34c759;
    border: 1px solid rgba(52,199,89,0.3);
  }
  .btn-success:hover { background: rgba(52,199,89,0.3); }
  .btn-danger {
    background: rgba(255,69,58,0.2); color: #ff453a;
    border: 1px solid rgba(255,69,58,0.3);
  }
  .btn-danger:hover { background: rgba(255,69,58,0.3); }
  .btn-sm { padding: 6px 14px; font-size: 13px; border-radius: 10px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th {
    text-align: left; padding: 12px 16px;
    color: rgba(255,255,255,0.4); font-weight: 600;
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  td { padding: 14px 16px; border-bottom: 1px solid rgba(255,255,255,0.05); color: rgba(255,255,255,0.85); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.03); }
  .badge {
    display: inline-block; padding: 3px 10px;
    border-radius: 20px; font-size: 12px; font-weight: 600;
  }
  .badge-pending  { background: rgba(255,214,10,0.15); color: #ffd60a; border: 1px solid rgba(255,214,10,0.3); }
  .badge-approved { background: rgba(52,199,89,0.15);  color: #34c759; border: 1px solid rgba(52,199,89,0.3); }
  .badge-rejected { background: rgba(255,69,58,0.15);  color: #ff453a; border: 1px solid rgba(255,69,58,0.3); }
  .badge-already  { background: rgba(255,159,10,0.15); color: #ff9f0a; border: 1px solid rgba(255,159,10,0.3); }
  .empty { text-align: center; padding: 60px 20px; color: rgba(255,255,255,0.3); font-size: 15px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card {
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px; padding: 20px; text-align: center;
  }
  .stat-number {
    font-size: 32px; font-weight: 700;
    background: linear-gradient(135deg, #a78bfa, #60a5fa);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .stat-label { font-size: 13px; color: rgba(255,255,255,0.4); margin-top: 4px; }
  /* стили для питания */
  .meal-class-row { cursor: pointer; }
  .meal-class-row:hover td { background: rgba(255,255,255,0.08); }
</style>
</head>
<body>
<nav class="nav">
  <div class="nav-brand">🏫 Перекличка</div>
  <a href="/" class="{{ 'active' if page == 'summary' }}">📊 Сводка</a>
  <a href="/requests" class="{{ 'active' if page == 'requests' }}">
    📩 Заявки
    {% if pending_count > 0 %}
      <span style="background:#ff453a;color:#fff;border-radius:10px;padding:1px 7px;font-size:11px;margin-left:4px;">{{ pending_count }}</span>
    {% endif %}
  </a>
  <a href="/meals" class="{{ 'active' if page == 'meals' }}">🍽️ Питание</a>
  <a href="/schools" class="{{ 'active' if page == 'schools' }}">🏫 Школы</a>
  <div style="margin-left:auto;display:flex;align-items:center;gap:8px;">
    <form method="get" action="/switch_school" style="margin:0;">
      <select name="school_id" onchange="this.form.submit()">
        {% for s in all_schools %}
          <option value="{{ s.id }}" {% if s.id == current_school_id %}selected{% endif %}>{{ s.name }}</option>
        {% endfor %}
      </select>
    </form>
  </div>
</nav>

<div class="container">

{% if page == 'summary' %}
  <div class="page-title">📊 Сводка посещаемости</div>
  <div class="glass">
    <div class="toolbar">
      <form method="get" style="display:flex;gap:10px;align-items:center">
        <input type="date" name="date" value="{{ date }}">
        <button type="submit" class="btn btn-primary">Показать</button>
      </form>
      <a href="/download_excel?date={{ date }}" class="btn btn-primary">📥 Excel</a>
    </div>
  </div>
  <div id="stats-block">
    {% if stats %}
    <div class="stats">
      <div class="stat-card"><div class="stat-number">{{ stats.total }}</div><div class="stat-label">Перекличек</div></div>
      <div class="stat-card"><div class="stat-number">{{ stats.absent }}</div><div class="stat-label">Отсутствуют</div></div>
      <div class="stat-card"><div class="stat-number">{{ stats.classes }}</div><div class="stat-label">Классов</div></div>
    </div>
    {% endif %}
  </div>
  <div class="glass" id="summary-table-container">
    {% if data %}
    <table>
      <tr><th>Учитель</th><th>Класс</th><th>Отсутствуют (причина)</th><th>Время</th></tr>
      {% for row in data %}
      <tr>
        <td>{{ row.teacher }}</td>
        <td>{{ row.class }}</td>
        <td style="white-space:pre-line">{{ row.absent }}</td>
        <td style="color:rgba(255,255,255,0.4)">{{ row.time }}</td>
      </tr>
      {% endfor %}
    </table>
    {% else %}
    <div class="empty">Нет данных за эту дату</div>
    {% endif %}
  </div>
  <script>
    const summarySource = new EventSource('/stream?token={{ sse_token }}');
    summarySource.addEventListener('summary_update', async (e) => {
      try {
        const params = new URLSearchParams(window.location.search);
        const dateStr = params.get('date') || new Date().toISOString().slice(0,10);
        const resp = await fetch(`/api/summary?date=${dateStr}`);
        const json = await resp.json();
        updateSummary(json);
      } catch(err) {
        console.error('Не удалось обновить сводку', err);
      }
    });
    function updateSummary(json) {
      const statsContainer = document.getElementById('stats-block');
      const tableContainer = document.getElementById('summary-table-container');
      if (json.stats) {
        statsContainer.innerHTML = `
          <div class="stats">
            <div class="stat-card"><div class="stat-number">${json.stats.total}</div><div class="stat-label">Перекличек</div></div>
            <div class="stat-card"><div class="stat-number">${json.stats.absent}</div><div class="stat-label">Отсутствуют</div></div>
            <div class="stat-card"><div class="stat-number">${json.stats.classes}</div><div class="stat-label">Классов</div></div>
          </div>`;
      } else {
        statsContainer.innerHTML = '';
      }
      if (json.data && json.data.length > 0) {
        let rows = json.data.map(row => `<tr>
          <td>${row.teacher}</td>
          <td>${row.class}</td>
          <td style="white-space:pre-line">${row.absent}</td>
          <td style="color:rgba(255,255,255,0.4)">${row.time}</td>
        </tr>`).join('');
        tableContainer.innerHTML = `<table>
          <tr><th>Учитель</th><th>Класс</th><th>Отсутствуют (причина)</th><th>Время</th></tr>
          ${rows}
        </table>`;
      } else {
        tableContainer.innerHTML = '<div class="empty">Нет данных за эту дату</div>';
      }
    }
  </script>

{% elif page == 'requests' %}
  <div class="page-title">📩 Заявки на доступ</div>
  <div class="glass" id="requests-table-container">
    {% if requests %}
    <table>
      <tr><th>Имя</th><th>Telegram ID</th><th>Роль</th><th>Класс</th><th>Статус</th><th>Действия</th></tr>
      {% for r in requests %}
      <tr>
        <td><b>{{ r.name }}</b></td>
        <td style="color:rgba(255,255,255,0.5);font-family:monospace">{{ r.telegram_id }}</td>
        <td>{{ r.role_label }}</td>
        <td>{{ r.class_name or '—' }}</td>
        <td>
          {% if r.status == 'pending' and r.already_exists %}
            <span class="badge badge-already">⚠️ Уже в системе</span>
          {% elif r.status == 'pending' %}
            <span class="badge badge-pending">⏳ Ожидает</span>
          {% elif r.status == 'approved' %}
            <span class="badge badge-approved">✅ Одобрена</span>
          {% else %}
            <span class="badge badge-rejected">❌ Отклонена</span>
          {% endif %}
        </td>
        <td>
          {% if r.status == 'pending' %}
            {% if r.already_exists %}
              <span style="color:rgba(255,255,255,0.3);font-size:13px">Уже существует</span>
              <form method="post" action="/requests/{{ r.id }}/reject" style="display:inline;margin-left:6px">
                <button type="submit" class="btn btn-danger btn-sm">❌ Отклонить</button>
              </form>
            {% else %}
              <form method="post" action="/requests/{{ r.id }}/approve" style="display:inline">
                <button type="submit" class="btn btn-success btn-sm">✅ Одобрить</button>
              </form>
              <form method="post" action="/requests/{{ r.id }}/reject" style="display:inline;margin-left:6px">
                <button type="submit" class="btn btn-danger btn-sm">❌ Отклонить</button>
              </form>
            {% endif %}
          {% else %}
            <span style="color:rgba(255,255,255,0.25);font-size:13px">Обработана</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>
    {% else %}
    <div class="empty">Новых заявок нет</div>
    {% endif %}
  </div>
  <script>
    const reqSource = new EventSource('/stream?token={{ sse_token }}');
    reqSource.addEventListener('requests_update', async () => {
      try {
        const resp = await fetch('/api/requests');
        const json = await resp.json();
        updateRequests(json);
      } catch(err) {
        console.error('Не удалось обновить заявки', err);
      }
    });
    function updateRequests(requests) {
      const container = document.getElementById('requests-table-container');
      if (!requests || requests.length === 0) {
        container.innerHTML = '<div class="empty">Новых заявок нет</div>';
        return;
      }
      let rows = requests.map(r => {
        let statusHtml = '';
        if (r.status === 'pending' && r.already_exists) {
          statusHtml = '<span class="badge badge-already">⚠️ Уже в системе</span>';
        } else if (r.status === 'pending') {
          statusHtml = '<span class="badge badge-pending">⏳ Ожидает</span>';
        } else if (r.status === 'approved') {
          statusHtml = '<span class="badge badge-approved">✅ Одобрена</span>';
        } else {
          statusHtml = '<span class="badge badge-rejected">❌ Отклонена</span>';
        }
        let actionsHtml = '';
        if (r.status === 'pending') {
          if (r.already_exists) {
            actionsHtml = `<span style="color:rgba(255,255,255,0.3);font-size:13px">Уже существует</span>
              <form method="post" action="/requests/${r.id}/reject" style="display:inline;margin-left:6px">
                <button type="submit" class="btn btn-danger btn-sm">❌ Отклонить</button>
              </form>`;
          } else {
            actionsHtml = `<form method="post" action="/requests/${r.id}/approve" style="display:inline">
                <button type="submit" class="btn btn-success btn-sm">✅ Одобрить</button>
              </form>
              <form method="post" action="/requests/${r.id}/reject" style="display:inline;margin-left:6px">
                <button type="submit" class="btn btn-danger btn-sm">❌ Отклонить</button>
              </form>`;
          }
        } else {
          actionsHtml = '<span style="color:rgba(255,255,255,0.25);font-size:13px">Обработана</span>';
        }
        return `<tr>
          <td><b>${r.name}</b></td>
          <td style="color:rgba(255,255,255,0.5);font-family:monospace">${r.telegram_id}</td>
          <td>${r.role_label}</td>
          <td>${r.class_name || '—'}</td>
          <td>${statusHtml}</td>
          <td>${actionsHtml}</td>
        </tr>`;
      }).join('');
      container.innerHTML = `<table>
        <tr><th>Имя</th><th>Telegram ID</th><th>Роль</th><th>Класс</th><th>Статус</th><th>Действия</th></tr>
        ${rows}
      </table>`;
    }
  </script>

{% elif page == 'meals' %}
  <div class="page-title">🍽️ Питание</div>
  <div class="glass">
    <div class="toolbar">
      <form method="get" style="display:flex;gap:10px;align-items:center">
        <input type="date" name="date" value="{{ date }}">
        <button type="submit" class="btn btn-primary">Показать</button>
      </form>
      <a href="/download_meal_excel?date={{ date }}&type=short" class="btn btn-primary">📥 Краткий Excel</a>
      <a href="/download_meal_excel?date={{ date }}&type=full" class="btn btn-primary">📥 Полный Excel</a>
    </div>
  </div>

  <div id="meals-stats-block" style="margin-bottom:20px;">
    {% if meal_stats %}
    <div class="stats">
      <div class="stat-card"><div class="stat-number">{{ meal_stats.total_classes }}</div><div class="stat-label">Классов подано</div></div>
      <div class="stat-card"><div class="stat-number">{{ meal_stats.total_meals }}</div><div class="stat-label">Всего порций</div></div>
      <div class="stat-card"><div class="stat-number">{{ meal_stats.paid }}</div><div class="stat-label">Платно</div></div>
      <div class="stat-card"><div class="stat-number">{{ meal_stats.free }}</div><div class="stat-label">Бесплатно</div></div>
    </div>
    {% endif %}
  </div>

  <div class="glass" id="meals-table-container">
    {% if meals_data %}
    <table>
      <tr><th>Класс</th><th>Всего</th><th>Платно</th><th>Бесплатно</th><th>Учитель</th></tr>
      {% for row in meals_data %}
      <tr class="meal-class-row" data-class-id="{{ row.class_id }}">
        <td>{{ row.class_name }}</td>
        <td>{{ row.total }}</td>
        <td>{{ row.paid }}</td>
        <td>{{ row.free }}</td>
        <td>{{ row.teacher }}</td>
      </tr>
      {% endfor %}
    </table>
    {% else %}
    <div class="empty">Нет поданных заявок за эту дату</div>
    {% endif %}
  </div>

  <div id="meal-detail-container" style="display:none; margin-top:20px;">
    <div class="glass">
      <table id="meal-detail-table">
        <tr><th>Ученик</th><th>Тип</th><th>Ест</th></tr>
      </table>
    </div>
  </div>

  <script>
    // раскрытие детализации
    document.querySelectorAll('.meal-class-row').forEach(row => {
      row.addEventListener('click', async () => {
        const classId = row.dataset.classId;
        const detailContainer = document.getElementById('meal-detail-container');
        const detailTable = document.getElementById('meal-detail-table');
        if (detailContainer.style.display === 'block' && detailContainer.dataset.currentClass === classId) {
          detailContainer.style.display = 'none';
          return;
        }
        detailContainer.style.display = 'block';
        detailContainer.dataset.currentClass = classId;
        detailTable.innerHTML = '<tr><td colspan="3">Загрузка...</td></tr>';
        try {
          const params = new URLSearchParams(window.location.search);
          const dateStr = params.get('date') || new Date().toISOString().slice(0,10);
          const resp = await fetch(`/api/meals/class?class_id=${classId}&date=${dateStr}`);
          const students = await resp.json();
          if (students.length === 0) {
            detailTable.innerHTML = '<tr><td colspan="3">Нет данных</td></tr>';
          } else {
            let rows = students.map(s => {
              const typeEmoji = s.meal_type === 'paid' ? '💰' : '🆓';
              const eatingIcon = s.is_eating ? '✅' : '❌';
              return `<tr><td>${s.name}</td><td>${typeEmoji} ${s.meal_type === 'paid' ? 'платно' : 'бесплатно'}</td><td>${eatingIcon}</td></tr>`;
            }).join('');
            detailTable.innerHTML = '<tr><th>Ученик</th><th>Тип</th><th>Ест</th></tr>' + rows;
          }
        } catch (err) {
          detailTable.innerHTML = '<tr><td colspan="3">Ошибка загрузки</td></tr>';
        }
      });
    });

    // SSE обновление
    const mealsSource = new EventSource('/stream?token={{ sse_token }}');
    mealsSource.addEventListener('meals_update', async () => {
      try {
        const params = new URLSearchParams(window.location.search);
        const dateStr = params.get('date') || new Date().toISOString().slice(0,10);
        const resp = await fetch(`/api/meals?date=${dateStr}`);
        const json = await resp.json();
        updateMealsTable(json);
      } catch(err) {
        console.error('Не удалось обновить питание', err);
      }
    });
    // обновление при смене школы
    mealsSource.addEventListener('school_switch', async () => {
      try {
        const params = new URLSearchParams(window.location.search);
        const dateStr = params.get('date') || new Date().toISOString().slice(0,10);
        const resp = await fetch(`/api/meals?date=${dateStr}`);
        const json = await resp.json();
        updateMealsTable(json);
      } catch(err) {
        console.error('Не удалось обновить питание после смены школы', err);
      }
    });

    function updateMealsTable(json) {
      const statsContainer = document.getElementById('meals-stats-block');
      const tableContainer = document.getElementById('meals-table-container');
      if (json.stats) {
        statsContainer.innerHTML = `
          <div class="stats">
            <div class="stat-card"><div class="stat-number">${json.stats.total_classes}</div><div class="stat-label">Классов подано</div></div>
            <div class="stat-card"><div class="stat-number">${json.stats.total_meals}</div><div class="stat-label">Всего порций</div></div>
            <div class="stat-card"><div class="stat-number">${json.stats.paid}</div><div class="stat-label">Платно</div></div>
            <div class="stat-card"><div class="stat-number">${json.stats.free}</div><div class="stat-label">Бесплатно</div></div>
          </div>`;
      } else {
        statsContainer.innerHTML = '';
      }
      if (json.data && json.data.length > 0) {
        let rows = json.data.map(row => {
          return `<tr class="meal-class-row" data-class-id="${row.class_id}">
            <td>${row.class_name}</td>
            <td>${row.total}</td>
            <td>${row.paid}</td>
            <td>${row.free}</td>
            <td>${row.teacher}</td>
          </tr>`;
        }).join('');
        tableContainer.innerHTML = `<table>
          <tr><th>Класс</th><th>Всего</th><th>Платно</th><th>Бесплатно</th><th>Учитель</th></tr>
          ${rows}
        </table>`;
        // заново вешаем обработчики клика
        document.querySelectorAll('.meal-class-row').forEach(row => {
          row.addEventListener('click', async () => {
            const classId = row.dataset.classId;
            const detailContainer = document.getElementById('meal-detail-container');
            const detailTable = document.getElementById('meal-detail-table');
            if (detailContainer.style.display === 'block' && detailContainer.dataset.currentClass === classId) {
              detailContainer.style.display = 'none';
              return;
            }
            detailContainer.style.display = 'block';
            detailContainer.dataset.currentClass = classId;
            detailTable.innerHTML = '<tr><td colspan="3">Загрузка...</td></tr>';
            try {
              const params = new URLSearchParams(window.location.search);
              const dateStr = params.get('date') || new Date().toISOString().slice(0,10);
              const resp = await fetch(`/api/meals/class?class_id=${classId}&date=${dateStr}`);
              const students = await resp.json();
              if (students.length === 0) {
                detailTable.innerHTML = '<tr><td colspan="3">Нет данных</td></tr>';
              } else {
                let rows = students.map(s => {
                  const typeEmoji = s.meal_type === 'paid' ? '💰' : '🆓';
                  const eatingIcon = s.is_eating ? '✅' : '❌';
                  return `<tr><td>${s.name}</td><td>${typeEmoji} ${s.meal_type === 'paid' ? 'платно' : 'бесплатно'}</td><td>${eatingIcon}</td></tr>`;
                }).join('');
                detailTable.innerHTML = '<tr><th>Ученик</th><th>Тип</th><th>Ест</th></tr>' + rows;
              }
            } catch (err) {
              detailTable.innerHTML = '<tr><td colspan="3">Ошибка загрузки</td></tr>';
            }
          });
        });
      } else {
        tableContainer.innerHTML = '<div class="empty">Нет поданных заявок за эту дату</div>';
      }
    }
  </script>

{% elif page == 'schools' %}
  <div class="page-title">🏫 Управление школами</div>
  <div class="glass">
    <form method="post" action="/schools" style="display:flex;gap:10px;align-items:center">
      <input type="text" name="name" placeholder="Название школы" required>
      <button type="submit" class="btn btn-primary">➕ Создать</button>
    </form>
  </div>
  <div class="glass">
    {% if schools %}
    <table>
      <tr><th>ID</th><th>Название</th><th>Действия</th></tr>
      {% for s in schools %}
      <tr>
        <td>{{ s.id }}</td>
        <td>{{ s.name }}</td>
        <td><a href="/schools/{{ s.id }}/import" class="btn btn-sm btn-success">📥 Импорт учеников</a></td>
      </tr>
      {% endfor %}
    </table>
    {% else %}
    <div class="empty">Нет зарегистрированных школ</div>
    {% endif %}
  </div>

{% elif page == 'import' %}
  <div class="page-title">📥 Импорт учеников в «{{ school_name }}»</div>
  <div class="glass">
    <form method="post" enctype="multipart/form-data" action="/schools/{{ school_id }}/import">
      <input type="file" name="file" accept=".xlsx" required>
      <button type="submit" class="btn btn-primary">⬆️ Загрузить и импортировать</button>
      <a href="/schools" class="btn btn-sm btn-danger">Отмена</a>
    </form>
  </div>
  {% if result %}
  <div class="glass">
    <p>✅ Импорт завершён.</p>
    <p>Добавлено учеников: {{ result.added }}</p>
    <p>Пропущено дубликатов: {{ result.skipped }}</p>
    <p>Создано новых классов: {{ result.classes_created }}</p>
  </div>
  {% endif %}
{% endif %}

</div>
</body>
</html>"""


def get_web_school_id() -> int:
    return session.get("school_id", DEFAULT_SCHOOL_ID)


def get_all_schools_data() -> list[dict]:
    from repositories import get_all_schools
    return get_all_schools()


def _pending_count(school_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(RegistrationRequest).filter(
            RegistrationRequest.status == "pending",
            RegistrationRequest.school_id == school_id,
        ).count()
    finally:
        db.close()


def _load_sessions(date_str: str, school_id: int) -> list:
    db = SessionLocal()
    try:
        sessions = (
            db.query(AttendanceSession)
            .options(
                joinedload(AttendanceSession.teacher),
                joinedload(AttendanceSession.class_),
                joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
            )
            .filter(
                AttendanceSession.session_date == date_str,
                AttendanceSession.status.in_(["completed", "auto_completed"]),
                AttendanceSession.school_id == school_id,
            )
            .all()
        )
        result = []
        for s in sessions:
            result.append({
                "teacher": s.teacher.name if s.teacher else "?",
                "class": s.class_.name if s.class_ else "?",
                "end_time": s.end_time,
                "absent": [
                    (r.student.name, r.reason)
                    for r in s.records
                    if not r.is_present
                ],
                "class_id": s.class_id,
            })
        return result
    finally:
        db.close()


def _generate_sse_token() -> str:
    """Генерирует случайный токен для SSE, сохраняет в сессию."""
    if 'sse_token' not in session:
        session['sse_token'] = uuid.uuid4().hex
    return session['sse_token']


# ── JSON API ─────────────────────────────────────────────────────────────────

@app.route("/api/summary")
@require_auth
def api_summary():
    school_id = get_web_school_id()
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    raw_sessions = _load_sessions(date_str, school_id)
    rows = []
    for s in raw_sessions:
        absent_entries = s["absent"]
        if absent_entries:
            absent_text = "\n".join(
                f"{escape(name)} — {escape(reason or '—')}" for name, reason in absent_entries
            )
        else:
            absent_text = "нет"
        rows.append({
            "teacher": escape(s["teacher"]),
            "class": escape(s["class"]),
            "absent": absent_text,
            "time": s["end_time"].strftime("%H:%M") if s["end_time"] else "",
        })
    stats = {
        "total": len(raw_sessions),
        "absent": sum(len(s["absent"]) for s in raw_sessions),
        "classes": len({s["class_id"] for s in raw_sessions}),
    } if raw_sessions else None
    return jsonify({"data": rows, "stats": stats})


@app.route("/api/requests")
@require_auth
def api_requests():
    from core.roles import ROLE_LABELS
    school_id = get_web_school_id()
    db = SessionLocal()
    try:
        reqs = (
            db.query(RegistrationRequest)
            .filter(RegistrationRequest.school_id == school_id)
            .order_by(RegistrationRequest.created_at.desc())
            .all()
        )
        active_teacher_ids = {
            row[0]
            for row in db.query(Teacher.telegram_id).filter(
                Teacher.school_id == school_id,
                Teacher.is_active == True,
            ).all()
        }
        result = [
            {
                "id": r.id,
                "name": r.name,
                "telegram_id": r.telegram_id,
                "role_label": ROLE_LABELS.get(r.role, r.role),
                "class_name": r.class_name,
                "status": r.status,
                "already_exists": r.telegram_id in active_teacher_ids,
            }
            for r in reqs
        ]
    finally:
        db.close()
    return jsonify(result)


# ── Обычные страницы ─────────────────────────────────────────────────────────

@app.route("/switch_school")
@require_auth
def switch_school():
    school_id = request.args.get("school_id", DEFAULT_SCHOOL_ID, type=int)
    session["school_id"] = school_id
    _notify_subscribers("school_switch", {"school_id": school_id})
    return redirect(request.referrer or url_for("index"))


@app.route("/")
@require_auth
def index():
    school_id = get_web_school_id()
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    raw_sessions = _load_sessions(date_str, school_id)
    rows = []
    for s in raw_sessions:
        absent_entries = s["absent"]
        if absent_entries:
            absent_text = "\n".join(
                f"{escape(name)} — {escape(reason or '—')}" for name, reason in absent_entries
            )
        else:
            absent_text = "нет"
        rows.append({
            "teacher": escape(s["teacher"]),
            "class": escape(s["class"]),
            "absent": absent_text,
            "time": s["end_time"].strftime("%H:%M") if s["end_time"] else "",
        })
    stats = {
        "total": len(raw_sessions),
        "absent": sum(len(s["absent"]) for s in raw_sessions),
        "classes": len({s["class_id"] for s in raw_sessions}),
    } if raw_sessions else None
    sse_token = _generate_sse_token()
    return render_template_string(
        TEMPLATE, page="summary", data=rows,
        date=date_str, stats=stats,
        pending_count=_pending_count(school_id),
        all_schools=get_all_schools_data(),
        current_school_id=school_id,
        sse_token=sse_token,
    )


@app.route("/requests")
@require_auth
def requests_page():
    from core.roles import ROLE_LABELS
    school_id = get_web_school_id()
    db = SessionLocal()
    try:
        reqs = (
            db.query(RegistrationRequest)
            .filter(RegistrationRequest.school_id == school_id)
            .order_by(RegistrationRequest.created_at.desc())
            .all()
        )
        active_teacher_ids = {
            row[0]
            for row in db.query(Teacher.telegram_id).filter(
                Teacher.school_id == school_id,
                Teacher.is_active == True,
            ).all()
        }
        result = [
            {
                "id": r.id,
                "name": r.name,
                "telegram_id": r.telegram_id,
                "role_label": ROLE_LABELS.get(r.role, r.role),
                "class_name": r.class_name,
                "status": r.status,
                "already_exists": r.telegram_id in active_teacher_ids,
            }
            for r in reqs
        ]
    finally:
        db.close()
    sse_token = _generate_sse_token()
    return render_template_string(
        TEMPLATE, page="requests", requests=result,
        pending_count=_pending_count(school_id),
        all_schools=get_all_schools_data(),
        current_school_id=school_id,
        sse_token=sse_token,
    )


@app.route("/requests/<int:req_id>/approve", methods=["POST"])
@require_auth
def approve_request_web(req_id: int):
    from core.school_context import set_current_school_id
    school_id = get_web_school_id()
    set_current_school_id(school_id)
    from repositories import approve_request
    success = approve_request(req_id)
    if success:
        _notify_subscribers("requests_update")
    return redirect(url_for("requests_page"))


@app.route("/requests/<int:req_id>/reject", methods=["POST"])
@require_auth
def reject_request_web(req_id: int):
    from core.school_context import set_current_school_id
    school_id = get_web_school_id()
    set_current_school_id(school_id)
    from repositories import reject_request
    reject_request(req_id)
    _notify_subscribers("requests_update")
    return redirect(url_for("requests_page"))


@app.route("/schools")
@require_auth
def schools_page():
    schools = get_all_schools_data()
    return render_template_string(
        TEMPLATE, page="schools", schools=schools,
        pending_count=_pending_count(get_web_school_id()),
        all_schools=schools,
        current_school_id=get_web_school_id(),
    )


@app.route("/schools", methods=["POST"])
@require_auth
def create_school_route():
    name = request.form.get("name", "").strip()
    if name:
        from repositories import create_school
        create_school(name)
        _notify_subscribers("schools_update")
    return redirect(url_for("schools_page"))


@app.route("/schools/<int:school_id>/import", methods=["GET", "POST"])
@require_auth
def import_students_route(school_id: int):
    if request.method == "GET":
        schools = get_all_schools_data()
        school_name = next((s["name"] for s in schools if s["id"] == school_id), f"Школа {school_id}")
        return render_template_string(
            TEMPLATE, page="import",
            school_id=school_id, school_name=school_name,
            pending_count=_pending_count(school_id),
            all_schools=schools,
            current_school_id=get_web_school_id(),
        )

    file = request.files.get("file")
    if not file or not file.filename.endswith(".xlsx"):
        return "Ошибка: нужен файл .xlsx", 400

    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = import_from_excel(tmp_path, school_id)
    finally:
        os.unlink(tmp_path)

    schools = get_all_schools_data()
    school_name = next((s["name"] for s in schools if s["id"] == school_id), f"Школа {school_id}")
    return render_template_string(
        TEMPLATE, page="import",
        school_id=school_id, school_name=school_name,
        result=result,
        pending_count=_pending_count(school_id),
        all_schools=schools,
        current_school_id=get_web_school_id(),
    )


@app.route("/download_excel")
@require_auth
def download_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    school_id = get_web_school_id()
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    raw_sessions = _load_sessions(date_str, school_id)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Сводка {date_str}"
    headers = ["Учитель", "Класс", "Отсутствуют (причина)", "Время завершения"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for s in raw_sessions:
        absent_text = "\n".join(
            f"{name} — {reason or '—'}" for name, reason in s["absent"]
        ) if s["absent"] else "нет"
        ws.append([
            s["teacher"],
            s["class"],
            absent_text,
            s["end_time"].strftime("%H:%M") if s["end_time"] else "",
        ])
    for col in ws.columns:
        width = max((len(str(cell.value or "")) for cell in col), default=10) + 2
        ws.column_dimensions[col[0].column_letter].width = width
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"attendance_{date_str}.xlsx",
    )


# ── Питание (вспомогательные функции и маршруты) ─────────────────────────────

def _load_meal_data(date_str: str, school_id: int):
    db = SessionLocal()
    try:
        reqs = (
            db.query(MealRequest)
            .options(
                joinedload(MealRequest.class_),
                joinedload(MealRequest.submitted_by),
                joinedload(MealRequest.items),
            )
            .filter(
                MealRequest.school_id == school_id,
                MealRequest.request_date == date_str,
            )
            .order_by(MealRequest.class_id)
            .all()
        )
        rows = []
        for req in reqs:
            total = len(req.items)
            paid = sum(1 for i in req.items if i.meal_type == "paid")
            free = total - paid
            teacher_name = req.submitted_by.name if req.submitted_by else "—"
            rows.append({
                "class_name": req.class_.name,
                "class_id": req.class_id,
                "total": total,
                "paid": paid,
                "free": free,
                "teacher": teacher_name,
            })
        stats = {
            "total_classes": len(reqs),
            "total_meals": sum(r["total"] for r in rows),
            "paid": sum(r["paid"] for r in rows),
            "free": sum(r["free"] for r in rows),
        } if rows else None
        return rows, stats
    finally:
        db.close()


def _load_class_meal_students(class_id: int, date_str: str, school_id: int):
    db = SessionLocal()
    try:
        req = (
            db.query(MealRequest)
            .options(joinedload(MealRequest.items).joinedload(MealRequestItem.student))
            .filter(
                MealRequest.class_id == class_id,
                MealRequest.request_date == date_str,
                MealRequest.school_id == school_id,
            )
            .first()
        )
        if not req:
            return []
        result = []
        for item in req.items:
            result.append({
                "name": item.student.name,
                "meal_type": item.meal_type,
                "is_eating": item.is_eating,
            })
        return result
    finally:
        db.close()


@app.route("/api/meals")
@require_auth
def api_meals():
    school_id = get_web_school_id()
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    rows, stats = _load_meal_data(date_str, school_id)
    return jsonify({"data": rows, "stats": stats})


@app.route("/api/meals/class")
@require_auth
def api_meals_class():
    school_id = get_web_school_id()
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    class_id = request.args.get("class_id", type=int)
    if not class_id:
        return jsonify([])
    students = _load_class_meal_students(class_id, date_str, school_id)
    return jsonify(students)


@app.route("/meals")
@require_auth
def meals_page():
    school_id = get_web_school_id()
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    rows, stats = _load_meal_data(date_str, school_id)
    sse_token = _generate_sse_token()
    return render_template_string(
        TEMPLATE, page="meals",
        meals_data=rows, meal_stats=stats,
        date=date_str,
        pending_count=_pending_count(school_id),
        all_schools=get_all_schools_data(),
        current_school_id=school_id,
        sse_token=sse_token,
    )


@app.route("/download_meal_excel")
@require_auth
def download_meal_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    school_id = get_web_school_id()
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    export_type = request.args.get("type", "short")

    wb = Workbook()
    # Лист "Сводка"
    ws_summary = wb.active
    ws_summary.title = "Сводка"
    headers = ["Класс", "Всего", "Платно", "Бесплатно", "Учитель"]
    for col, h in enumerate(headers, 1):
        cell = ws_summary.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    rows_summary, _ = _load_meal_data(date_str, school_id)
    for row_data in rows_summary:
        ws_summary.append([
            row_data["class_name"],
            row_data["total"],
            row_data["paid"],
            row_data["free"],
            row_data["teacher"],
        ])
    # автоширина для сводки
    for col in ws_summary.columns:
        width = max((len(str(cell.value or "")) for cell in col), default=10) + 2
        ws_summary.column_dimensions[col[0].column_letter].width = width

    if export_type == "full":
        # Лист "Детализация"
        ws_detail = wb.create_sheet("Детализация")
        detail_headers = ["Класс", "Ученик", "Тип питания", "Ест"]
        for col, h in enumerate(detail_headers, 1):
            cell = ws_detail.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        # Получаем все классы школы
        db = SessionLocal()
        try:
            classes = db.query(Class).filter(Class.school_id == school_id).order_by(Class.name).all()
        finally:
            db.close()
        for cls in classes:
            students = _load_class_meal_students(cls.id, date_str, school_id)
            for s in students:
                meal_type_str = "платно" if s["meal_type"] == "paid" else "бесплатно"
                eating_str = "да" if s["is_eating"] else "нет"
                ws_detail.append([cls.name, s["name"], meal_type_str, eating_str])
        # автоширина для детализации
        for col in ws_detail.columns:
            width = max((len(str(cell.value or "")) for cell in col), default=10) + 2
            ws_detail.column_dimensions[col[0].column_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"meals_{date_str}.xlsx",
    )


# ── SSE и внутренний publish ──────────────────────────────────────────────────

@app.route("/stream")
def stream():
    """SSE endpoint для браузера с проверкой токена из сессии."""
    token = request.args.get("token")
    if not token or token != session.get("sse_token"):
        return Response("Unauthorized", status=403)

    def event_stream():
        q: queue.Queue = queue.Queue()
        with subscribers_lock:
            subscribers.append(q)
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with subscribers_lock:
                subscribers.remove(q)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/_publish", methods=["POST"])
def internal_publish():
    """Только для бота: получает событие и рассылает SSE-клиентам."""
    token = request.headers.get("X-SSE-Token") or request.args.get("token")
    if token != SSE_PUBLISH_TOKEN:
        return jsonify({"error": "unauthorized"}), 403

    payload = request.get_json(silent=True) or {}
    event = payload.get("event", "update")
    data = payload.get("data", {})
    _notify_subscribers(event, data)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)