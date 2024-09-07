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
        response = requests.get('https://youtrack.{{BASE_PATH}}.com/api/users/me', auth=HTTPBasicAuth(login, password))
        response.raise_for_status()
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
    base_url = f'https://youtrack.{{BASE_PATH}}.com/api/issues'

    fields = 'idReadable,project(name),summary'
    query = '(for:%20me) or (Reviewer:%20me)'
    top = 40
    skip = 0

    max_retries = 5
    retry_delay = 2
    login = context.user_data.get('login')
    password = context.user_data.get('password')

    if login == None or password == None:
        await update.message.reply_text('Пожалуйста, авторизуйтесь.')
        return

    if len(context.args) != 2:
        await update.message.reply_text('Пожалуйста, укажите начальную и конечную даты в формате: YYYY-MM-DD YYYY-MM-DD')
        return
    
    try:
        start_date = datetime.strptime(context.args[0], '%Y-%m-%d')
        end_date = datetime.strptime(context.args[1], '%Y-%m-%d')
    except ValueError:
        await update.message.reply_text('Неверный формат даты. Используйте формат: YYYY-MM-DD')
        return

    issueDictionary = {}

    while True:
        url = f'{base_url}?fields={fields}&query={query}&$skip={skip}&$top={top}'
        
        try:
            response = requests.get(url, auth=HTTPBasicAuth(login, password))
            response.raise_for_status()

            issues = response.json()
            
            if not issues:
                break

            for issue in issues:
                issue_id = issue.get('idReadable')
                time_tracking_url = f'https://youtrack.{{BASE_PATH}}.com/api/issues/{issue_id}/timeTracking?fields=workItems(author(login),date,duration(minutes))'
                retries = 0
                while retries < max_retries:
                    try:
                        response = requests.get(time_tracking_url, auth=HTTPBasicAuth(login, password))
                        response.raise_for_status()

                        timeTrackingData = response.json()

                        if 'workItems' in timeTrackingData:
                            for work_item in timeTrackingData['workItems']:
                                author_login = work_item.get('author', {}).get('login')
                                work_item_date = work_item.get('date')
                                duration_minutes = work_item.get('duration', {}).get('minutes')

                                if (
                                    author_login == 'Polina.Shimolina' 
                                    and work_item_date is not None 
                                    and start_date <= datetime.utcfromtimestamp(work_item_date / 1000.0) <= end_date
                                ):
                                    
                                    project_name = issue.get('project', {}).get('name')

                                    if project_name not in issueDictionary:
                                        issueDictionary[project_name] = []

                                    task_exists = False
                                    for task in issueDictionary[project_name]:
                                        if task['summary'] == issue.get('summary'):
                                            task['spent_hours'] += duration_minutes
                                            task_exists = True
                                            break
                                    
                                    if not task_exists:
                                        issueDictionary[project_name].append({
                                            'summary': issue.get('summary'),
                                            'spent_hours': duration_minutes
                                        })
                        break

                    except requests.exceptions.HTTPError as http_err:
                        print(f'HTTP error occurred for issue {issue_id}: {http_err}')
                        retries += 1
                        time.sleep(retry_delay)
                    except Exception as err:
                        print(f'Other error occurred for issue {issue_id}: {err}')
                        retries += 1
                        time.sleep(retry_delay)
            skip += top

        except requests.exceptions.HTTPError as http_err:
            print(f'HTTP error occurred while getting issues list: {http_err}')
            break
        except Exception as err:
            print(f'Other error occurred while getting issues list: {err}')
            break


    hours_sum = 0

    for project, issues in issueDictionary.items():
        for issue in issues:

            issue['spent_hours'] = math.ceil(issue['spent_hours']/60)
            hours_sum += issue['spent_hours']



    print(issueDictionary)

    print(hours_sum)

    doc = Document()

    if issueDictionary:

        table = doc.add_table(rows=1, cols=3)

        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = '№ п\п'
        hdr_cells[1].text = 'Наименование и виды работ, услуг'
        hdr_cells[2].text = 'Кол-во часов'

        row_number = 1

        for project, issues in issueDictionary.items():
            for issue in issues:
                row_cells = table.add_row().cells
                row_cells[0].text = str(row_number)
                row_cells[1].text = '[A661ver12A] ' + issue['summary']
                row_cells[2].text = str(issue['spent_hours'])

                row_number += 1
        row_cells = table.add_row().cells
        row_cells[1].text = 'Всего:'
        row_cells[2].text = str(hours_sum)

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