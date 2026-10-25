from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title='Анализ интернет-магазина', page_icon='🛒', layout='wide')
st.title('🛒 Анализ эффективности интернет-магазина')
st.caption('Интерактивный анализ заказов, покупателей и ассортимента')
BASE = Path(__file__).resolve().parent

@st.cache_data
def load_data():
    orders = pd.read_csv(BASE / 'orders.csv')
    users = pd.read_csv(BASE / 'users.csv')
    items = pd.read_csv(BASE / 'items.csv')
    return orders, users, items

try:
    orders, users, items = load_data()
except (FileNotFoundError, pd.errors.ParserError) as exc:
    st.error(f'Не удалось загрузить CSV: {exc}. Разместите три файла рядом с app.py.')
    st.stop()

# Проверка обязательных полей
required = {
    'orders.csv': (orders, {'order_id', 'user_id', 'item_id', 'order_date', 'quantity', 'price_per_unit'}),
    'users.csv': (users, {'user_id'}),
    'items.csv': (items, {'item_id', 'item_name', 'category'}),
}
for filename, (frame, columns) in required.items():
    missing = columns - set(frame.columns)
    if missing:
        st.error(f'В {filename} отсутствуют столбцы: {", ".join(sorted(missing))}')
        st.stop()

# Не допускаем размножения строк из-за повторяющихся справочных ключей.
users = users.drop_duplicates(subset='user_id', keep='first')
items = items.drop_duplicates(subset='item_id', keep='first')
df = orders.merge(users, on='user_id', how='left', validate='many_to_one')
df = df.merge(items, on='item_id', how='left', validate='many_to_one')
missing_before = df.isnull().sum()
df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')
if 'registration_date' in df:
    df['registration_date'] = pd.to_datetime(df['registration_date'], errors='coerce')
for col in ('quantity', 'price_per_unit'):
    df[col] = pd.to_numeric(df[col], errors='coerce')
for col in ('category', 'item_name', 'city', 'user_segment'):
    if col in df:
        df[col] = df[col].fillna('Неизвестно').astype(str)
initial_rows = len(df)
df = df.dropna(subset=['order_id', 'user_id', 'item_id', 'order_date', 'quantity', 'price_per_unit']).copy()
df = df[(df['quantity'] > 0) & (df['price_per_unit'] >= 0)].copy()
removed_rows = initial_rows - len(df)
df['revenue'] = df['quantity'] * df['price_per_unit']
if df.empty:
    st.warning('После очистки не осталось записей для анализа.')
    st.stop()

st.sidebar.header('Фильтры')
category_options = sorted(df['category'].unique().tolist())
selected_categories = st.sidebar.multiselect('Категории товаров', category_options, default=category_options)
min_day = df['order_date'].min().date()
max_day = df['order_date'].max().date()
dates = st.sidebar.date_input('Период заказов', value=(min_day, max_day), min_value=min_day, max_value=max_day)
if not isinstance(dates, (tuple, list)) or len(dates) != 2:
    st.info('Выберите начальную и конечную даты периода.')
    st.stop()
start, end = dates
if start > end:
    st.error('Дата начала должна быть не позднее даты окончания.')
    st.stop()
filtered = df[df['category'].isin(selected_categories) & df['order_date'].dt.date.between(start, end)].copy()

raw_tab, kpi_tab, viz_tab, insights_tab = st.tabs(['📋 Сырые данные', '📊 Ключевые показатели', '📈 Визуализация', '💡 Аналитические выводы'])
with raw_tab:
    st.subheader('Объединённые и очищенные данные')
    st.dataframe(filtered, use_container_width=True)
    st.caption(f'Исходных строк заказов: {len(orders)}. Удалено при очистке: {removed_rows}. Строк после фильтрации: {len(filtered)}.')
    with st.expander('Пропуски до очистки и заполнения'):
        st.dataframe(missing_before.rename('Пропусков').to_frame(), use_container_width=True)
    st.download_button('Скачать отфильтрованные данные', filtered.to_csv(index=False).encode('utf-8-sig'), 'filtered_orders.csv', 'text/csv')

order_count = filtered['order_id'].nunique()
revenue = filtered['revenue'].sum()
user_count = filtered['user_id'].nunique()
avg_order = revenue / order_count if order_count else 0
with kpi_tab:
    st.subheader('Показатели за выбранный период')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Количество заказов', f'{order_count:,}')
    c2.metric('Общая выручка', f'{revenue:,.2f} ₽')
    c3.metric('Уникальные покупатели', f'{user_count:,}')
    c4.metric('Средний чек', f'{avg_order:,.2f} ₽')
    st.caption('Заказ учитывается один раз по order_id; выручка = quantity × price_per_unit. При фильтрации по категории средний чек относится к выбранным товарам в заказах.')

with viz_tab:
    if filtered.empty:
        st.info('Нет данных для построения графиков. Измените фильтры.')
    else:
        st.subheader('Топ-10 товаров по выручке')
        top = filtered.groupby('item_name')['revenue'].sum().nlargest(10).sort_values()
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh(top.index, top.values, color='#3478c0')
        ax.set_xlabel('Выручка, ₽')
        ax.set_title('Лидеры продаж по выручке')
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        st.subheader('Выручка по категориям')
        by_category = filtered.groupby('category')['revenue'].sum().sort_values(ascending=False)
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.bar(by_category.index, by_category.values, color='#35a48a')
        ax.set_ylabel('Выручка, ₽')
        ax.tick_params(axis='x', rotation=25)
        ax.set_title('Сравнение категорий')
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        st.subheader('Количество заказов по дням недели')
        days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        weekdays = (filtered.assign(weekday=filtered['order_date'].dt.dayofweek)
                    .groupby('weekday')['order_id'].nunique().reindex(range(7), fill_value=0))
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.bar(days, weekdays.values, color='#e8a04b')
        ax.set_ylabel('Уникальных заказов')
        ax.set_title('Активность покупателей по дням недели')
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

with insights_tab:
    st.subheader('Выводы для руководства')
    if filtered.empty:
        st.warning('По выбранным фильтрам заказов нет, поэтому выводы не формируются.')
    else:
        cat_rev = filtered.groupby('category')['revenue'].sum().sort_values(ascending=False)
        item_rev = filtered.groupby('item_name')['revenue'].sum().sort_values(ascending=False)
        day_orders = (filtered.assign(weekday=filtered['order_date'].dt.dayofweek)
                      .groupby('weekday')['order_id'].nunique().reindex(range(7), fill_value=0))
        lead_cat = cat_rev.index[0]
        cat_share = cat_rev.iloc[0] / revenue * 100 if revenue else 0
        lead_item = item_rev.index[0]
        peak_day = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'][int(day_orders.idxmax())]
        weekend = day_orders.loc[[5, 6]].sum()
        weekday = day_orders.loc[[0, 1, 2, 3, 4]].sum()
        st.markdown(f'''**Итоги за {start:%d.%m.%Y}–{end:%d.%m.%Y}:**

- Выручка составила **{revenue:,.2f} ₽**, оформлено **{order_count}** уникальных заказов, средний чек — **{avg_order:,.2f} ₽**.
- Наибольшую выручку принесла категория **«{lead_cat}»**: **{cat_share:.1f}%** от выручки выбранной выборки.
- Товар-лидер по выручке — **«{lead_item}»** (**{item_rev.iloc[0]:,.2f} ₽**).
- Наибольшее число заказов пришлось на **{peak_day}** ({day_orders.max()} заказов).
- За выходные оформлено **{weekend}** заказов, за будни — **{weekday}**. Для сравнения интенсивности следует учитывать, что будних дней в периоде больше.

**Рекомендации:** изучить продвижение наиболее доходной категории и товара-лидера; проверить, какие акции или каналы привлечения связаны с пиковыми днями. Для выводов об эффективности рекламы потребуются данные о рекламных расходах.''')
        st.caption('Выводы пересчитываются при изменении фильтров. Это описательная аналитика, а не доказательство причинно-следственных связей.')
