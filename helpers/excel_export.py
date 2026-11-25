# helpers/excel_export.py
import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment


def generate_absences_excel(data: dict, title_info: str = "Все классы") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Пропуски"

    # Заголовок отчета
    ws.cell(row=1, column=1, value=f"Отчет по пропускам: {title_info}").font = Font(bold=True, size=12)

    headers = ["Класс", "ФИО", "Всего", "По болезни", "На оздоровлении",
               "По заявлению", "По приказу", "Без уважительной"]

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    row_num = 4
    for class_name, students in data.items():
        for s in students:
            ws.cell(row=row_num, column=1, value=class_name)
            ws.cell(row=row_num, column=2, value=s["name"])
            ws.cell(row=row_num, column=3, value=s["total"])
            ws.cell(row=row_num, column=4, value=s["sick"])
            ws.cell(row=row_num, column=5, value=s["recuperation"])
            ws.cell(row=row_num, column=6, value=s["statement"])
            ws.cell(row=row_num, column=7, value=s["order"])
            ws.cell(row=row_num, column=8, value=s["unexcused"])
            row_num += 1

    for col in ws.columns:
        width = max((len(str(cell.value or "")) for cell in col), default=10) + 2
        ws.column_dimensions[col[0].column_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def generate_class_summary_excel(rows: list[dict], title_info: str = "Все классы") -> bytes:
    """
    Сводный Excel по классам: одна строка на класс, суммы по причинам.
    Используется для отчёта «Все классы» в веб-панели.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Сводка по классам"

    ws.cell(row=1, column=1, value=f"Отчет по пропускам: {title_info}").font = Font(bold=True, size=12)

    headers = ["Класс", "Учеников", "Всего", "По болезни", "На оздоровлении",
               "По заявлению", "По приказу", "Без уважительной"]

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    row_num = 4
    for r in rows:
        ws.cell(row=row_num, column=1, value=r['class_name'])
        ws.cell(row=row_num, column=2, value=r['students_count'])
        ws.cell(row=row_num, column=3, value=r['total'])
        ws.cell(row=row_num, column=4, value=r['sick'])
        ws.cell(row=row_num, column=5, value=r['recuperation'])
        ws.cell(row=row_num, column=6, value=r['statement'])
        ws.cell(row=row_num, column=7, value=r['order'])
        ws.cell(row=row_num, column=8, value=r['unexcused'])
        row_num += 1

    for col in ws.columns:
        width = max((len(str(cell.value or "")) for cell in col), default=10) + 2
        ws.column_dimensions[col[0].column_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()