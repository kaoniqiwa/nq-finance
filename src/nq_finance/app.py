from typing import cast

import streamlit as st
from helpers import (
    TYPE_CHOICES,
    TYPE_LABELS,
    add_transaction,
    delete_transaction,
    delete_transactions,
    get_categories,
    get_category_stats,
    get_monthly_totals,
    get_month_options,
    list_transactions,
    update_transaction,
)
from db import TxType
import altair as alt
import pandas as pd
from datetime import date
from db import init_db
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, JsCode

st.set_page_config(page_title='记账小工具', page_icon='💰', layout='wide')

# AG Grid 的界面文案。不覆盖这份翻译的话,分页、筛选器、菜单全是英文
GRID_LOCALE_ZH = {
    'page': '页',
    'to': '到',
    'of': '共',
    'next': '下一页',
    'last': '末页',
    'first': '首页',
    'previous': '上一页',
    'loadingOoo': '加载中...',
    'noRowsToShow': '暂无数据',
    'selectAll': '全选',
    'searchOoo': '搜索...',
    'blanks': '空白',
    'filterOoo': '筛选...',
    'applyFilter': '应用',
    'resetFilter': '重置',
    'clearFilter': '清除',
    'cancelFilter': '取消',
    'equals': '等于',
    'notEqual': '不等于',
    'lessThan': '小于',
    'greaterThan': '大于',
    'lessThanOrEqual': '小于等于',
    'greaterThanOrEqual': '大于等于',
    'inRange': '区间',
    'contains': '包含',
    'notContains': '不包含',
    'startsWith': '开头是',
    'endsWith': '结尾是',
    'pageSizeSelectorLabel': '每页条数:',
    'pageSize': '每页条数',
    'totalRows': '总行数',
    'totalAndFilteredRows': '全部 / 筛选后',
}

# 操作列的按钮渲染器。AGGrid 单元格里的点击没法直接回传 Python,
# 所以按钮被点击时把 "动作:id:时间戳" 写进隐藏列 _action,
# 再靠它的 cellValueChanged 事件把这次点击带回 Python。
# 带时间戳是为了让同一行、同一个按钮被反复点击时值也每次不同
# (值不变就不触发 cellValueChanged,第二次点击会丢)。
ACTION_RENDERER = JsCode("""
class ActionRenderer {
  init(params) {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;gap:10px;align-items:center;height:100%';

    const make = (label, kind, tip) => {
      const el = document.createElement('span');
      el.textContent = label;
      el.title = tip;
      el.style.cssText = 'cursor:pointer;font-size:15px;user-select:none';
      el.onclick = (e) => {
        e.stopPropagation();
        params.node.setDataValue(
          '_action', kind + ':' + params.data.ID + ':' + Date.now()
        );
      };
      return el;
    };

    wrap.appendChild(make('✏️', 'edit', '编辑'));
    wrap.appendChild(make('🗑', 'del', '删除'));
    this.eGui = wrap;
  }
  getGui() { return this.eGui; }
}
""")


@st.cache_resource
def init_db_once() -> None:
    """建表 + 写预置分类。用 cache_resource 包一层,保证整个应用生命周期只执行一次。"""
    init_db()


# 启动时初始化数据库(第一次 rerun 执行,之后走缓存)
init_db_once()


# ---------------------------------------------------------------------------
# session_state 初始化
# 新手提示:st.session_state 像一个 dict,在多次 rerun 之间保持值。
# ---------------------------------------------------------------------------

def init_session_state() -> None:
    if 'show_edit_dialog' not in st.session_state:
        st.session_state.show_edit_dialog = None
    if 'show_delete_dialog' not in st.session_state:
        st.session_state.show_delete_dialog = None
    if 'grid_version' not in st.session_state:
        st.session_state.grid_version = 0


init_session_state()


# ---------------------------------------------------------------------------
# 工具函数:控件封装
# Streamlit 控件的返回类型普遍标注偏宽(为了兼容可选空值、日期范围模式等分支),
# 这里统一用 cast 收窄成实际类型,业务代码里就不必到处写 cast
# ---------------------------------------------------------------------------


def select_tx_type(label: str, key: str) -> TxType:
    """类型下拉框,返回 TxType。"""
    return cast(
        TxType,
        st.selectbox(label, options=TYPE_CHOICES, format_func=lambda x: TYPE_LABELS[x], key=key),
    )


def input_amount(label: str, key: str) -> float:
    """金额输入框,返回 float(单位:元)。"""
    return cast(float, st.number_input(label, min_value=0.01, step=1.0, format='%.2f', key=key))


def input_date(label: str, key: str) -> date:
    """日期选择框,返回 date。"""
    return cast(date, st.date_input(label, value=date.today(), key=key))


def input_note(label: str, key: str, placeholder: str = '选填') -> str:
    """备注输入框,返回 str。"""
    return cast(str, st.text_input(label, key=key, placeholder=placeholder))


# ---------------------------------------------------------------------------
# 工具函数:失效缓存
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 工具函数:失效缓存
# ---------------------------------------------------------------------------

def invalidate_caches() -> None:
    """写完数据库后调用,让列表/统计 tab 看到最新数据。"""
    cached_list_transactions.clear()
    get_categories.clear()
    get_month_options.clear()
    cached_get_category_stats.clear()  # 统计 tab 还没做


# ---------------------------------------------------------------------------
# 缓存包装:把 helpers 里的查询包一层 st.cache_data
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 缓存包装:把 helpers 里的查询包一层 st.cache_data
# ---------------------------------------------------------------------------

@st.cache_data
def cached_list_transactions(
        months: list[str] | None = None,
        types: list[str] | None = None,
        category_ids: list[int] | None = None
):
    """缓存 list_transactions 结果。

        提示:
        - Streamlit 不能直接缓存 list/dict,要用 tuple。
        - 写完数据库必须 clear_cache(),否则这里还是旧数据。
        """

    return list_transactions(
        months=list(months) if months else None,
        types=list(types) if types else None,
        category_ids=list(category_ids) if category_ids else None,
    )


@st.cache_data
def cached_get_category_stats(
        transaction_type: TxType, months_tuple: tuple | None = None
) -> pd.DataFrame:
    return get_category_stats(
        transaction_type=transaction_type,
        months=list(months_tuple) if months_tuple else None,
    )


@st.cache_data
def cached_get_monthly_totals(
        transaction_type: TxType | None, months_tuple: tuple | None = None
) -> pd.DataFrame:
    return get_monthly_totals(
        transaction_type=transaction_type,
        months=list(months_tuple) if months_tuple else None,
    )


# ---------------------------------------------------------------------------
# Tab 1: 添加账目
# ---------------------------------------------------------------------------


def render_add_tab() -> None:
    """渲染「添加账目」tab:类型、分类、金额、日期、备注表单。"""
    st.header("➕ 添加账目")

    # 操作流程:① 选类型 -> ② 按类型加载分类 -> ③ 选分类并反查 id
    #          -> ④ 填金额/日期/备注 -> ⑤ 点保存写库 -> ⑥ 清缓存并提示
    # 整个表单用一层带边框的 container 圈住,不用 st.form:
    # form 内的控件改动不触发 rerun,分类就没法跟着类型联动
    with st.container(border=True):
        # ① 选类型
        type_code = select_tx_type("类型", key="add_type")

        # ② 按类型取分类(带缓存);一条都没有说明库没初始化好,直接中断渲染
        cats_df = get_categories(type_code)
        if cats_df.empty:
            st.error('没有可用的分类,请检查数据库初始化。')
            return
        cat_options = cats_df['category_name'].tolist()

        # 类型一变就把分类重置回第一项。
        # 这里要"赋值"而不是 pop:pop 之后 session_state 里没有这个 key,
        # Streamlit 会回退到前端传来的 widget 值,下拉框仍旧显示上次选的分类
        if st.session_state.get('add_type_prev') != type_code:
            st.session_state['add_category'] = cat_options[0]
            st.session_state.add_type_prev = type_code

        # ③ 选分类,再由分类名反查 id(库里存的是 id 不是名字)
        category_name = st.selectbox(
            '分类',
            options=cat_options,
            key='add_category',
        )
        category_id = int(cats_df[cats_df['category_name'] == category_name].iloc[0]['id'])

        # ④ 金额和日期并排,备注单独一行
        col1, col2 = st.columns(2)
        with col1:
            amount = input_amount('金额(元)', key='add_amount')
        with col2:
            trans_date = input_date('日期', key='add_date')
        note = input_note('备注', key='add_note')

        # ⑤ 保存按钮:没有 form 了,普通按钮点下即触发 rerun
        if st.button('💾 保存', width='stretch', type='primary'):
            new_id = add_transaction(
                transaction_type=type_code,
                amount=amount,
                category_id=category_id,
                trans_date=trans_date.isoformat(),
                note=note.strip(),
            )
            invalidate_caches()
            # 清掉已填内容,相当于 st.form 的 clear_on_submit=True
            for k in ('add_category', 'add_amount', 'add_date', 'add_note'):
                st.session_state.pop(k, None)
            st.session_state.flash_add = f'✓ 已保存!账目 id = {new_id}'
            st.rerun()

        # ⑥ 提示紧跟在保存按钮下方。用独立的 flash_add 键,
        #    不跟 main() 顶部那个 flash 混用,位置才落在这里
        if flash := st.session_state.pop('flash_add', None):
            st.success(flash)
            st.balloons()


# ---------------------------------------------------------------------------
# Tab 2: 账目列表
# ---------------------------------------------------------------------------

def render_list_tab() -> None:
    st.header('📋 账目列表')
    # 顶部筛选条
    filter_cols = st.columns(3)
    with filter_cols[0]:
        # 月份选项:由数据库 DISTINCT 得出(已缓存),不必把整表拉进 pandas
        month_options = get_month_options()
        selected_months = st.multiselect(
            '月份',
            options=month_options,
            key='filter_months',
            placeholder='全部月份',  # 不选时显示,否则是框架默认的英文
        )
    with filter_cols[1]:
        selected_types = st.multiselect(
            '类型',
            options=TYPE_CHOICES,
            format_func=lambda x: TYPE_LABELS[x],
            key='filter_types',
            placeholder='全部类型',
        )

    with filter_cols[2]:
        all_cats = get_categories(None)
        cat_options = all_cats['category_name'].tolist()
        selected_cats = st.multiselect(
            '分类',
            options=cat_options,
            key='filter_cats',
            placeholder='全部分类',
        )
        # 计算分类 id 列表
    selected_cat_ids: list[int] = []
    if selected_cats:
        selected_cat_ids = (
            all_cats[all_cats['category_name'].isin(selected_cats)]['id'].astype(int).tolist()
        )

    # 查询
    df = cached_list_transactions(
        list(selected_months) if selected_months else None,
        list(selected_types) if selected_types else None,
        list(selected_cat_ids) if selected_cat_ids else None,
    )

    if df.empty:
        st.info('没有匹配的账目,试试在「添加」页记一笔 ✍️')
        return
    # 合计行:左边写总数,右边留一个占位。
    # 批量删除按钮要等表格渲染完、读到勾选状态才能决定是否禁用,
    # 所以先用 empty() 占住位置,稍后再往里填 —— 位置仍留在这一行
    cap_col, act_slot = st.columns([5, 1])
    cap_col.caption(f'共 {len(df)} 条,总金额 ¥{df["amount"].sum():.2f}')
    bulk_slot = act_slot.empty()
    # 交给 AgGrid:分页、排序、列筛选、列宽调整都由它提供,
    # 不再需要我们逐行手写,也不受"行多就慢"的限制
    show_df = df[['id', 'date', 'type_label', 'category', 'amount', 'note']].rename(
        columns={
            'id': 'ID',
            'date': '日期',
            'type_label': '类型',
            'category': '分类',
            'amount': '金额',
            'note': '备注',
        }
    )
    # AgGrid 对 Decimal(object dtype) 支持不好,金额转成 float
    show_df['金额'] = show_df['金额'].astype(float)
    # 「操作」列只负责显示两个按钮(cellRenderer),本身不存值;
    # 「_action」是隐藏列,用来承接按钮点击写进来的动作
    show_df['操作'] = ''
    show_df['_action'] = ''

    gb = GridOptionsBuilder.from_dataframe(show_df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gb.configure_column('ID', width=80, type=['numericColumn'])
    gb.configure_column(
        '金额',
        width=110,
        type=['numericColumn'],
        valueFormatter="value != null ? value.toFixed(2) : ''",
    )
    gb.configure_column('备注', flex=2)
    gb.configure_column(
        '操作',
        width=90,
        sortable=False,
        filter=False,
        cellRenderer=ACTION_RENDERER,
    )
    gb.configure_column('_action', hide=True)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=10)
    # 每行前面的勾选框(可多选),用来做批量操作
    gb.configure_selection(selection_mode='multiple', use_checkbox=True)
    gb.configure_grid_options(
        # 分页下拉的候选项。不显式给的话,那个下拉框是空白的
        paginationPageSizeSelector=[10, 20, 50],
        # 界面文案中文化
        localeText=GRID_LOCALE_ZH,
    )

    grid = AgGrid(
        show_df,
        gridOptions=gb.build(),
        # 注意:update_on 不只是"哪些事件触发重跑",它还决定组件会不会把数据回传。
        # 没列进来的事件,后端根本收不到 —— 所以勾选必须监听 selectionChanged,
        # 否则读 selected_rows 永远是空的(哪怕用户明明勾了)。
        # 代价:每勾一行都会重跑一次整页,视觉上闪一下。
        update_on=['cellValueChanged', 'selectionChanged'],
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        # valueFormatter / cellRenderer 里都是 JS 代码,需要放行
        allow_unsafe_jscode=True,
        height=420,
        fit_columns_on_grid_load=True,
        # key 里带版本号:编辑/删除成功后自增,强制重建组件。
        # AGGrid 的行数据有自己的状态,key 不变的话传新数据进去也不会刷新
        key=f'tx_grid_{st.session_state.grid_version}',
    )

    # 解析按钮点击:隐藏列的值形如 "edit:12:1697000000000"
    grid_data = grid.get('data')
    if grid_data is not None and '_action' in list(getattr(grid_data, 'columns', [])):
        hits = grid_data['_action'].astype(str)
        hits = hits[hits.str.count(':') == 2]  # 只有点过的行才符合这个格式
        if len(hits) > 0:
            raw = str(hits.iloc[-1])
            # 同一次点击只处理一次:值里带时间戳,新的点击必然是新的字符串。
            # 这里刻意不 st.rerun() —— 弹窗在同一轮就弹出,省掉一次整页重绘
            if raw != st.session_state.get('last_action'):
                st.session_state.last_action = raw
                kind, tx_id, _ts = raw.split(':')
                if kind == 'edit':
                    st.session_state.show_edit_dialog = int(tx_id)
                else:
                    st.session_state.show_delete_dialog = int(tx_id)

    # ---- 勾选多行 → 批量删除 ----
    selected = grid.get('selected_rows')
    sel_ids: list[int] = []
    if selected is not None and len(selected) > 0:
        # 不同版本分别返回 DataFrame 或 list[dict],两种都兜住
        if hasattr(selected, 'iloc'):
            sel_ids = [int(v) for v in selected['ID']]
        else:
            sel_ids = [int(r['ID']) for r in selected]

    # 填回合计行右侧的占位:没勾选时置灰,勾上就点亮,文案带上条数
    with bulk_slot:
        if st.button(
            f'🗑 批量删除 ({len(sel_ids)})' if sel_ids else '🗑 批量删除',
            disabled=not sel_ids,
            key='bulk_delete',
            width='stretch',
        ):
            # 不 st.rerun():下面的弹窗调用就在这一轮里,省掉一次整页重绘
            st.session_state.show_bulk_delete = list(sel_ids)

    # ---- 弹窗:每轮脚本执行到这里,按需弹出 ----
    if st.session_state.get('show_edit_dialog'):
        edit_dialog(st.session_state.show_edit_dialog)
    if st.session_state.get('show_delete_dialog'):
        delete_dialog(st.session_state.show_delete_dialog)
    if st.session_state.get('show_bulk_delete'):
        bulk_delete_dialog(st.session_state.show_bulk_delete)


# ---------------------------------------------------------------------------
# 弹窗:编辑 / 删除确认
# ---------------------------------------------------------------------------
@st.dialog('✏️ 编辑账目')
def edit_dialog(trans_id: int) -> None:
    """弹窗编辑一笔账目。"""
    # 从 DB 拿当前值(不走缓存,确保是最新的)
    all_df = list_transactions()
    row = all_df[all_df['id'] == trans_id]
    if row.empty:
        st.error(f'找不到 ID = {trans_id} 的账目,可能已被删除。')
        return
    current = row.iloc[0]

    new_type = st.selectbox(
        '类型',
        options=TYPE_CHOICES,
        index=TYPE_CHOICES.index(current['type']),
        format_func=lambda x: TYPE_LABELS[x],
        key=f'edit_type_{trans_id}',
    )
    cats_df = get_categories(new_type)
    cat_names = cats_df['category_name'].tolist()
    cur_cat = current['category']
    # 当前分类不属于新类型时(比如把"信用卡还款"改成支出),回退到第一项
    if cur_cat not in cat_names:
        cur_cat = cat_names[0]
    new_cat_name = st.selectbox(
        '分类',
        options=cat_names,
        index=cat_names.index(cur_cat),
        key=f'edit_cat_{trans_id}',
    )
    new_cat_id = int(cats_df[cats_df['category_name'] == new_cat_name].iloc[0]['id'])

    c1, c2 = st.columns(2)
    with c1:
        new_amount = st.number_input(
            '金额',
            min_value=0.01,
            step=1.0,
            format='%.2f',
            value=float(current['amount']),
            key=f'edit_amount_{trans_id}',
        )
    with c2:
        new_date = st.date_input(
            '日期',
            value=date.fromisoformat(current['date']),
            key=f'edit_date_{trans_id}',
        )
    new_note = st.text_input(
        '备注',
        value=str(current['note'] or ''),
        key=f'edit_note_{trans_id}',
    )

    s1, s2 = st.columns(2)
    with s1:
        if st.button('💾 保存修改', width='stretch', type='primary', key=f'save_edit_{trans_id}'):
            update_transaction(
                trans_id,
                transaction_type=new_type,
                amount=new_amount,
                category_id=new_cat_id,
                trans_date=new_date.isoformat(),
                note=new_note.strip(),
            )
            invalidate_caches()
            st.session_state.show_edit_dialog = None
            st.session_state.grid_version += 1  # 重建表格,否则行数据不会刷新
            st.session_state.toast = f'✓ 账目 #{trans_id} 已更新'
            st.rerun()
    with s2:
        if st.button('取消', width='stretch', key=f'cancel_edit_{trans_id}'):
            st.session_state.show_edit_dialog = None
            st.rerun()


@st.dialog('⚠️ 确认删除')
def delete_dialog(trans_id: int) -> None:
    """删除确认弹窗:点了确认才真正删。"""
    st.warning(f'确定要删除账目 #{trans_id} 吗?此操作不可撤销。')

    s1, s2 = st.columns(2)
    with s1:
        if st.button('🗑 确认删除', width='stretch', type='primary', key=f'confirm_del_{trans_id}'):
            delete_transaction(trans_id)
            invalidate_caches()
            st.session_state.show_delete_dialog = None
            st.session_state.grid_version += 1  # 重建表格,否则行数据不会刷新
            st.session_state.toast = f'已删除账目 #{trans_id}'
            st.rerun()
    with s2:
        if st.button('取消', width='stretch', key=f'cancel_del_{trans_id}'):
            st.session_state.show_delete_dialog = None
            st.rerun()


@st.dialog('⚠️ 确认批量删除')
def bulk_delete_dialog(trans_ids: list[int]) -> None:
    """批量删除的确认弹窗:列出条数和 ID,确认后才真删。"""
    st.warning(f'确定要删除选中的 {len(trans_ids)} 条账目吗?此操作不可撤销。')
    # ID 太多时只列前 20 个,避免弹窗被撑爆
    shown = '、'.join(f'#{i}' for i in trans_ids[:20])
    st.caption(f'账目 ID:{shown}' + (' …' if len(trans_ids) > 20 else ''))

    s1, s2 = st.columns(2)
    with s1:
        if st.button('🗑 确认删除', width='stretch', type='primary', key='confirm_bulk_del'):
            deleted = delete_transactions(trans_ids)
            invalidate_caches()
            st.session_state.show_bulk_delete = None
            st.session_state.grid_version += 1      # 重建表格,刷新数据并清掉勾选
            st.session_state.toast = f'已删除 {deleted} 条账目'
            st.rerun()
    with s2:
        if st.button('取消', width='stretch', key='cancel_bulk_del'):
            st.session_state.show_bulk_delete = None
            st.rerun()


# ---------------------------------------------------------------------------
# Tab 3: 分类统计
# ---------------------------------------------------------------------------
def render_stats_tab() -> None:
    st.header('📊 分类统计')

    # 类型选择
    # 选项里混一个 None 表示"不限类型";显示名靠 format_func 翻译
    stat_type = st.radio(
        '统计类型',
        options=[None, *TYPE_CHOICES],
        format_func=lambda x: '全部' if x is None else TYPE_LABELS[x],
        horizontal=True,
        key='stat_type',
    )
    # 月份筛选(与列表 tab 共用同一个缓存函数)
    month_options = get_month_options()
    selected_months = st.multiselect(
        '月份(不选则统计全部)',
        options=month_options,
        key='stat_months',
        placeholder='全部月份',      # 不选时显示,否则是框架默认的英文
    )

    # 查统计
    stats_df = cached_get_category_stats(
        stat_type,
        tuple(selected_months) if selected_months else None,
    )

    if stats_df.empty:
        type_label = '全部' if stat_type is None else TYPE_LABELS[stat_type]
        st.info(f'暂无{type_label}数据,先在「添加」页记几笔吧 ✍️')
        return

    # 总计
    total = stats_df['total'].sum()
    count = stats_df['count'].sum()
    cols = st.columns(3)
    cols[0].metric('总金额', f'¥{total:,.2f}')
    cols[1].metric('总笔数', f'{count}')
    cols[2].metric('分类数', f'{len(stats_df)}')

    # 图表切换
    chart_kind = st.segmented_control(
        '图表',
        options=['柱状图', '折线图'],
        default='柱状图',
        key='chart_kind',
    )

    # 两张图共用同一套 mark/chrome 规格(来自数据可视化规范):
    # - 单系列只用一种颜色,不做"越大越深"的渐变 —— 那等于把长度/位置信息再编码一遍
    # - 网格线 1px 实线浅灰,不用虚线(虚线会被读成"预测"或"阈值")
    # - 数值标签用中性色,不跟着数据色染色
    if chart_kind == '折线图':
        # 折线看的是趋势,所以换成按月聚合的数据(分类维度对折线没有意义)
        monthly_df = cached_get_monthly_totals(
            stat_type,
            tuple(selected_months) if selected_months else None,
        )
        if monthly_df.empty:
            st.info('所选条件下没有数据')
        else:
            line_df = monthly_df.copy()
            line_df['total'] = line_df['total'].astype(float)

            line = (
                alt.Chart(line_df)
                .mark_line(
                    color='#2a78d6',
                    strokeWidth=2,
                    # 数据点 ≥8px,太小的点既难点中也不好看
                    point=alt.OverlayMarkDef(color='#2a78d6', size=64, filled=True),
                )
                .encode(
                    x=alt.X(
                        'month:O',
                        title=None,
                        axis=alt.Axis(ticks=False, domain=False,
                                      labelColor='#0b0b0b', labelFontSize=12),
                    ),
                    y=alt.Y(
                        'total:Q',
                        title='金额(元)',
                        scale=alt.Scale(zero=True),
                        axis=alt.Axis(
                            gridColor='#e1e0d9', gridWidth=1, domainColor='#c3c2b7',
                            labelColor='#898781', titleColor='#52514e', tickCount=5,
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip('month:O', title='月份'),
                        alt.Tooltip('total:Q', title='金额', format=',.2f'),
                        alt.Tooltip('count:Q', title='笔数'),
                    ],
                )
            )
            # 只在最后一个月标值:每个点都标数字会满屏噪声,反而没人读
            end_label = (
                alt.Chart(line_df.tail(1))
                .mark_text(align='center', baseline='bottom', dy=-10,
                           fontSize=12, color='#52514e')
                .encode(
                    x=alt.X('month:O'),
                    y=alt.Y('total:Q'),
                    text=alt.Text('total:Q', format=',.2f'),
                )
            )
            st.altair_chart(
                (line + end_label).configure_view(stroke=None),
                width='stretch',
            )
    else:
        # 柱状图:各分类的金额对比
        chart_df = stats_df.copy()
        chart_df['total'] = chart_df['total'].astype(float)   # Decimal 转数值,否则 Altair 画不出来

        bars = (
            alt.Chart(chart_df)
            .mark_bar(color='#2a78d6', size=18, cornerRadiusEnd=4)
            .encode(
                x=alt.X(
                    'category:N',
                    sort='-y',
                    title=None,
                    axis=alt.Axis(labelAngle=-30, ticks=False, domain=False,
                                  labelColor='#0b0b0b', labelFontSize=12),
                ),
                y=alt.Y(
                    'total:Q',
                    title='金额(元)',
                    # 柱状图的纵轴必须从 0 起:截断基线会把差距放大好几倍,读者会高估差异
                    scale=alt.Scale(zero=True),
                    axis=alt.Axis(
                        gridColor='#e1e0d9', gridWidth=1, domainColor='#c3c2b7',
                        labelColor='#898781', titleColor='#52514e', tickCount=5,
                    ),
                ),
                tooltip=[
                    alt.Tooltip('category:N', title='分类'),
                    alt.Tooltip('total:Q', title='金额', format=',.2f'),
                    alt.Tooltip('count:Q', title='笔数'),
                    alt.Tooltip('percent:Q', title='占比(%)', format='.1f'),
                ],
            )
        )
        labels = bars.mark_text(
            align='center', baseline='bottom', dy=-6, fontSize=12, color='#52514e'
        ).encode(
            text=alt.Text('total:Q', format=',.2f'),
        )
        st.altair_chart(
            (bars + labels).configure_view(stroke=None),
            width='stretch',
        )

    # 统计表
    st.subheader('📋 详细数据')
    show_stats = stats_df.rename(
        columns={
            'category': '分类',
            'total': '金额',
            'count': '笔数',
            'percent': '占比(%)',
        }
    )
    st.dataframe(show_stats, width='stretch', hide_index=True)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main() -> None:
    """应用入口:渲染标题和三个 tab。"""

    # 提示做成浮层(右上角,几秒后自动消失),类似前端的 ElMessage;
    # 同样借 session_state 传递,因为 rerun 会丢弃当场渲染的提示
    if toast_msg := st.session_state.pop('toast', None):
        st.toast(toast_msg)

    st.title("💰 记账小工具")
    st.caption("Python + Streamlit + SQLite · 本机运行 · 数据存 finance.db")
    TAB_ADD, TAB_LIST, TAB_STATS = '➕ 添加', '📋 列表', '📊 统计'
    # key 有两个作用:一是把"当前选中哪个 tab"存进 session_state,
    # 这样 rerun 后不会跳回第一个 tab;二是拿到它才能做下面的惰性渲染
    tab_add, tab_list, tab_stats = st.tabs(
        [TAB_ADD, TAB_LIST, TAB_STATS],
        key='main_tab',
        # 切 tab 本身是前端行为、不触发 rerun,不加这个惰性渲染后切过去会是空白
        on_change='rerun',
    )

    # 只渲染当前选中的那个 tab。st.tabs 默认不是懒加载 ——
    # 三个 tab 的代码每轮都会执行,那样在列表页点个按钮,
    # 统计页的图表也会被重建一遍,白白增大重绘量(视觉上就是那一下闪)
    current_tab = st.session_state.get('main_tab') or TAB_ADD
    if current_tab == TAB_ADD:
        with tab_add:
            render_add_tab()
    elif current_tab == TAB_LIST:
        with tab_list:
            render_list_tab()
    else:
        with tab_stats:
            render_stats_tab()


print('main')
if __name__ == "__main__":
    main()
