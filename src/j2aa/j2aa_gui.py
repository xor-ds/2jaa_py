# -*- coding: utf-8 -*-
"""
Created on Sun Mar 10 16:49:16 2024

@author: Sokolov-DeV
"""
from jiralib.jira_session import JiraSession
from jiralib.j2aa_converter import J2aaConverter

import tkinter as tk
from tkinter import scrolledtext, messagebox as mb, filedialog as fd
import webbrowser
import configparser
from itertools import chain
import os
import xmltodict
from urllib.parse import urlparse
from urllib.parse import parse_qs
import threading
from requests.exceptions import ConnectionError
import datetime
from pathlib import Path, PurePath

APP_TITLE = "Jira to actionable agile converter"
APP_VERSION = "2.0.0"
CURRENT_CONFIG_FILE_NAME = None
ROOT = None
# HOME_DIRECTORY = None
WIDTH_LEFT = 50
WIDTH_CENTER = 80
WIDTH_RIGHT = 20
PROFILE_FILE_TYPES = [("Profile", "*.xml"), ("All files", "*.*")]

STOP_FLAG = False
THREAD = None


class ConvertationStopped(Exception):
    pass


def set_title():
    global CURRENT_CONFIG_FILE_NAME, APP_TITLE, APP_VERSION, ROOT

    title = f"{APP_TITLE} v{APP_VERSION}"

    if CURRENT_CONFIG_FILE_NAME is not None:
        title += f" [{Path(CURRENT_CONFIG_FILE_NAME).stem}]"
        # title += f" [{os.path.basename(CURRENT_CONFIG_FILE_NAME)}]"

    ROOT.title(title)


def on_select_profile():
    # TODO Поддержка последней открытой директории
    # TODO Отображение имени профиля в заголвке окна после его открытия

    global CURRENT_CONFIG_FILE_NAME

    file_name = fd.askopenfilename(
        title="Выберите профиль подключения",
        filetypes=PROFILE_FILE_TYPES,
        # defaultextension=PROFILE_FILE_TYPES
    )
    if file_name != "":
        set_val_to_txt("", txt_board_url)

        with open(file_name, "r", encoding="utf-8") as file:
            my_xml = file.read()

        try:
            props = {}
            for p in xmltodict.parse(my_xml)["properties"]["entry"]:
                props[p["@key"]] = p["#text"] if "#text" in p else ""

            set_val_to_txt(props["board_url"], txt_board_url)
            set_val_to_txt(props["jira_fields"], txt_fields)
            set_val_to_txt(props["jql_sub_filter"], txt_jql)
            set_val_to_txt(props["output_file_name"], txt_output_file)
            print_message("", True)

            CURRENT_CONFIG_FILE_NAME = file_name
            set_title()
        except:
            get_default_properties()
            mb.showwarning(
                "Выбор профиля подключения",
                "Неверный формат файла с профилем подключения.",
            )


def on_save_profile():
    # TODO Проверка на наличие обязательных параметров
    # TODO Поддержка последней открытой директории
    # TODO подстановка расширения по-умолчанию
    # TODO Отображение имени профиля в заголвке окна после его сохранения

    global CURRENT_CONFIG_FILE_NAME

    if CURRENT_CONFIG_FILE_NAME is not None:
        p = Path(CURRENT_CONFIG_FILE_NAME)
        initialfile = p.name
        initialdir = p.parent
    else:
        initialfile = None
        initialdir = None

    file_name = fd.asksaveasfilename(
        title="Выберите имя файла для профиля подключения",
        filetypes=PROFILE_FILE_TYPES,
        defaultextension="xml",
        # initialfile = CURRENT_CONFIG_FILE_NAME if CURRENT_CONFIG_FILE_NAME is not None else None
        initialfile=initialfile,
        initialdir=initialdir,
    )
    if file_name != "":

        entry = []
        entry.append({"@key": "board_url", "#text": txt_board_url.get()})
        entry.append({"@key": "jira_fields", "#text": txt_fields.get()})
        entry.append({"@key": "jql_sub_filter", "#text": txt_jql.get()})
        entry.append({"@key": "output_file_name", "#text": txt_output_file.get()})

        props = {}
        props["entry"] = entry

        root = {}
        root["properties"] = props

        xml_string = xmltodict.unparse(root)

        formatted_file_name = Path(file_name).with_suffix(".xml")
        p = Path(formatted_file_name)
        p.write_text(xml_string, encoding="utf-8")

        # TODO убрать использование os.path Поменять на pathlib
        # ext = os.path.splitext(file_name)[-1].lower()
        # if ext == '':
        #     file_name += '.xml'
        # # print(f'Extension is "{ext}"')

        # with open(file_name, 'w', encoding='utf-8') as file:
        #      file.write(xml_string)

        CURRENT_CONFIG_FILE_NAME = file_name
        set_title()


def on_select_output_file():
    # TODO Вставить возможность выбора диркетории вместо файла
    # TODO Проверка слэшей
    # TODO Использование относительных путей
    # TODO Поддержка последней открытой директории

    file_name = fd.askopenfilename(
        title="Выберите выходной файл",
        filetypes=[("csv file", "*.csv"), ("All files", "*.*")],
        # defaultextension=PROFILE_FILE_TYPES
    )
    if file_name != "":
        set_val_to_txt(file_name, txt_output_file)


def print_message(message, clear=False):
    txt_log.config(state="normal")

    if clear:
        txt_log.delete(1.0, tk.END)

    txt_log.insert(tk.INSERT, f"{message}\n")
    txt_log.config(state="disabled")


def on_convert():
    global THREAD
    global STOP_FLAG

    if THREAD is None:
        print_message("Начало конвертации", True)
        THREAD = threading.Thread(target=convert)
        THREAD.start()
    else:
        print_message("Остановка ...")
        STOP_FLAG = True


def convert():
    # TODO Проверку на наличие обзательных параметров
    # TODO проверка на валидность имени csv файла
    # TODO Журналирование предыдущих файлов

    js = None

    try:
        controls = [
            txt_board_url,
            txt_fields,
            txt_jql,
            txt_output_file,
            txt_username,
            txt_password,
            btn_select_profile,
            btn_save_profile,
            btn_select_output_file,
        ]

        for ctl in controls:
            ctl.configure(state=tk.DISABLED)
        btn_convert["text"] = "Прервать"

        url = txt_board_url.get()
        parsed_url = urlparse(url)
        board_id = parse_qs(parsed_url.query)["rapidView"][0]
        fields = [s.strip() for s in txt_fields.get().split(",")]

        jql = txt_jql.get()
        output_file_name = txt_output_file.get()

        username = txt_username.get()
        password = txt_password.get()
        verify_ssl = False
        # TODO Убрать ссылку на сертификат
        # TODO Добавить обработку сертификатов из конфига
        # verify_ssl = 'C:/Users/sokolov-dev/PythonProjects/jiralib-main/jira_cert.PEM'

        js = JiraSession(url, username, password, verify_ssl=verify_ssl)

        def callback(issues, p, t):
            print_message(f"Получено {len(issues)} из {t} issues")
            if STOP_FLAG:
                raise ConvertationStopped("")

        issues = js.select_issues_for_board(
            board_id,
            jql,
            fields=["created", "status"] + fields,
            expand="changelog",
            callback=callback,
        )

        if len(issues) > 0:
            converter = J2aaConverter.from_jira_session(js, board_id)
            df = converter.convert_issues(issues, fields, print_log=print_message)

            def archive_file(file_path):
                unix_creation_time = os.path.getmtime(file_path)
                suffix = datetime.datetime.fromtimestamp(unix_creation_time).strftime(
                    "_%Y%m%d_%H%M"
                )

                # file_name = os.path.splitext(file_path)
                # new_file_path = file_name[0] + suffix + file_name[1]
                new_stem = PurePath(file_path).stem + suffix
                new_file_path = PurePath(file_path).with_stem(new_stem)

                # os.rename(file_path, new_file_path)
                Path(file_path).rename(new_file_path)

            # if os.path.exists(file_path):
            if Path(output_file_name).exists():
                archive_file(output_file_name)

            abs_path = J2aaConverter.export_to_csv(df, output_file_name)
            print_message(f"Данные по выгружены в файл {abs_path}")
        else:
            print_message("Получено 0 issues. Нет данных для конвертации")
    except ConvertationStopped:
        print_message("Конвертация остановлена")
    except ConnectionError:
        print_message("Не удается подключиться")
        pass
    # except Exception as e:
    #     print_message(e)
    finally:
        if js is not None:
            js.close()

        for ctl in controls:
            ctl.configure(state=tk.NORMAL)
            btn_convert["text"] = "Конвертация"

        global STOP_FLAG
        global THREAD
        STOP_FLAG = False
        THREAD = None


def get_default_properties():
    # config_file_name = f'{HOME_DIRECTORY}/.j2aa_py'
    config_file_name = f"{Path.home()}/.j2aa"

    p = Path(config_file_name)
    if not p.exists():
        p.write_text(
            "username=\n"
            + "password=\n"
            + "\n"
            + "board-url=https://jira.example.com/secure/RapidBoard.jspa?rapidView=00000\n"
            + "sub-filter = ((statusCategory = Done AND status changed AFTER -12w) OR (statusCategory != Done)) AND (IssueType in (Bug, Story, Task))\n"
            + "output-file = csv/output.csv\n"
            + "\n"
            + "# supported attributes: issuetype, labels, epic, priority, components, project, assignee, reporter, projectkey, fixVersions, summary, creator, status\n"
            + "jira-fields = issuetype, labels\n"
            + "#verify_ssl=False\n"
        )

    parser = configparser.ConfigParser()
    with Path(config_file_name).open() as lines:
        lines = chain(("[default]",), lines)
        parser.read_file(lines)

    return dict(parser.items("default"))


def set_val_to_txt(val, txt):
    txt.delete(0, tk.END)
    txt.insert(0, val)


def set_props_to_txt(properties, key, txt):
    if key in properties:
        set_val_to_txt(properties[key], txt)
    else:
        set_val_to_txt(properties[key], "")


def read_default_config():
    defaults = get_default_properties()
    set_props_to_txt(defaults, "username", txt_username)
    set_props_to_txt(defaults, "password", txt_password)
    set_props_to_txt(defaults, "board-url", txt_board_url)
    set_props_to_txt(defaults, "sub-filter", txt_jql)
    set_props_to_txt(defaults, "output-file", txt_output_file)
    set_props_to_txt(defaults, "jira-fields", txt_fields)


def on_open_board_url(ADD):
    url = txt_board_url.get()
    webbrowser.open(url, new=2)


def on_reset_default_jql(ADD):
    defaults = get_default_properties()
    set_props_to_txt(defaults, "sub-filter", txt_jql)


def on_reset_default_fields(ADD):
    defaults = get_default_properties()
    set_props_to_txt(defaults, "jira-fields", txt_fields)


def on_reset_default_output_file(ADD):
    defaults = get_default_properties()
    set_props_to_txt(defaults, "output-file", txt_output_file)


def on_reset_default_credentials(ADD):
    defaults = get_default_properties()
    set_props_to_txt(defaults, "username", txt_username)
    set_props_to_txt(defaults, "password", txt_password)


if __name__ == "__main__":
    # HOME_DIRECTORY = os.path.expanduser("~")

    # TODO Запрет на изменение размеров окна
    ROOT = tk.Tk()
    set_title()

    # root.geometry('800x400')
    # root.title(APP_TITLE)

    lbl = tk.Label(ROOT, text="Ссылка на доску")
    lbl.grid(column=0, row=0, sticky=tk.W + tk.N)
    lbl.bind("<Double-Button-1>", on_open_board_url)
    txt_board_url = tk.Entry(ROOT, width=WIDTH_CENTER)
    txt_board_url.grid(column=1, row=0)
    btn_select_profile = tk.Button(
        ROOT, text="Выбрать профиль", command=on_select_profile, width=WIDTH_RIGHT
    )
    btn_select_profile.grid(column=3, row=0, sticky=tk.W + tk.N)
    btn_select_profile.focus()

    lbl = tk.Label(ROOT, text="JQL фильтр")
    lbl.grid(column=0, row=1, sticky=tk.W + tk.N)
    lbl.bind("<Double-Button-1>", on_reset_default_jql)
    txt_jql = tk.Entry(ROOT, width=WIDTH_CENTER)
    txt_jql.grid(column=1, row=1)
    btn_save_profile = tk.Button(
        ROOT, text="Сохранить профиль", command=on_save_profile, width=WIDTH_RIGHT
    )
    btn_save_profile.grid(column=3, row=1, sticky=tk.W + tk.N)

    lbl = tk.Label(ROOT, text="Поля jira")
    lbl.bind("<Double-Button-1>", on_reset_default_fields)
    lbl.grid(column=0, row=2, sticky=tk.W + tk.N)
    txt_fields = tk.Entry(ROOT, width=WIDTH_CENTER)
    txt_fields.grid(column=1, row=2)

    lbl = tk.Label(ROOT, text="Файл для экспорта")
    lbl.grid(column=0, row=3, sticky=tk.W + tk.N)
    lbl.bind("<Double-Button-1>", on_reset_default_output_file)
    txt_output_file = tk.Entry(ROOT, width=WIDTH_CENTER)
    txt_output_file.grid(column=1, row=3)
    btn_select_output_file = tk.Button(
        ROOT, text="Обзор", command=on_select_output_file, width=WIDTH_RIGHT
    )
    btn_select_output_file.grid(column=3, row=3, sticky=tk.W + tk.N)

    lbl = tk.Label(ROOT, text="Имя пользователя")
    lbl.grid(column=0, row=4, sticky=tk.W + tk.N)
    lbl.bind("<Double-Button-1>", on_reset_default_credentials)
    txt_username = tk.Entry(ROOT, width=WIDTH_CENTER)
    txt_username.grid(column=1, row=4)

    lbl = tk.Label(ROOT, text="Пароль")
    lbl.grid(column=0, row=5, sticky=tk.W + tk.N)
    lbl.bind("<Double-Button-1>", on_reset_default_credentials)
    txt_password = tk.Entry(ROOT, show="*", width=WIDTH_CENTER)
    txt_password.grid(column=1, row=5)

    txt_log = scrolledtext.ScrolledText(
        ROOT, height=10, width=WIDTH_CENTER - 22, state=tk.DISABLED
    )
    txt_log.grid(column=1, row=6, sticky=tk.W + tk.N)
    btn_convert = tk.Button(
        ROOT, text="Конвертировать", command=on_convert, width=WIDTH_RIGHT
    )
    btn_convert.grid(column=3, row=6, sticky=tk.W + tk.N)

    read_default_config()

    ROOT.mainloop()
