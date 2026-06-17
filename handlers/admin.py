# handlers/admin.py
import io
from datetime import date

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from repositories import (
    get_all_teachers, delete_teacher,
    update_teacher_role, update_teacher_class,
    get_all_classes, get_students_by_class,
    create_student, delete_student,
    get_sessions_for_report, get_teacher_card,
    get_pending_requests, approve_request, reject_request,
)
from database import Teacher, SessionLocal
from services import ReportService
from core.keyboards import BTN_SCHOOL_SUMMARY, BTN_TEACHER_LIST, BTN_STUDENTS, build_menu_keyboard
from core.roles import is_admin, ALL_ROLES, ROLE_LABELS, Role
from config import ADMIN_TELEGRAM_ID

admin_router = Router()


class AddStudentStates(StatesGroup):
    waiting_name = State()


# ===== Сводка по школе =====
@admin_router.message(F.text == BTN_SCHOOL_SUMMARY)
async def school_summary(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    summary = ReportService.get_daily_summary(date.today())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать Excel", callback_data="admin:excel")],
    ])
    await message.answer(summary, reply_markup=kb)


@admin_router.callback_query(F.data == "admin:excel")
async def download_excel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("Формирую файл…")
    sessions = get_sessions_for_report(date.today())
    file_bytes = _build_excel(sessions, date.today().strftime("%Y-%m-%d"))
    document = BufferedInputFile(file_bytes, filename=f"attendance_{date.today()}.xlsx")
    await callback.message.answer_document(document, caption=f"📅 Сводка за {date.today().strftime('%d.%m.%Y')}")


def _build_excel(sessions, date_str: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"Сводка {date_str}"
    headers = ["Учитель", "Класс", "Отсутствуют", "Причины", "Время завершения"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for sess in sessions:
        absent_str = ", ".join(n for n, _ in sess.absent) if sess.absent else "нет"
        reasons_str = ", ".join(r or "—" for _, r in sess.absent) if sess.absent else ""
        end_time = sess.end_time.strftime("%H:%M") if sess.end_time else ""
        ws.append([sess.teacher_name, sess.class_name, absent_str, reasons_str, end_time])
    for col in ws.columns:
        width = max((len(str(cell.value or "")) for cell in col), default=10) + 2
        ws.column_dimensions[col[0].column_letter].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ===== Список пользователей (учителей) =====
@admin_router.message(F.text == BTN_TEACHER_LIST)
async def teacher_list(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await _show_teacher_list(message)


async def _show_teacher_list(target, edit: bool = False) -> None:
    teachers = get_all_teachers()
    text = "👨‍🏫 Управление пользователями:"
    kb = _teacher_list_keyboard(teachers)
    if edit:
        await target.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


def _teacher_list_keyboard(teachers) -> InlineKeyboardMarkup:
    rows = []
    for t in teachers:
        label = f"{t.name} · {ROLE_LABELS.get(t.role, t.role)} · {t.class_name or 'нет'}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admin:teacher:{t.id}")])
    rows.append([InlineKeyboardButton(text="📩 Заявки", callback_data="admin:requests")])
    rows.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@admin_router.callback_query(F.data == "admin:back_teachers")
async def back_to_teacher_list(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await _show_teacher_list(callback.message, edit=True)
    await callback.answer()


# ---------- Заявки ----------
@admin_router.callback_query(F.data == "admin:requests")
async def show_requests(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    requests = get_pending_requests()
    if not requests:
        await callback.message.edit_text(
            "📩 Нет активных заявок.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin:back_teachers")]
            ])
        )
        await callback.answer()
        return

    text = "📩 Активные заявки:"
    kb = []
    for r in requests:
        kb.append([InlineKeyboardButton(
            text=f"{r['name']} ({r['role_label']}, {r['class_name'] or 'класс не выбран'})",
            callback_data=f"admin:request:{r['id']}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin:back_teachers")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:request:"))
async def request_detail(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    req_id = int(callback.data.split(":")[-1])
    requests = get_pending_requests()
    req = next((r for r in requests if r['id'] == req_id), None)
    if not req:
        await callback.answer("Заявка не найдена.")
        return

    text = (
        f"📩 Заявка от {req['name']}\n"
        f"ID: {req['telegram_id']}\n"
        f"Роль: {req['role_label']}\n"
        f"Класс: {req['class_name'] or 'не выбран'}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin:approve:{req_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:reject:{req_id}")],
        [InlineKeyboardButton(text="🔙 К списку заявок", callback_data="admin:requests")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:approve:"))
async def approve_request_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    req_id = int(callback.data.split(":")[-1])
    success = approve_request(req_id)
    if success:
        await callback.answer("✅ Заявка одобрена, пользователь добавлен.")
    else:
        await callback.answer("❌ Ошибка при одобрении.")
    await show_requests(callback)


@admin_router.callback_query(F.data.startswith("admin:reject:"))
async def reject_request_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    req_id = int(callback.data.split(":")[-1])
    reject_request(req_id)
    await callback.answer("Заявка отклонена.")
    await show_requests(callback)


# ===== Карточка учителя (управление) =====
@admin_router.callback_query(F.data.startswith("admin:teacher:"))
async def teacher_card(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    teacher_id = int(callback.data.split(":")[-1])
    await _show_teacher_card(callback.message, teacher_id)
    await callback.answer()


async def _show_teacher_card(message, teacher_id: int) -> None:
    t = get_teacher_card(teacher_id)
    if not t:
        await message.edit_text("Пользователь не найден.")
        return
    text = (f"👤 {t.name} (ID: {t.telegram_id})\n"
            f"Роль: {ROLE_LABELS.get(t.role, t.role)}\n"
            f"Класс: {t.class_name or 'нет'}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сменить роль",    callback_data=f"admin:chrole:{teacher_id}")],
        [InlineKeyboardButton(text="🏫 Назначить класс", callback_data=f"admin:setclass:{teacher_id}")],
        [InlineKeyboardButton(text="🚫 Убрать класс",    callback_data=f"admin:rmclass:{teacher_id}")],
        [InlineKeyboardButton(text="🗑 Удалить",          callback_data=f"admin:delteacher:{teacher_id}")],
        [InlineKeyboardButton(text="↩️ Назад к списку",  callback_data="admin:back_teachers")],
    ])
    await message.edit_text(text, reply_markup=kb)


@admin_router.callback_query(F.data.startswith("admin:rmclass:"))
async def remove_class(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    teacher_id = int(callback.data.split(":")[-1])
    update_teacher_class(teacher_id, None)
    await callback.answer("Класс снят.")
    await _show_teacher_card(callback.message, teacher_id)


@admin_router.callback_query(F.data.startswith("admin:delteacher:"))
async def delete_teacher_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    teacher_id = int(callback.data.split(":")[-1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin:delconfirm:{teacher_id}")],
        [InlineKeyboardButton(text="❌ Отмена",       callback_data=f"admin:teacher:{teacher_id}")],
    ])
    await callback.message.edit_text("Удалить пользователя? Это действие необратимо.", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:delconfirm:"))
async def delete_teacher_execute(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    teacher_id = int(callback.data.split(":")[-1])
    delete_teacher(teacher_id)
    await callback.answer("Пользователь удалён.")
    await _show_teacher_list(callback.message, edit=True)


@admin_router.callback_query(F.data.startswith("admin:chrole:"))
async def change_role_menu(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    teacher_id = int(callback.data.split(":")[-1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        *[[InlineKeyboardButton(text=ROLE_LABELS[r], callback_data=f"admin:setrole:{teacher_id}:{r}")] for r in ALL_ROLES],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin:teacher:{teacher_id}")],
    ])
    await callback.message.edit_text("Выберите новую роль:", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:setrole:"))
async def set_role(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    teacher_id = int(parts[2])
    new_role = parts[3]
    update_teacher_role(teacher_id, new_role)
    await callback.answer("Роль изменена.")
    await _show_teacher_card(callback.message, teacher_id)


@admin_router.callback_query(F.data.startswith("admin:setclass:"))
async def set_class_menu(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    teacher_id = int(callback.data.split(":")[-1])
    classes = get_all_classes()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        *[[InlineKeyboardButton(text=c.name, callback_data=f"admin:assignclass:{teacher_id}:{c.id}")] for c in classes],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin:teacher:{teacher_id}")],
    ])
    await callback.message.edit_text("Выберите класс:", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:assignclass:"))
async def assign_class(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    teacher_id = int(parts[2])
    class_id = int(parts[3])
    update_teacher_class(teacher_id, class_id)
    await callback.answer("Класс назначен.")
    await _show_teacher_card(callback.message, teacher_id)


# ===== Ученики =====
@admin_router.message(F.text == BTN_STUDENTS)
async def students_menu(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await _show_classes_for_students(message)


async def _show_classes_for_students(target, edit: bool = False) -> None:
    classes = get_all_classes()
    if not classes:
        text = "Нет классов в базе."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Меню", callback_data="nav:menu")]])
    else:
        text = "🎓 Выберите класс для управления учениками:"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            *[[InlineKeyboardButton(text=c.name, callback_data=f"admin:students:{c.id}")] for c in classes],
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")],
        ])
    if edit:
        await target.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


@admin_router.callback_query(F.data.startswith("admin:students:"))
async def show_students(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    class_id = int(callback.data.split(":")[-1])
    await _show_student_list(callback.message, class_id)
    await callback.answer()


async def _show_student_list(message, class_id: int) -> None:
    students = get_students_by_class(class_id)
    classes = get_all_classes()
    class_obj = next((c for c in classes if c.id == class_id), None)
    class_name = class_obj.name if class_obj else "?"
    rows = [[InlineKeyboardButton(text=f"🗑 {s.name}", callback_data=f"admin:delstudent:{s.id}:{class_id}")]
            for s in students]
    rows.append([InlineKeyboardButton(text="➕ Добавить ученика", callback_data=f"admin:addstudent:{class_id}")])
    rows.append([InlineKeyboardButton(text="↩️ К классам", callback_data="admin:back_classes")])
    rows.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="nav:menu")])
    await message.edit_text(f"🎓 Ученики класса {class_name} ({len(students)} чел.):",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@admin_router.callback_query(F.data == "admin:back_classes")
async def back_to_classes(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await _show_classes_for_students(callback.message, edit=True)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:addstudent:"))
async def add_student_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    class_id = int(callback.data.split(":")[-1])
    await state.update_data(class_id=class_id)
    await state.set_state(AddStudentStates.waiting_name)
    await callback.message.answer("Введите имя и фамилию ученика:")
    await callback.answer()


@admin_router.message(AddStudentStates.waiting_name)
async def process_student_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    data = await state.get_data()
    class_id = data["class_id"]
    create_student(name=name, class_id=class_id)
    await state.clear()
    await message.answer(f"✅ Ученик «{name}» добавлен.")
    students = get_students_by_class(class_id)
    classes = get_all_classes()
    class_obj = next((c for c in classes if c.id == class_id), None)
    class_name = class_obj.name if class_obj else "?"
    rows = [[InlineKeyboardButton(text=f"🗑 {s.name}", callback_data=f"admin:delstudent:{s.id}:{class_id}")]
            for s in students]
    rows.append([InlineKeyboardButton(text="➕ Добавить ученика", callback_data=f"admin:addstudent:{class_id}")])
    rows.append([InlineKeyboardButton(text="↩️ К классам", callback_data="admin:back_classes")])
    await message.answer(f"🎓 Ученики класса {class_name}:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@admin_router.callback_query(F.data.startswith("admin:delstudent:"))
async def delete_student_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    student_id = int(parts[2])
    class_id = int(parts[3])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin:delstudentok:{student_id}:{class_id}")],
        [InlineKeyboardButton(text="❌ Отмена",       callback_data=f"admin:students:{class_id}")],
    ])
    await callback.message.edit_text("Удалить ученика?", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:delstudentok:"))
async def delete_student_execute(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    student_id = int(parts[2])
    class_id = int(parts[3])
    delete_student(student_id)
    await callback.answer("Ученик удалён.")
    await _show_student_list(callback.message, class_id)


@admin_router.message(Command("restore_admin"))
async def restore_admin(message: Message) -> None:
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        await message.answer("Нет доступа.")
        return
    db = SessionLocal()
    teacher = db.query(Teacher).filter(Teacher.telegram_id == ADMIN_TELEGRAM_ID).first()
    if teacher:
        teacher.role = Role.ADMIN
        db.commit()
        await message.answer("Роль администратора восстановлена. Нажмите /menu.")
    else:
        await message.answer("Вы не найдены в базе.")
    db.close()