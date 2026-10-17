"""学生可用的数据库助手函数：沙箱运行前自动可用的全局函数。

- get_conn()               返回 pymysql 连接（已连到你自己的库）
- query(sql, args)         执行查询，返回元组列表
- query_dicts(sql, args)   执行查询，返回字典列表
- execute(sql, args)       执行写入，返回影响行数（自动 commit）
"""
import os


def get_conn():
    import pymysql

    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
    )


def query(sql, args=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.fetchall()
    finally:
        conn.close()


def query_dicts(sql, args=None):
    import pymysql

    conn = get_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, args or ())
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql, args=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            conn.commit()
            return cur.rowcount
    finally:
        conn.close()
