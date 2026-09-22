"""schedule HTTP 合同测例的共享夹具。

所有用例通过 FastAPI TestClient 走真实 ASGI 链路（路由 -> Pydantic 校验
-> MortgageService -> 引擎 -> SQLite），并把 DATA_DIR 指到临时目录，
绝不触碰开发库 backend/data/app.db。
"""
import os
import sqlite3
import tempfile

# 必须在 import app.* 之前设置：app.config 在导入时固化 DATA_DIR / DB_PATH。
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="mortgage_contract_")
os.environ["DATA_DIR"] = _TMP_DATA_DIR

import pytest
from fastapi.testclient import TestClient

from app import seed
from app.db import DB_PATH
from app.main import app


@pytest.fixture(scope="session")
def client():
    seed.init_db()  # 幂等：建表 + 仅空库时写入种子数据
    with TestClient(app) as c:  # 进入上下文触发 startup（init_db）
        yield c


@pytest.fixture()
def run_count():
    """返回一个读取 calc_runs 当前条数的可调用对象，每个用例独立连接临时库。"""

    def _count() -> int:
        conn = sqlite3.connect(DB_PATH)
        try:
            return conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0]
        finally:
            conn.close()

    return _count
