# web_viewer.py
from flask import Flask, render_template_string, request, send_file, redirect, url_for
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from database import SessionLocal, AttendanceSession, AttendanceRecord, RegistrationRequest, Teacher, Class
from repositories import create_teacher
from core.roles import Role
import io

app = Flask(__name__)

TEMPLATE = """<!DOCTYPE html>
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
    -webkit-backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding: 16px 32px;
    display: flex;
    align-items: center;
    gap: 32px;
    position: sticky;
    top: 0;
    z-index: 100;
  }

  .nav-brand {
    font-size: 18px;
    font-weight: 700;
    background: linear-gradient(135deg, #a78bfa, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.3px;
  }

  .nav a {
    color: rgba(255,255,255,0.6);
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    padding: 6px 14px;
    border-radius: 20px;
    transition: all 0.2s;
  }

  .nav a:hover, .nav a.active {
    color: #fff;
    background: rgba(255,255,255,0.1);
  }

  .container {
    max-width: 1100px;
    margin: 0 auto;
    padding: 32px 24px;
  }

  .page-title {
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 24px;
    letter-spacing: -0.5px;
  }

  .glass {
    background: rgba(255,255,255,0.07);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 20px;
    padding: 24px;
    margin-bottom: 20px;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  input[type="date"] {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 12px;
    padding: 10px 16px;
    color: #e8eaf6;
    font-size: 14px;
    outline: none;
    transition: all 0.2s;
  }

  input[type="date"]:focus {
    border-color: rgba(167,139,250,0.6);
    background: rgba(255,255,255,0.12);
  }

  .btn {
    padding: 10px 20px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 600;
    border: none;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.2s;
  }

  .btn-primary {
    background: linear-gradient(135deg, #a78bfa, #60a5fa);
    color: #fff;
  }

  .btn-primary:hover { opacity: 0.85; transform: translateY(-1px); }

  .btn-success {
    background: rgba(52, 199, 89, 0.2);
    color: #34c759;
    border: 1px solid rgba(52,199,89,0.3);
  }

  .btn-success:hover { background: rgba(52,199,89,0.3); }

  .btn-danger {
    background: rgba(255, 69, 58, 0.2);
    color: #ff453a;
    border: 1px solid rgba(255,69,58,0.3);
  }

  .btn-danger:hover { background: rgba(255,69,58,0.3); }

  .btn-sm { padding: 6px 14px; font-size: 13px; border-radius: 10px; }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  th {
    text-align: left;
    padding: 12px 16px;
    color: rgba(255,255,255,0.4);
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }

  td {
    padding: 14px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    color: rgba(255,255,255,0.85);
  }

  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.03); }

  .badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
  }

  .badge-pending {
    background: rgba(255,214,10,0.15);
    color: #ffd60a;
    border: 1px solid rgba(255,214,10,0.3);
  }

  .badge-approved {
    background: rgba(52,199,89,0.15);
    color: #34c759;
    border: 1px solid rgba(52,199,89,0.3);
  }

  .badge-rejected {
    background: rgba(255,69,58,0.15);
    color: #ff453a;
    border: 1px solid rgba(255,69,58,0.3);
  }

  .badge-already {
    background: rgba(255,159,10,0.15);
    color: #ff9f0a;
    border: 1px solid rgba(255,159,10,0.3);
  }

  .empty {
    text-align: center;
    padding: 60px 20px;
    color: rgba(255,255,255,0.3);
    font-size: 15px;
  }

  .stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }

  .stat-card {
    background: rgba(255,255,255,0.07);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    padding: 20px;
    text-align: center;
  }

  .stat-number {
    font-size: 32px;
    font-weight: 700;
    background: linear-gradient(135deg, #a78bfa, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .stat-label {
    font-size: 13px;
    color: rgba(255,255,255,0.4);
    margin-top: 4px;
  }

  .alert {
    padding: 12px 16px;
    border-radius: 12px;
    font-size: 14px;
    margin-bottom: 16px;
  }

  .alert-warning {
    background: rgba(255,159,10,0.15);
    border: 1px solid rgba(255,159,10,0.3);
    color: #ff9f0a;
  }
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

  {% if stats %}
  <div class="stats">
    <div class="stat-card">
      <div class="stat-number">{{ stats.total }}</div>
      <div class="stat-label">Перекличек</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{{ stats.absent }}</div>
      <div class="stat-label">Отсутствуют</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{{ stats.classes }}</div>
      <div class="stat-label">Классов</div>
    </div>
  </div>
  {% endif %}

  <div class="glass">
    {% if data %}
    <table>
      <tr>
        <th>Учитель</th>
        <th>Класс</th>
        <th>Отсутствуют (причина)</th>
        <th>Время</th>
      </tr>
      {% for row in data %}
      <tr>
        <td>{{ row.teacher }}</td>
        <td>{{ row.class }}</td>
        <td style="line-height:1.6">
          {% if row.absent == "нет" %}
            нет
          {% else %}
            {{ row.absent|safe }}
          {% endif %}
        </td>
        <td style="color:rgba(255,255,255,0.4)">{{ row.time }}</td>
      </tr>
      {% endfor %}
    </table>
    {% else %}
    <div class="empty">Нет данных за эту дату</div>
    {% endif %}
  </div>

{% elif page == 'requests' %}
  <div class="page-title">📩 Заявки на доступ</div>

  <div class="glass">
    {% if requests %}
    <table>
      <tr>
        <th>Имя</th><th>Telegram ID</th><th>Роль</th><th>Класс</th><th>Статус</th><th>Действия</th>
      </tr>
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
              <span style="color:rgba(255,255,255,0.3);font-size:13px">Пользователь уже существует</span>
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

{% endif %}
</div>
</body>
</html>"""


def _pending_count():
    db = SessionLocal()
    count = db.query(RegistrationRequest).filter(RegistrationRequest.status == "pending").count()
    db.close()
    return count


def _load_sessions(date_str: str):
    db = SessionLocal()
    sessions = db.query(AttendanceSession).options(
        joinedload(AttendanceSession.teacher),
        joinedload(AttendanceSession.class_),
        joinedload(AttendanceSession.records).joinedload(AttendanceRecord.student),
    ).filter(
        func.date(AttendanceSession.start_time) == date_str,
        AttendanceSession.status.in_(["completed", "auto_completed"]),
    ).all()
    db.close()
    return sessions


@app.route("/")
def index():
    from datetime import date
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    sessions = _load_sessions(date_str)
    rows = []
    for sess in sessions:
        absent = [(rec.student.name, rec.reason or "—") for rec in sess.records if not rec.is_present]
        if absent:
            absent_lines = [f"{name} — {reason}" for name, reason in absent]
            absent_html = "<br>".join(absent_lines)
        else:
            absent_html = "нет"
        rows.append({
            "teacher": sess.teacher.name if sess.teacher else "?",
            "class":   sess.class_.name  if sess.class_  else "?",
            "absent":  absent_html,
            "time":    sess.end_time.strftime("%H:%M") if sess.end_time else "",
        })
    stats = {
        "total": len(sessions),
        "absent": sum(1 for s in sessions for r in s.records if not r.is_present),
        "classes": len({s.class_id for s in sessions}),
    } if sessions else None

    return render_template_string(TEMPLATE, page="summary", data=rows,
                                  date=date_str, stats=stats,
                                  pending_count=_pending_count())


@app.route("/requests")
def requests_page():
    from core.roles import ROLE_LABELS
    db = SessionLocal()
    reqs = db.query(RegistrationRequest).order_by(RegistrationRequest.created_at.desc()).all()

    # Для каждой pending-заявки проверяем — не существует ли уже такой пользователь
    existing_ids = set(
        t.telegram_id for t in db.query(Teacher.telegram_id).all()
    )

    result = [{
        "id": r.id,
        "name": r.name,
        "telegram_id": r.telegram_id,
        "role_label": ROLE_LABELS.get(r.role, r.role),
        "class_name": r.class_name,
        "status": r.status,
        "already_exists": r.telegram_id in existing_ids,
    } for r in reqs]
    db.close()
    return render_template_string(TEMPLATE, page="requests", requests=result,
                                  pending_count=_pending_count())


@app.route("/requests/<int:req_id>/approve", methods=["POST"])
def approve_request(req_id: int):
    from core.roles import ROLE_LABELS
    db = SessionLocal()
    req = db.query(RegistrationRequest).filter(RegistrationRequest.id == req_id).first()
    if req and req.status == "pending":
        # Защита от дубликата — проверяем перед INSERT
        already = db.query(Teacher).filter(Teacher.telegram_id == req.telegram_id).first()
        if already:
            # Пользователь уже есть — просто закрываем заявку
            req.status = "approved"
            db.commit()
            db.close()
            return redirect(url_for("requests_page"))

        class_id = None
        if req.class_name:
            c = db.query(Class).filter(Class.name == req.class_name).first()
            if c:
                class_id = c.id
        teacher = Teacher(telegram_id=req.telegram_id, name=req.name,
                          role=req.role, class_id=class_id)
        db.add(teacher)
        req.status = "approved"
        db.commit()
    db.close()
    return redirect(url_for("requests_page"))


@app.route("/requests/<int:req_id>/reject", methods=["POST"])
def reject_request(req_id: int):
    db = SessionLocal()
    req = db.query(RegistrationRequest).filter(RegistrationRequest.id == req_id).first()
    if req and req.status == "pending":
        req.status = "rejected"
        db.commit()
    db.close()
    return redirect(url_for("requests_page"))


@app.route("/download_excel")
def download_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    from datetime import date
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    sessions = _load_sessions(date_str)
    wb = Workbook()
    ws = wb.active
    ws.title = f"Сводка {date_str}"
    headers = ["Учитель", "Класс", "Отсутствуют (причина)", "Время завершения"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for sess in sessions:
        absent = [(rec.student.name, rec.reason or "—") for rec in sess.records if not rec.is_present]
        if absent:
            absent_text = "\n".join(f"{name} — {reason}" for name, reason in absent)
        else:
            absent_text = "нет"
        ws.append([
            sess.teacher.name if sess.teacher else "?",
            sess.class_.name  if sess.class_  else "?",
            absent_text,
            sess.end_time.strftime("%H:%M") if sess.end_time else "",
        ])
    for col in ws.columns:
        width = max((len(str(cell.value or "")) for cell in col), default=10) + 2
        ws.column_dimensions[col[0].column_letter].width = width
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True,
                     download_name=f"attendance_{date_str}.xlsx")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)