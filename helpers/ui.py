# helpers/ui.py
"""
Управление «рабочим сообщением» раздела.

Соглашение: в FSM-state по ключу "screen_msg_id" хранится id сообщения,
которое сейчас служит рабочим экраном раздела. Все шаги раздела
(выбор, отметка, отправка) редактируют его через edit_text / edit_reply_markup.

При входе в новый раздел — старое рабочее сообщение удаляется, чтобы
в чате не копились «мёртвые» экраны.
"""
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

# Имена FSM-состояний, в которых при выходе надо подчистить БД.
# Хранятся строкой, чтобы не импортировать StatesGroup из хендлеров
# (это создало бы циклический импорт).
_STATE_ATTENDANCE_MARKING = "AttendanceStates:marking"


async def reset_screen(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """
    Удаляет текущее рабочее сообщение (если было) и очищает FSM-state.

    Перед очисткой подчищает незавершённые операции:
      • активная перекличка (AttendanceStates.marking) — удаляется сессия,
        иначе класс остаётся «уже отмеченным» до конца дня.

    Безопасно вызывать даже если ничего не сохранено.
    """
    data = await state.get_data()
    current = await state.get_state()
    old_id = data.get("screen_msg_id")

    if current == _STATE_ATTENDANCE_MARKING:
        session_id = data.get("session_id")
        if session_id:
            from repositories import delete_session
            try:
                delete_session(session_id)
            except Exception:
                pass

    await state.clear()

    if old_id:
        try:
            await bot.delete_message(chat_id, old_id)
        except TelegramBadRequest:
            pass


async def set_screen(state: FSMContext, message_id: int) -> None:
    """Запоминает id текущего рабочего сообщения в state."""
    await state.update_data(screen_msg_id=message_id)