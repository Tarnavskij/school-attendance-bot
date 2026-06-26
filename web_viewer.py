# web_viewer.py
import io
import functools
from flask import (
    Flask, render_template_string, request, send_file,
    redirect, url_for, session, Response,
)
from markupsafe import escape
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from database import SessionLocal, AttendanceSession, AttendanceRecord, RegistrationRequest, Teacher, Class
from config import DEFAULT_SCHOOL_ID, WEB_USERNAME, WEB_PASSWORD, FLASK_SECRET_KEY
from import_students import import_from_excel

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY


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


# ── Шаблон ────────────────────────────────────────────────────────────────────

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
  {% if stats %}
  <div class="stats">
    <div class="stat-card"><div class="stat-number">{{ stats.total }}</div><div class="stat-label">Перекличек</div></div>
    <div class="stat-card"><div class="stat-number">{{ stats.absent }}</div><div class="stat-label">Отсутствуют</div></div>
    <div class="stat-card"><div class="stat-number">{{ stats.classes }}</div><div class="stat-label">Классов</div></div>
  </div>
  {% endif %}
  <div class="glass">
    {% if data %}
    <table>
      <tr><th>Учитель</th><th>Класс</th><th>Отсутствуют (причина)</th><th>Время</th></tr>
      {% for row in data %}
      <tr>
        <td>{{ row.teacher }}</td>
        <td>{{ row.class }}</td>
        {# absent уже экранирован через escape() в Python, nl2br применён явно #}
        <td style="white-space:pre-line">{{ row.absent }}</td>
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
    """Загружает сессии по session_date (индексируемое поле)."""
    from datetime import date as date_type
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
                AttendanceSession.session_date == date_str,   # индекс по session_date
                AttendanceSession.status.in_(["completed", "auto_completed"]),
                AttendanceSession.school_id == school_id,
            )
            .all()
        )
        # Детачим данные до закрытия сессии
        result = []
        for s in sessions:
            result.append({
                "teacher": s.teacher.name if s.teacher else "?",
                "class": s.class_.name if s.class_ else "?",
                "end_time": s.end_time,
                "records": [(r.student.name, r.reason) for r in s.records],
                "class_id": s.class_id,
            })
        return result
    finally:
        db.close()


@app.route("/switch_school")
@require_auth
def switch_school():
    school_id = request.args.get("school_id", DEFAULT_SCHOOL_ID, type=int)
    session["school_id"] = school_id
    return redirect(request.referrer or url_for("index"))


@app.route("/")
@require_auth
def index():
    from datetime import date
    school_id = get_web_school_id()
    date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    raw_sessions = _load_sessions(date_str, school_id)

    rows = []
    for s in raw_sessions:
        absent = [(name, reason or "—") for name, reason in s["records"] if reason is not None or True]
        absent = [(name, reason) for name, reason in s["records"]]
        absent_entries = [(name, reason or "—") for name, reason in absent if name]

        # XSS-fix: экранируем данные из БД, используем plain text с переносами
        if absent_entries:
            absent_text = "\n".join(
                f"{escape(name)} — {escape(reason)}" for name, reason in absent_entries
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
        "absent": sum(1 for s in raw_sessions for name, _ in s["records"]),
        "classes": len({s["class_id"] for s in raw_sessions}),
    } if raw_sessions else None

    return render_template_string(
        TEMPLATE, page="summary", data=rows,
        date=date_str, stats=stats,
        pending_count=_pending_count(school_id),
        all_schools=get_all_schools_data(),
        current_school_id=school_id,
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
        # Один запрос вместо двух отдельных
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

    return render_template_string(
        TEMPLATE, page="requests", requests=result,
        pending_count=_pending_count(school_id),
        all_schools=get_all_schools_data(),
        current_school_id=school_id,
    )


@app.route("/requests/<int:req_id>/approve", methods=["POST"])
@require_auth
def approve_request_web(req_id: int):
    """Делегируем в репозиторий, чтобы не дублировать бизнес-логику."""
    from core.school_context import set_current_school_id
    school_id = get_web_school_id()
    set_current_school_id(school_id)
    from repositories import approve_request
    approve_request(req_id)
    return redirect(url_for("requests_page"))


@app.route("/requests/<int:req_id>/reject", methods=["POST"])
@require_auth
def reject_request_web(req_id: int):
    from core.school_context import set_current_school_id
    school_id = get_web_school_id()
    set_current_school_id(school_id)
    from repositories import reject_request
    reject_request(req_id)
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
    from datetime import date
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
        absent = [(name, reason or "—") for name, reason in s["records"]]
        absent_text = "\n".join(f"{name} — {reason}" for name, reason in absent) if absent else "нет"
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)