# 💰 记账小工具 (nq-finance)

一个用 **Python + Streamlit + SQLite** 做的本地记账 Web 应用，完全离线运行，数据存在本机 `data/finance.db` 文件里。

## ✨ 功能

- **➕ 添加账目**：类型与分类联动选择，填金额、日期、备注
- **📋 账目列表**：按月份 / 类型 / 分类筛选；表格支持分页、排序、列筛选
- **✏️ 编辑账目**：每行一个编辑按钮，弹出模态框改完保存
- **🗑 删除账目**：行内按钮单条删除，或勾选多行批量删除；两者都带二次确认
- **📊 分类统计**：全部 / 支出 / 收入 / 转账四种口径，柱状图与月度趋势折线图可切换

## 🗂 预设分类

| 类型 | 分类                               |
|------|------------------------------------|
| 支出 | 餐饮、交通、购物、娱乐、居住、其他 |
| 收入 | 工资、奖金、红包、其他收入         |
| 转账 | 信用卡还款、余额转账               |

## 🚀 快速开始

需要 **Python 3.12+**，依赖用 [uv](https://docs.astral.sh/uv/) 管理。

```bash
# 1. 安装依赖(自动创建/复用 .venv,按 uv.lock 锁定版本)
uv sync
# 或者:make sync

# 2. 启动应用
make run
# 或者:uv run streamlit run src/nq_finance/app.py
```

浏览器打开 `http://localhost:8503`（端口在 `.streamlit/config.toml` 里配好了），看到三个 tab 就成功了 🎉

首次启动会自动建库并写入预置分类，不需要手动初始化。

## 🧱 项目结构

```
nq-finance/
├── src/nq_finance/
│   ├── db.py          # 数据层:连接、建表、金额换算、枚举定义(137 行)
│   ├── helpers.py     # 数据访问层:所有 SQL 都写在这里(302 行)
│   └── app.py         # 界面层:只负责渲染和交互,不写 SQL(791 行)
├── data/finance.db    # SQLite 数据库(自动生成,已在 .gitignore)
├── resume/            # 项目经验 & 面试问答(与运行无关)
├── .streamlit/config.toml
├── Makefile
└── pyproject.toml / uv.lock
```

三层职责分明：`app.py` 要数据就调 `helpers.py`，`helpers.py` 要连接就调 `db.py`，反向不依赖。

## 🖱 操作指南

### 添加账目

1. 切到 **「➕ 添加」** tab
2. 选类型（支出/收入/转账）→ **下面的分类下拉会自动跟着变**
3. 选分类、填金额（必须 > 0）、日期（默认今天）、备注（选填）
4. 点 **💾 保存**，右上角浮出提示就是成功了

### 查看 / 编辑 / 删除

1. 切到 **「📋 列表」** tab
2. 顶部三个多选框筛选月份 / 类型 / 分类
3. 表格支持点列头排序、点列头漏斗图标筛选、拖列宽
4. **改一条**：点该行末尾的 ✏️ → 弹出编辑框 → 改完保存
5. **删一条**：点该行末尾的 🗑 → 弹窗确认（二次确认后真删）
6. **删多条**：勾选若干行 → 点合计行右侧的 **🗑 批量删除** → 弹窗确认

### 看统计

1. 切到 **「📊 统计」** tab
2. 顶部选统计口径：**全部 / 支出 / 收入 / 转账**
3. 多选月份（不选 = 全部）
4. 用 **柱状图 / 折线图** 切换按钮换图表：柱状图看各分类的金额对比，折线图看按月走势

## ⚠️ 常见问题（新手必读）

1. **Streamlit 每次交互都会重新跑整个 `app.py` 脚本**
   所以"当前打开的弹窗是哪个"这类状态必须用 `st.session_state` 存，不能用普通 Python 变量。本项目里用
   `show_edit_dialog`、`show_delete_dialog`、`show_bulk_delete` 来标记当前要弹哪个框。

2. **金额一律用整数分存储，不要碰浮点**
   字段是 `amount_cents INTEGER`，12.34 元存成 `1234`。读写时用 `db.py` 的 `to_cents()` / `from_cents()`
   转换（内部走 `Decimal`）。直接拿浮点数运算，累加误差会让账对不上。

3. **SQL 永远用 `?` 占位符，不能 f-string 拼值**
   `f"WHERE name = '{user_input}'"` 是 SQL 注入漏洞。本项目所有查询都是 `?` + 参数绑定。
   （唯一"拼"的是 `IN (?,?,?)` 里的占位符个数——那是按参数**个数**生成的，值仍然走绑定。）

4. **写完数据库要调 `invalidate_caches()`**
   不然列表页/统计页还显示旧数据。这个函数集中在 `app.py`，一次清掉所有查询缓存。

5. **`st.tabs` 不是懒加载，但我们做了惰性渲染**
   默认情况下三个 tab 的代码每轮都会执行（哪怕你只看其中一个）。`app.py` 里根据 `session_state['main_tab']`
   判断当前在哪个 tab，只渲染那一个——否则你在列表页点个按钮，统计页的图表也会被重建一遍。

6. **第三方组件的状态是前端状态，Python 改不了**
   AGGrid 的勾选框就是例子：Python 只能**读**回来，不能从后端设置"选中哪些行"。所以"全选/反选"这类需求
   在它上面实现不了（除非写 JS 桥接，代价很大）。另外 `update_on` 参数不只是"哪些事件触发重跑"，
   它同时决定了组件会不会把数据回传——没列进去的事件，后端根本收不到。

7. **端口被占用怎么办？**
   ```bash
   uv run streamlit run src/nq_finance/app.py --server.port 8502
   ```

## 🔧 想改点东西？

| 想改什么         | 看哪里                                        |
|------------------|-----------------------------------------------|
| 加 / 改分类      | `db.py` 的 `PRESET_CATEGORIES` + `TYPE_LABELS` |
| 加一个账目类型   | `db.py` 的 `TxType` 枚举 + `TYPE_LABELS`       |
| 加 / 改字段      | `db.py` 的建表 SQL + `helpers.py` 的对应函数   |
| 改页面长什么样   | `app.py` 里的 `render_*_tab` 函数              |
| 改统计口径       | `helpers.py` 的 `get_category_stats` / `get_monthly_totals` |
| 改金额显示格式   | `helpers.py` 的 `from_cents()`                 |

> ⚠️ **改了建表语句记得删库重建**。`init_db()` 用的是 `CREATE TABLE IF NOT EXISTS`，它不会给已存在的表加列或改约束——
> 表结构变了但库没重建的话，问题会推迟到实际读写时才暴露。删掉 `data/finance.db` 重新启动即可（预置分类会自动补回）。

## 🧪 怎么手动跑数据库脚本

```bash
# 建库 + 打印所有分类(幂等,重复跑不会重复插数据)
uv run python -m nq_finance.db

# 只确认路径和连接
uv run python -c "import sys; sys.path.insert(0,'src/nq_finance'); import db; print(db.DB_PATH)"

# 代码检查 / 格式化
make check      # ruff check --fix
make format     # ruff format
```

**测试时请指向临时库，不要动真实数据**：

```bash
NQ_FINANCE_DB=/tmp/test.db uv run python -m nq_finance.db
```

## ⚙️ 数据库

- **位置**：`data/finance.db`，已加进 `.gitignore`，不会污染版本控制
- **可用环境变量 `NQ_FINANCE_DB` 覆盖**（测试时指向临时库，避免误操作真实数据）
- **重置数据**：删掉 `data/finance.db` 即可，下次启动自动重建

两张表：

| 表 | 作用 | 关键约束 |
|---|---|---|
| `categories` | 分类字典 | `UNIQUE(category_name, category_type)` 防重复 |
| `transactions` | 流水记录 | 复合外键 `(category_id, transaction_type)` 约束类型一致；CHECK 保证类型合法、金额 > 0 |

## 📦 依赖

直接依赖三个：

- `streamlit` — Web UI 框架
- `pandas` — 查询结果处理
- `streamlit-aggrid` — 表格组件（分页 / 排序 / 列筛选 / 行内按钮）

`sqlite3` 是 Python 标准库，不需要装。`altair`（图表）是 streamlit 的间接依赖，不用单独声明。

依赖声明写在 `pyproject.toml`，精确版本锁在 `uv.lock`（已提交进 git）：

- 装 / 同步依赖：`uv sync`
- 加新依赖：`uv add <包名>`（自动更新 `pyproject.toml` 和 `uv.lock`）
- 升级某个包：`uv lock --upgrade-package streamlit && uv sync`
- 升级全部：`uv lock --upgrade && uv sync`

## 🚧 已知限制

- 暂不支持多账本 / 多用户，所有数据混在一起
- 暂不支持导入 / 导出（可以加，工作量不大）
- 表格的排序和筛选目前在前端做。数据量很大时（十万条量级）需要改成服务端分页，否则一次性把全量数据传给组件会卡
- 界面文案的中文化只覆盖了页面的部分：AGGrid 的界面文字靠 `localeText` 配了中文，但 Streamlit 自带组件（多选框展开后的搜索提示等）是框架硬编码的，没有开关
