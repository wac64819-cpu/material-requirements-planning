"""Loopback-only UI adapter; business logic remains procedural in planner.py."""
import argparse
import json
import sqlite3
from urllib.parse import parse_qs
from pathlib import Path
from wsgiref.simple_server import make_server

from planner import calculate_plan
from sample_data import priority_case, basic_case, surplus_case
import storage
import csv_io

ROOT = Path(__file__).parent / "web"
DATABASE = Path(__file__).parent / "data" / "planning.sqlite3"


def browser_numbers(value):
    """Keep calculated large integers exact when displayed by JavaScript."""
    if type(value) is int and abs(value) > 9007199254740991:
        return str(value)
    if isinstance(value, list):
        return [browser_numbers(item) for item in value]
    if isinstance(value, dict):
        return {key: browser_numbers(item) for key, item in value.items()}
    return value


def reply(start_response, status, value, mime="application/json; charset=utf-8"):
    data = value if isinstance(value, bytes) else json.dumps(browser_numbers(value), ensure_ascii=False).encode("utf-8")
    start_response(status, [("Content-Type", mime), ("Content-Length", str(len(data))),
        ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
        ("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")])
    return [data]


def download(start_response, data, filename, mime):
    start_response("200 OK", [("Content-Type", mime), ("Content-Length", str(len(data))),
        ("Content-Disposition", 'attachment; filename="'+filename+'"'),
        ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")])
    return [data]


def route(env, start_response):
    host = env.get("HTTP_HOST", "")
    if host not in ("127.0.0.1:" + env["SERVER_PORT"], "localhost:" + env["SERVER_PORT"]):
        return reply(start_response, "403 Forbidden", {"message": "只允许本机访问。"})
    path, method = env.get("PATH_INFO", "/"), env["REQUEST_METHOD"]
    if method == "GET" and path == "/api/csv/templates.zip":
        return download(start_response, csv_io.templates_zip(), "mrp-csv-templates.zip", "application/zip")
    if method == "GET" and path.startswith("/api/history/") and "/csv/" in path:
        parts = path.split("/")
        if len(parts) != 6 or parts[5] not in ("MAKE","PURCHASE","ALLOCATION","TRACE","RISK"):
            return reply(start_response,"400 Bad Request",{"message":"不支持的导出类型。"})
        record = storage.get_batch(DATABASE, parts[3])
        if not record:
            return reply(start_response,"404 Not Found",{"message":"历史计划不存在。"})
        return download(start_response,csv_io.export_batch(record,parts[5]),
                        "plan-"+record["saved_batch"]["batch_id"]+"-"+parts[5]+".csv","text/csv; charset=utf-8")
    if method == "GET" and path == "/favicon.ico":
        return reply(start_response, "204 No Content", b"")
    if method == "GET" and path == "/api/workspace":
        return reply(start_response, "200 OK", storage.load_workspace(DATABASE))
    if method == "GET" and path == "/api/history":
        try:
            offset = int(parse_qs(env.get("QUERY_STRING", "")).get("offset", ["0"])[0])
            if offset < 0:
                raise ValueError()
        except ValueError:
            return reply(start_response, "400 Bad Request", {"message": "无效的历史页码。"})
        return reply(start_response, "200 OK", storage.list_batches(DATABASE, offset=offset))
    if method == "GET" and path.startswith("/api/history/"):
        batch = storage.get_batch(DATABASE, path.rsplit("/", 1)[-1])
        return reply(start_response, "200 OK" if batch else "404 Not Found", batch or {"message": "历史计划不存在。"})
    if method == "GET" and path in ("/", "/app.js", "/style.css"):
        name, mime = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                      "/style.css": ("style.css", "text/css")}[path]
        return reply(start_response, "200 OK", (ROOT / name).read_bytes(), mime + "; charset=utf-8")
    if method == "GET" and path.startswith("/api/example/"):
        factory = {"priority": priority_case, "basic": basic_case, "surplus": surplus_case}.get(path.split("/")[-1])
        if factory:
            sources, request = factory()
            return reply(start_response, "200 OK", dict(sources=sources, request=request))
    if method == "POST" and path in ("/api/calculate", "/api/workspace", "/api/csv/preview"):
        if env.get("HTTP_ORIGIN") not in (None, "http://" + host):
            return reply(start_response, "403 Forbidden", {"message": "不允许其他网站提交计算。"})
        if env.get("CONTENT_TYPE", "").split(";")[0] != "application/json":
            return reply(start_response, "415 Unsupported Media Type", {"message": "请提交JSON数据。"})
        try:
            size = int(env.get("CONTENT_LENGTH") or "0")
            if not 0 < size <= 2_000_000:
                return reply(start_response, "413 Content Too Large", {"message": "输入为空或超过2MB。"})
            payload = json.loads(env["wsgi.input"].read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected record")
        except (ValueError, UnicodeError):
            return reply(start_response, "400 Bad Request", {"message": "输入数据格式无效。"})
        if path == "/api/csv/preview":
            return reply(start_response,"200 OK",csv_io.preview_import(payload.get("payload"),payload.get("files")))
        if path == "/api/workspace":
            outcome = storage.save_workspace(DATABASE, payload.get("payload"), payload.get("expected_revision"))
            return reply(start_response, "409 Conflict" if outcome["status"] == "CONFLICT" else "200 OK", outcome)
        return reply(start_response, "200 OK", storage.calculate_and_save(DATABASE, payload))
    return reply(start_response, "404 Not Found", {"message": "找不到这个页面或接口。"})


def application(env, start_response):
    try:
        return route(env, start_response)
    except (sqlite3.Error, OSError):
        return reply(start_response, "503 Service Unavailable", {
            "status": "SAVE_FAILED", "message": "本地存储操作失败，未确认保存成功。请检查磁盘或文件权限后重试。"})


def main():
    global DATABASE
    parser = argparse.ArgumentParser(description="Local material planning workbench")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--database", type=Path, default=DATABASE)
    options = parser.parse_args()
    DATABASE = options.database.resolve()
    storage.initialize(DATABASE)
    with make_server("127.0.0.1", options.port, application) as server:
        print(f"Open http://127.0.0.1:{options.port}  |  Ctrl+C to stop", flush=True)
        if options.open_browser:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{options.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Stopped.")


if __name__ == "__main__":
    main()
