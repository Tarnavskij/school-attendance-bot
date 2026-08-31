# handlers/director.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import date

from services import ReportService
from repositories import get_all_classes, get_absent_students_today, get_default_school_id
from core.keyboards import (
    BTN_SCHOOL_SUMMARY, BTN_DIRECTOR_CLASSES, BTN_ATTENDANCE_GRAPH,
    start_kb, back_to_menu_btn
)
from core.roles import check_access, Role
from core.school_context import get_school_id_for_admin
# Импорт для подключения к Sigur
from sigur_reader import get_sigur_connection

director_router = Router()


@director_router.message(F.text == BTN_SCHOOL_SUMMARY)
async def school_summary(message: Message) -> None:
    if not check_access(message.from_user.id, [Role.DIRECTOR]):
        await message.answer("Нет доступа.")
        return
    summary = ReportService.get_daily_summary(date.today())
    await message.answer(summary, reply_markup=start_kb)


@director_router.message(F.text == BTN_DIRECTOR_CLASSES)
async def director_classes(message: Message) -> None:
    if not check_access(message.from_user.id, [Role.DIRECTOR]):
        await message.answer("Нет доступа.")
        return
    await _show_class_list(message)


async def _show_class_list(target, edit: bool = False) -> None:
    from repositories import get_teacher_by_telegram_id
    user_id = target.from_user.id if hasattr(target, 'from_user') else None
    if user_id:
        teacher = get_teacher_by_telegram_id(user_id)
        school_id = teacher.school_id if teacher else get_school_id_for_admin(user_id)
    else:
        school_id = get_default_school_id()

    classes = get_all_classes(school_id)
    if not classes:
        text = "Нет классов в базе."
        kb = InlineKeyboardMarkup(inline_keyboard=[[back_to_menu_btn()]])
    else:
        text = "🏫 Выберите класс для просмотра отсутствующих сегодня:"
        kb = _build_class_grid_keyboard(classes, callback_prefix="dir:view")

    if edit:
        await target.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


def _build_class_grid_keyboard(classes, callback_prefix: str) -> InlineKeyboardMarkup:
    groups: dict[int, list] = {}
    for c in classes:
        grade = c.grade or 0
        groups.setdefault(grade, []).append(c)

    rows = []
    for grade in sorted(groups.keys()):
        buttons = [InlineKeyboardButton(text=c.name, callback_data=f"{callback_prefix}:{c.id}") for c in groups[grade]]
        rows.append(buttons)

    rows.append([back_to_menu_btn()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@director_router.callback_query(F.data.startswith("dir:view:"))
async def view_class_absences(callback: CallbackQuery) -> None:
    if not check_access(callback.from_user.id, [Role.DIRECTOR]):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    class_id = int(callback.data.split(":")[-1])
    await _show_absent_readonly(callback.message, class_id, callback.from_user.id)
    await callback.answer()


@director_router.callback_query(F.data == "dir:back_classes")
async def back_to_class_list(callback: CallbackQuery) -> None:
    if not check_access(callback.from_user.id, [Role.DIRECTOR]):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await _show_class_list(callback.message, edit=True)
    await callback.answer()


async def _show_absent_readonly(message: Message, class_id: int, user_id: int) -> None:
    today = date.today()
    from repositories import get_teacher_by_telegram_id
    teacher = get_teacher_by_telegram_id(user_id)
    school_id = teacher.school_id if teacher else get_school_id_for_admin(user_id)

    absent = get_absent_students_today(class_id, today, school_id=school_id)

    classes = get_all_classes(school_id)
    class_obj = next((c for c in classes if c.id == class_id), None)
    class_name = class_obj.name if class_obj else "?"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ К классам", callback_data="dir:back_classes")],
        [back_to_menu_btn()],
    ])

    if not absent:
        text = f"📋 В классе {class_name} сегодня отсутствующих нет."
    else:
        lines = [f"📋 Отсутствующие в классе {class_name}:"]
        for info in absent.values():
            reason = info["reason"] or "причина не указана"
            lines.append(f"• {info['name']} — {reason}")
        text = "\n".join(lines)

    await message.edit_text(text, reply_markup=kb)


# ===== НОВЫЙ ХЕНДЛЕР ДЛЯ КНОПКИ "ГРАФИК" =====

@director_router.message(F.text == BTN_ATTENDANCE_GRAPH)
async def attendance_graph(message: Message) -> None:
    if not check_access(message.from_user.id, [Role.DIRECTOR]):
        await message.answer("Нет доступа.")
        return

    today = date.today().strftime('%Y-%m-%d')

    try:
        with get_sigur_connection() as conn:
            with conn.cursor() as cur:
                sql = """
                    SELECT 
                        p.NAME AS employee_name,
                        MIN(CASE WHEN l.DIRECTION = 2 THEN l.LOGTIME END) AS first_entry,
                        MAX(CASE WHEN l.DIRECTION = 1 THEN l.LOGTIME END) AS last_exit
                    FROM `tc-db-log`.`v_logs` l
                    LEFT JOIN `tc-db-main`.`personal` p ON l.EMPHINT = p.ID
                    WHERE l.ACCESS_OBJECT_TYPE_ID = 'EMP'
                      AND DATE(l.LOGTIME) = %s
                      AND l.DIRECTION IN (1, 2)
                    GROUP BY p.NAME
                """
                cur.execute(sql, (today,))
                rows = cur.fetchall()

                if not rows:
                    await message.answer("📅 За сегодня событий нет.")
                    return

                lines = [f"📅 График посещаемости за {today}:"]
                for row in rows:
                    name = row['employee_name'] or 'Неизвестно'
                    first = row['first_entry'].strftime('%H:%M') if row['first_entry'] else '—'
                    last = row['last_exit'].strftime('%H:%M') if row['last_exit'] else '—'
                    lines.append(f"• {name}: вход {first}, выход {last}")

                await message.answer("\n".join(lines))
    except Exception as e:
        await message.answer(f"⚠️ Ошибка при получении данных: {e}")