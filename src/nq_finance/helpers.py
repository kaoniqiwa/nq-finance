from decimal import Decimal
import streamlit as st
import pandas as pd

from db import TYPE_LABELS, TxType, from_cents, get_connection, to_cents

TYPE_CHOICES = list(TxType)


# ---------------------------------------------------------------------------
# 分类相关
# ---------------------------------------------------------------------------
@st.cache_data
def get_categories(type_code: TxType | None = None) -> pd.DataFrame:
    """取分类列表。type_code 为 None 时返回全部;否则按类型过滤。"""
    conn = get_connection()
    try:
        if type_code is None:
            df = pd.read_sql_query(
                "SELECT id, category_name, category_type FROM categories ORDER BY category_type, id",
                conn,
            )
        else:
            df = pd.read_sql_query(
                "SELECT id, category_name, category_type FROM categories WHERE category_type = ? ORDER BY id",
                conn,
                params=[type_code],
            )
        return df
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 账目 CRUD
# ---------------------------------------------------------------------------
def add_transaction(
        transaction_type: TxType,
        amount: Decimal | float | int | str,
        category_id: int,
        trans_date: str,
        note: str = "",
) -> int:
    """添加一笔账目,返回新 id。amount 单位是元,内部转成整数分存储。"""
    # 流程:① 开连接 -> ② 执行 INSERT -> ③ 由 lastrowid 取回新 id -> ④ 关连接
    conn = get_connection()
    try:
        # 用 ? 占位符而不是拼字符串:既防 SQL 注入,也免去手工转义
        cur = conn.execute(
            """
            INSERT INTO transactions (transaction_type, amount_cents, category_id, date, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            # 参数与上面列名一一对应;金额先由元转成整数分再落库,
            # int() 是把 numpy 整数转成 Python int(sqlite3 不认 numpy 类型)
            (transaction_type, to_cents(amount), int(category_id), trans_date, note),
        )
        # lastrowid 就是刚插入那一行的自增 id,不需要再查一次。
        # 它的类型标注是 int | None(执行非 INSERT 语句时会是 None),
        # 这里插入成功必然有值,显式收窄一下类型
        new_id = cur.lastrowid
        if new_id is None:
            raise RuntimeError("INSERT 未返回 lastrowid,写入可能未成功")
        return new_id
    finally:
        # 无论成功还是抛异常都要关连接,避免泄漏
        conn.close()


def list_transactions(
        months: list[str] | None = None,
        types: list[str] | None = None,
        category_ids: list[int] | None = None,
) -> pd.DataFrame:
    """查账目,带可选筛选。

    参数:
        months       — 例 ['2026-07', '2026-06'],None 或 [] 表示不限
        types        — 例 ['expense', 'income'],None 或 [] 表示不限
        category_ids — 例 [1, 2, 3],None 或 [] 表示不限

    返回 DataFrame 列:id, date, type, type_label, category, category_id, amount, note
    其中 amount 单位是元(Decimal)。按 date DESC, id DESC 排序。
    """
    where_parts: list[str] = []
    params: list[str | int] = []
    if months:
        placeholders = ",".join("?" for _ in months)
        where_parts.append(f"strftime('%Y-%m', t.date) IN ({placeholders})")
        params.extend(months)
    if types:
        placeholders = ",".join("?" for _ in types)
        where_parts.append(f"t.transaction_type IN ({placeholders})")
        params.extend(types)
    if category_ids:
        placeholders = ",".join("?" for _ in category_ids)
        where_parts.append(f"t.category_id IN ({placeholders})")
        params.extend(category_ids)

    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    sql = f"""
           SELECT t.id, t.date, t.transaction_type AS type, c.category_name AS category,
                  t.category_id, t.amount_cents, t.note
           FROM transactions t
           LEFT JOIN categories c ON t.category_id = c.id
           {where_sql}
           ORDER BY t.date DESC, t.id DESC
       """
    conn = get_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()

    # 分 -> 元,用 Decimal 转换避免浮点误差
    df["amount"] = df["amount_cents"].map(from_cents)
    df = df.drop(columns=["amount_cents"])

    # 把 type 翻译成中文,放一列方便显示
    if not df.empty:
        df["type_label"] = df["type"].map(TYPE_LABELS).fillna(df["type"])
    else:
        df["type_label"] = pd.Series(dtype=str)

    # 固定列顺序,与 docstring 保持一致
    return df[["id", "date", "type", "type_label", "category", "category_id", "amount", "note"]]


def delete_transaction(trans_id: int) -> None:
    """按 id 删除一笔账目。"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM transactions WHERE id = ?", (int(trans_id),))
    finally:
        conn.close()


def delete_transactions(trans_ids: list[int]) -> int:
    """按 id 批量删除,返回实际删掉的条数。"""
    if not trans_ids:
        return 0
    # 占位符按 id 个数生成,值仍然走参数绑定,不是拼 SQL
    placeholders = ",".join("?" for _ in trans_ids)
    conn = get_connection()
    try:
        cur = conn.execute(
            f"DELETE FROM transactions WHERE id IN ({placeholders})",
            [int(i) for i in trans_ids],
        )
        return cur.rowcount
    finally:
        conn.close()


def update_transaction(
        trans_id: int,
        transaction_type: TxType,
        amount: Decimal | float | int | str,
        category_id: int,
        trans_date: str,
        note: str = "",
) -> None:
    """更新一笔账目。amount 单位是元,内部转成整数分存储。"""
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE transactions
               SET transaction_type = ?, amount_cents = ?, category_id = ?, date = ?, note = ?
             WHERE id = ?
            """,
            (
                transaction_type,
                to_cents(amount),
                int(category_id),
                trans_date,
                note,
                int(trans_id),
            ),
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

def get_category_stats(
    transaction_type: TxType | None = None,
    months: list[str] | None = None,
) -> pd.DataFrame:
    """按分类聚合统计。transaction_type 传 None 表示不限类型(统计全部)。

    返回 DataFrame 列:category, total, count, percent
    其中 total 单位是元(Decimal),percent 是占比(%,float)。按 total DESC 排序。
    """
    where_parts: list[str] = []
    params: list[str | int] = []
    if transaction_type is not None:
        where_parts.append("t.transaction_type = ?")
        params.append(transaction_type)

    if months:
        placeholders = ",".join("?" for _ in months)
        where_parts.append(f"strftime('%Y-%m', t.date) IN ({placeholders})")
        params.extend(months)

    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    # 用 INNER JOIN:这样分类如果没有交易就不会出现,统计里全是 0 的分类不显示
    sql = f"""
        SELECT c.category_name AS category,
               SUM(t.amount_cents) AS total_cents,
               COUNT(t.id) AS count
        FROM categories c
        JOIN transactions t ON t.category_id = c.id
        {where_sql}
        GROUP BY c.id, c.category_name
        ORDER BY total_cents DESC
    """

    conn = get_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()

    # 不提前返回:空结果也要走完,否则列名/列数会和 docstring 对不上
    # 百分比用整数分算:结果是普通 float,round() 才可靠
    grand_total_cents = df["total_cents"].sum()
    if grand_total_cents > 0:
        df["percent"] = (df["total_cents"] / grand_total_cents * 100).round(1)
    else:
        df["percent"] = 0.0

    # 分 -> 元,与 list_transactions 的口径保持一致
    df["total"] = df["total_cents"].map(from_cents)
    return df[["category", "total", "count", "percent"]]


def get_monthly_totals(
    transaction_type: TxType | None = None,
    months: list[str] | None = None,
) -> pd.DataFrame:
    """按月聚合金额,给折线图用(趋势是时间维度,分类维度交给柱状图)。

    transaction_type 传 None 表示不限类型。
    返回 DataFrame 列:month(YYYY-MM), total, count,按 month 升序。
    """
    where_parts: list[str] = []
    params: list[str | int] = []
    if transaction_type is not None:
        where_parts.append("t.transaction_type = ?")
        params.append(transaction_type)
    if months:
        placeholders = ",".join("?" for _ in months)
        where_parts.append(f"strftime('%Y-%m', t.date) IN ({placeholders})")
        params.extend(months)

    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    # 让数据库直接 GROUP BY 出每月一行,不用把明细拉进 pandas 再聚合
    sql = f"""
        SELECT strftime('%Y-%m', t.date) AS month,
               SUM(t.amount_cents) AS total_cents,
               COUNT(t.id) AS count
        FROM transactions t
        {where_sql}
        GROUP BY month
        ORDER BY month
    """
    conn = get_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()

    df["total"] = df["total_cents"].map(from_cents)
    return df[["month", "total", "count"]]


# ---------------------------------------------------------------------------
# 筛选辅助
# ---------------------------------------------------------------------------
@st.cache_data
def get_month_options() -> list[str]:
    """列出有账目的月份(YYYY-MM),倒序,给筛选下拉用。

    交给数据库 DISTINCT 去重,只取需要的几行;
    比把整表拉进 pandas 再算 strftime 省事得多。
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT strftime('%Y-%m', t.date) AS month"
            " FROM transactions t ORDER BY month DESC"
        ).fetchall()
        return [r["month"] for r in rows]
    finally:
        conn.close()
