# helpers/quarters.py
from datetime import date

def get_available_quarters(today: date) -> list[dict]:
    """
    Возвращает список начавшихся четвертей текущего учебного года.
    В сентябре добавляет 4-ю четверть прошлого года (если она была).
    """
    y, m = today.year, today.month
    start_year = y if m >= 9 else y - 1

    q_defs = [
        (1, "1-я четверть", date(start_year, 9, 1), date(start_year, 10, 31)),
        (2, "2-я четверть", date(start_year, 11, 1), date(start_year, 12, 31)),
        (3, "3-я четверть", date(start_year + 1, 1, 1), date(start_year + 1, 3, 31)),
        (4, "4-я четверть", date(start_year + 1, 4, 1), date(start_year + 1, 5, 31)),
    ]

    result = []
    for q_id, label, d_from, d_to in q_defs:
        if d_from <= today:
            result.append({
                "id": q_id,
                "label": f"{label} {start_year}-{start_year + 1}",
                "short_label": label,
                "date_from": d_from,
                "date_to": d_to,
            })

    if m == 9:
        prev = start_year - 1
        result.insert(0, {
            "id": 4,
            "label": f"4-я четверть {prev}-{prev + 1}",
            "short_label": "4-я четверть",
            "date_from": date(prev + 1, 4, 1),
            "date_to": date(prev + 1, 5, 31),
        })

    return list(reversed(result))