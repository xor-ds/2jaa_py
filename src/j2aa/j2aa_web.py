import time
from itertools import chain
from dash import (
    Dash,
    dcc,
    html,
    callback,
    Input,
    Output,
    State,
    no_update,
    set_props,
    DiskcacheManager,
    CeleryManager,
)
import webbrowser
import os
from threading import Timer
from pathlib import Path, PurePath
import datetime
import configparser

# import dash_mantine_components as dmc
import base64
import xmltodict
import diskcache
from celery import Celery
from urllib.parse import urlparse, parse_qs

from jiralib.jira_session import JiraSession
from jiralib.j2aa_converter import J2aaConverter

import logger

# import dash_bootstrap_components as dbc

from dash.exceptions import PreventUpdate  # , LongCallbackError

# from dash.exceptions import LongCallbackError

HOST = "localhost"

PORT = 8050

CURRENT_CONFIG_FILE_NAME = None

if "REDIS_URL" in os.environ:
    celery_app = Celery(
        __name__, broker=os.environ["REDIS_URL"], backend=os.environ["REDIS_URL"]
    )

    BACKGROUND_CALLBACK_MANAGER = CeleryManager(celery_app)

else:
    cache = diskcache.Cache("./cache")

    BACKGROUND_CALLBACK_MANAGER = DiskcacheManager(cache)

app = Dash(__name__)

app.layout = html.Div(
    [
        dcc.Store(id="auth"),
        html.Table(
            [
                html.Tr(
                    [
                        html.Td(
                            html.Div("Ссылка на доску", className="field-label"),
                            className="left-column",
                        ),
                        html.Td(
                            dcc.Input(id="board_url", className="field"),
                            className="center-column",
                        ),
                        html.Td(
                            dcc.Upload(
                                html.Button(
                                    "Выбрать профиль",
                                    id="upload_profile_button",
                                    className="button",
                                ),
                                # accept="{name: 'my file.json', type: 'text/plain'}",
                                id="upload_profile",
                            ),
                            className="right-column",
                        ),
                    ]
                ),
                html.Tr(
                    [
                        html.Td(
                            html.Div("Доп. JQL фильтр", className="field-label"),
                            className="left-column",
                        ),
                        html.Td(
                            dcc.Input(id="sub_filter", className="field"),
                            className="center-column",
                        ),
                        html.Td(
                            [
                                html.Button(
                                    "Сохранить профиль",
                                    id="save_profile_button",
                                    className="button",
                                ),
                                dcc.Download(id="save_profile"),
                            ],
                            className="right-column",
                        ),
                    ]
                ),
                html.Tr(
                    [
                        html.Td(
                            html.Div("Поля jira", className="field-label"),
                            className="left-column",
                        ),
                        html.Td(
                            dcc.Input(id="jira_fields", className="field"),
                            className="center-column",
                        ),
                        html.Td(className="right-column"),
                    ]
                ),
                html.Tr(
                    [
                        html.Td(
                            html.Div("Файл для экспорта", className="field-label"),
                            className="left-column",
                        ),
                        html.Td(
                            dcc.Input(id="output_file", className="field"),
                            className="center-column",
                        ),
                        html.Td(className="right-column"),
                    ]
                ),
                html.Tr(
                    [
                        html.Td(
                            html.Div("Имя пользователя", className="field-label"),
                            className="left-column",
                        ),
                        html.Td(
                            dcc.Input(id="username", className="field"),
                            className="center-column",
                        ),
                        html.Td(className="right-column"),
                    ]
                ),
                html.Tr(
                    [
                        html.Td(
                            html.Div("Пароль", className="field-label"),
                            className="left-column",
                        ),
                        html.Td(
                            dcc.Input(
                                id="password", className="field", type="password"
                            ),
                            className="center-column",
                        ),
                        html.Td(className="right-column"),
                    ]
                ),
                html.Tr(
                    [
                        html.Td(className="left-column"),
                        html.Td(
                            [
                                html.Progress(
                                    id="progress_bar",
                                    value="0",
                                    style={"visibility": "hidden", "width": "100%"},
                                ),
                                html.Div(
                                    children="",
                                    id="progress_text",
                                    className="progress-text",
                                ),
                                html.Div(
                                    children="", id="log_area", className="log-area"
                                ),
                            ],
                            className="center-column",
                        ),
                        html.Td(
                            [
                                html.Button(
                                    "Конвертировать",
                                    id="convert_button",
                                    className="button",
                                ),
                                html.Button(
                                    "Отменить",
                                    id="cancel_button",
                                    className="button",
                                    disabled=True,
                                ),
                            ],
                            className="right-column",
                        ),
                    ]
                ),
            ]
        ),
    ]
)


def set_title():
    pass


def get_default_properties():
    config_file_name = f"{Path.home()}/.j2aa"

    p = Path(config_file_name)
    if not p.exists():
        p.write_text(
            "username=\n"
            + "password=\n"
            + "\n"
            + "board_url=https://jira.example.com/secure/RapidBoard.jspa?rapidView=00000\n"
            + "sub_filter = ((statusCategory = Done AND status changed AFTER -12w) OR (statusCategory != Done)) AND (IssueType in (Bug, Story, Task))\n"
            + "output_file = csv/output.csv\n"
            + "\n"
            + "# supported attributes: issuetype, labels, epic, priority, components, project, assignee, reporter, projectkey, fixVersions, summary, creator, status\n"
            + "jira_fields = issuetype, labels\n"
            + "#verify_ssl=False\n"
        )

    parser = configparser.ConfigParser()
    with Path(config_file_name).open() as lines:
        lines = chain(("[default]",), lines)
        parser.read_file(lines)

    return dict(parser.items("default"))


def decode_base64(b64_content):
    content_type, content_string = b64_content.split(",")

    decoded = base64.b64decode(content_string).decode()

    return decoded


@callback(
    Output("board_url", "value"),
    Output("sub_filter", "value"),
    Output("jira_fields", "value"),
    Output("output_file", "value"),
    Output("username", "value"),
    Output("password", "value"),
    Output("log_area", "children"),
    Input("upload_profile", "contents"),
    State("upload_profile", "filename"),
)
def upload_profile(contents, filename):
    # TODO вставить фильтр расширения в окно выбора файла
    if contents is None:
        defaults = get_default_properties()

        return (
            defaults["board-url"],
            defaults["sub-filter"],
            defaults["jira-fields"],
            defaults["output-file"],
            defaults["username"],
            defaults["password"],
            "",
        )

    else:
        try:
            props = {}
            decoded_str = decode_base64(contents)
            for p in xmltodict.parse(decoded_str)["properties"]["entry"]:
                props[p["@key"]] = p["#text"] if "#text" in p else ""

            global CURRENT_CONFIG_FILE_NAME

            CURRENT_CONFIG_FILE_NAME = filename

            set_title()

            return (
                props["board_url"],
                props["jql_sub_filter"],
                props["jira_fields"],
                props["output_file_name"],
                no_update,
                no_update,
                "",
            )

        except Exception as err:
            # TODO defaults = get_default_properties()
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                f"Неверный формат файла с профилем подключения: {str(err)}.",
            )


@callback(
    Output("save_profile", "data"),
    Input("save_profile_button", "n_clicks"),
    State("board_url", "value"),
    State("sub_filter", "value"),
    State("jira_fields", "value"),
    State("output_file", "value"),
)
def save_profile(n_clicks, board_url, sub_filter, jira_fields, output_file):
    # TODO Сделать выбор имени файла при сохранении
    if n_clicks is not None:
        entry = list()
        entry.append({"@key": "board_url", "#text": board_url})
        entry.append({"@key": "jira_fields", "#text": jira_fields})
        entry.append({"@key": "jql_sub_filter", "#text": sub_filter})
        entry.append({"@key": "output_file_name", "#text": output_file})

        props = dict()
        props["entry"] = entry

        root = dict()
        root["properties"] = props

        content = xmltodict.unparse(root)
        return dict(content=content, filename="profile.xml")

    else:
        raise PreventUpdate


@callback(Input("cancel_button", "n_clicks"), State("auth", "data"))
def close_session(n_clicks, auth):
    if (n_clicks is not None) and (auth is not None):
        # JiraSession.close_session(auth['url'], auth['session'], False)

        print(f"Закрытие сессии {auth}")

        set_props("auth", {"data": None})


@callback(
    # Output('log_area', 'children', allow_duplicate=True),
    Input("convert_button", "n_clicks"),
    State("board_url", "value"),
    State("sub_filter", "value"),
    State("jira_fields", "value"),
    State("output_file", "value"),
    State("username", "value"),
    State("password", "value"),
    background=True,
    manager=BACKGROUND_CALLBACK_MANAGER,
    prevent_initial_call=True,
    running=[
        (Output("convert_button", "disabled"), True, False),
        (Output("cancel_button", "disabled"), False, True),
        (Output("save_profile_button", "disabled"), True, False),
        (Output("upload_profile", "disabled"), True, False),
        (Output("save_profile_button", "disabled"), True, False),
        (Output("board_url", "disabled"), True, False),
        (Output("sub_filter", "disabled"), True, False),
        (Output("jira_fields", "disabled"), True, False),
        (Output("output_file", "disabled"), True, False),
        (Output("username", "disabled"), True, False),
        (Output("password", "disabled"), True, False),
        (
            Output("progress_bar", "style"),
            {"visibility": "visible", "width": "100%"},
            {"visibility": "hidden", "width": "100%"},
        ),
    ],
    cancel=[Input("cancel_button", "n_clicks")],
    progress=[Output("progress_bar", "value"), Output("progress_bar", "max")],
)
def convert(
    set_progress,
    n_clicks,
    board_url,
    sub_filter,
    jira_fields,
    output_file,
    username,
    password,
):
    log2 = logger.Logger("auth", "data")

    log = logger.Logger("log_area", "children")

    def print_message(msg):
        log.append(msg)

    jira_session = None

    try:
        parsed_url = urlparse(board_url)
        board_id = parse_qs(parsed_url.query)["rapidView"][0]
        fields = [s.strip() for s in jira_fields.split(",")]
        verify_ssl = False

        # TODO Убрать ссылку на сертификат
        # TODO Добавить обработку сертификатов из конфига
        # verify_ssl = 'C:/Users/sokolov-dev/PythonProjects/jiralib-main/jira_cert.PEM'

        jira_session = JiraSession(
            board_url, username, password, verify_ssl=verify_ssl, debug_session=True
        )

        # auth = dict(url=board_url, session=dict(name='JSESSIONID', value='1111111111111'))
        # auth = dict(url=board_url, session=jira_session.session)
        # set_props('auth', {'children': auth})
        # log2.append(auth)
        # print(auth)
        # print_message('Получены промежуточные данные')
        # time.sleep(10)
        # print_message('Получение данных завершено')

        def callback(received_issues, chunk_size, total):
            received = len(received_issues)
            set_progress((str(received), str(total)))
            set_props(
                "progress_text", {"children": f"Получено {received} из {total} issues"}
            )
            # print_message(f'Получено {received} из {total} issues')

            # if STOP_FLAG:
            #     raise ConvertationStopped('')

        issues = jira_session.select_issues_for_board(
            board_id,
            sub_filter,
            fields=["created", "status"] + fields,
            expand="changelog",
            callback=callback,
        )

        # issues = []

        if len(issues) > 0:
            converter = J2aaConverter.from_jira_session(jira_session, board_id)
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

            if Path(output_file).exists():
                archive_file(output_file)

            abs_path = J2aaConverter.export_to_csv(df, output_file)
            print_message(f"Данные по выгружены в файл {abs_path}")

        else:
            print_message("Получено 0 issues. Нет данных для конвертации")

    # except ConvertationStopped:
    #     print_message('Конвертация остановлена')
    # except LongCallbackError:
    # print_message("Не удается подключиться")
    except Exception as e:
        print_message(str(e))
    finally:
        if jira_session is not None:
            jira_session.close()


def open_browser():
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open_new(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    Timer(1, open_browser).start()

    app.run(debug=True, host=HOST, port=PORT)
