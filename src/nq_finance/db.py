import os
import sqlite3
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path

# <root>/src/nq_finance/db.py -> <root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("NQ_FINANCE_DB", PROJECT_ROOT / "data" / "finance.db"))


class TxType(StrEnum):
    """账目类型。"""

    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"


# 业务常量(给下拉框 / 中文显示用)
TYPE_LABELS = {
    TxType.EXPENSE: "支出",
    TxType.INCOME: "收入",
    TxType.TRANSFER: "转账",
}

# 预置分类:(type, name)
PRESET_CATEGORIES = [
    # 6 个支出分类
    (TxType.EXPENSE, "餐饮"),
    (TxType.EXPENSE, "交通"),
    (TxType.EXPENSE, "购物"),
    (TxType.EXPENSE, "娱乐"),
    (TxType.EXPENSE, "居住"),
    (TxType.EXPENSE, "其他"),
    # 4 个收入分类
    (TxType.INCOME, "工资"),
    (TxType.INCOME, "奖金"),
    (TxType.INCOME, "红包"),
    (TxType.INCOME, "其他收入"),
    # 2 个转账分类
    (TxType.TRANSFER, "信用卡还款"),
    (TxType.TRANSFER, "余额转账"),
]


def to_cents(amount: Decimal | float | int | str) -> int:
    """金额(元)转整数分。金额一律以分为单位存库,避免浮点误差。"""
    return int((Decimal(str(amount)) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> Decimal:
    """整数分转回金额(元)。"""
    return (Decimal(cents) / 100).quantize(Decimal("0.01"))


def get_connection() -> sqlite3.Connection:
    """获取一个数据库连接。

    新手提示:
    - row_factory = sqlite3.Row 让查询结果可以像字典一样访问 row["name"]
    - PRAGMA foreign_keys = ON 启用外键约束(默认是关的)
    - check_same_thread = False 是为了兼容 Streamlit 的多线程
    - isolation_level = None 是自动提交模式,写操作不用再手动 commit
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """初始化数据库:建表 + 写入预置分类(幂等,可重复执行)。"""
    print('init db')
    conn = get_connection()
    try:
        # categories 表:分类字典
        # UNIQUE(category_name, category_type) 防重复;UNIQUE(id, category_type) 供 transactions 的复合外键引用
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                category_name TEXT NOT NULL,
                category_type TEXT NOT NULL CHECK(category_type IN ('expense','income','transfer')),
                UNIQUE (category_name, category_type),
                UNIQUE (id, category_type)
            )
            """
        )
        # transactions 表:账目流水
        # amount_cents 以"分"存整数;复合外键保证分类 category_type 与流水 transaction_type 一致
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_type  TEXT NOT NULL CHECK(transaction_type IN ('expense','income','transfer')),
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                category_id  INTEGER NOT NULL,
                date         TEXT NOT NULL,
                note         TEXT NOT NULL DEFAULT '',
                created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (category_id, transaction_type) REFERENCES categories(id, category_type)
            )
            """
        )

        # 索引:加速按日期和按 (类型+分类) 的查询
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trans_date ON transactions(date)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trans_type_cat ON transactions(transaction_type, category_id)"
        )

        # 预置分类:靠 UNIQUE(category_name, category_type) + INSERT OR IGNORE 保证幂等
        for cat_type, cat_name in PRESET_CATEGORIES:
            conn.execute(
                "INSERT OR IGNORE INTO categories (category_name, category_type) VALUES (?, ?)",
                (cat_name, cat_type),
            )
    finally:
        conn.close()


def main() -> None:
    """本地验证入口:建库并打印分类。"""
    init_db()
    print(f"DB 路径: {DB_PATH}")
    conn = get_connection()
    try:
        for row in conn.execute("SELECT * FROM categories ORDER BY category_type, id"):
            print(f"  {row['id']:>2}  {row['category_type']:<8}  {row['category_name']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
