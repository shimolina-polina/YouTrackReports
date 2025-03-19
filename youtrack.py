from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth
import time
import math
from docx import Document
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

login = None
password = None


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Привет! Используйте команду /login для авторизации, укажите почту и пароль вашей учетной записи YouTrack. Используйте команду /generate для создания документа. Укажите период: /generate YYYY-MM-DD YYYY-MM-DD')

async def login(update: Update, context: CallbackContext) -> None:
    login = context.args[0]
    password = context.args[1]
    try:
        response = requests.get('https://youtrack.advalange.com/api/users/me', auth=HTTPBasicAuth(login, password))
        response.raise_for_status()
        user_data = response.json()
    
        user_id = user_data.get('id')

        context.user_data['id'] = user_id
        context.user_data['login'] = login
        context.user_data['password'] = password
        await update.message.reply_text('Спасибо за авторизацию!')

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            await update.message.reply_text('Ошибка: Вы не авторизованы.')
        else:
            await update.message.reply_text(f'Ошибка: {e.response.status_code} - {e.response.text}')
    except Exception as e:
        await update.message.reply_text(f'Произошла ошибка: {e}')
   


async def generate_document(update: Update, context: CallbackContext) -> None:
    base_url = f"https://youtrack.advalange.com/api/workItems"

    try:
        start_date = datetime.strptime(context.args[0], '%Y-%m-%d').date().isoformat()  # Формат YYYY-MM-DD
        end_date = datetime.strptime(context.args[1], '%Y-%m-%d').date().isoformat()    # Формат YYYY-MM-DD
    except (ValueError, IndexError):
        await update.message.reply_text('Неверный формат даты. Используйте формат: YYYY-MM-DD YYYY-MM-DD')
        return
    id = context.user_data.get('id')
    login = context.user_data.get('login')
    password = context.user_data.get('password')
    params = {
            "$top": 1000,
            "fields": "duration(minutes),issue(summary,project(name))",
            "endDate": end_date,
            "startDate": start_date,
            "creator": id
        }

    if login == None or password == None:
        await update.message.reply_text('Пожалуйста, авторизуйтесь.')
        return

    if len(context.args) != 2:
        await update.message.reply_text('Пожалуйста, укажите начальную и конечную даты в формате: YYYY-MM-DD YYYY-MM-DD')
        return
    
    issueDictionary = {}

    try:
        response = requests.get(base_url, params=params, auth=HTTPBasicAuth(login, password))

        print(f"Response status code: {response.status_code}")
        print(f"Response text: {response.text}")
        response.raise_for_status()

        work_items = response.json()

        if not work_items:
            await update.message.reply_text('Нет задач за указанный период.')
            return

        for work_item in work_items:
            project_name = work_item.get('issue', {}).get('project', {}).get('name')
            issue_summary = work_item.get('issue', {}).get('summary')
            duration_minutes = work_item.get('duration', {}).get('minutes', 0)

            if project_name not in issueDictionary:
                issueDictionary[project_name] = {}

            if issue_summary in issueDictionary[project_name]:
                issueDictionary[project_name][issue_summary] += duration_minutes
            else:
                issueDictionary[project_name][issue_summary] = duration_minutes

        hours_sum = sum(sum(issues.values()) for issues in issueDictionary.values()) / 60

        print(issueDictionary)

        print(hours_sum)

    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f'Ошибка при выполнении запроса: {e}')
    doc = Document()

    if issueDictionary:

        table = doc.add_table(rows=1, cols=3)

        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = '№ п\п'
        hdr_cells[1].text = 'Наименование и виды работ, услуг'
        hdr_cells[2].text = 'Кол-во часов'

        row_number = 1

        for project, issues in issueDictionary.items():
            for issue, duration_minutes in issues.items():
                row_cells = table.add_row().cells
                row_cells[0].text = str(row_number)
                row_cells[1].text = f"[{project}] {issue}"
                row_cells[2].text = f"{duration_minutes / 60}"

                row_number += 1
        row_cells = table.add_row().cells
        row_cells[1].text = 'Всего:'
        row_cells[2].text = f"{hours_sum}"

    document_path = 'issue_dictionary.docx'
    doc.save(document_path)

    with open(document_path, 'rb') as file:
        await update.message.reply_document(file, caption="Ваш документ с задачами!")

def main() -> None:
    application = ApplicationBuilder().token("7516898139:AAElhtK7hnrjWkwOK9_Xlmd4cqKGadiogC8").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("generate", generate_document))

    application.run_polling()

    
if __name__ == '__main__':
    main()