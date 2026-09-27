"""대시보드.  실행:  streamlit run app.py

노트북에서 확정한 쿼리를 올려놓는 곳입니다.
숫자마다 '정의 · 제외 조건 · 실행된 SQL'을 함께 보여주는 것이 이 대시보드의 핵심입니다.
"""
from pathlib import Path

import duckdb
import streamlit as st

ROOT = Path(__file__).parent
DATA = (ROOT / "data" / "raw").as_posix()

st.set_page_config(page_title="배송 지연이 리뷰를 얼마나 깎는가", page_icon="📦", layout="wide")


@st.cache_resource(show_spinner=False)
def con():
    if not (ROOT / "data" / "raw" / "olist_orders_dataset.csv").exists():
        st.error("`data/raw/` 에 CSV가 없습니다. `data/README.md` 안내대로 먼저 내려받으세요.")
        st.stop()
    c = duckdb.connect()
    c.execute((ROOT / "sql" / "base.sql").read_text(encoding="utf-8").format(data=DATA))
    return c


@st.cache_data(show_spinner=False)
def q(sql: str):
    return con().execute(sql).df()


def block(title, sql, definition, caveat=None, chart=None, y=None, show_table=True):
    """차트 하나 + 그 숫자의 정의 + 실행된 SQL을 한 묶음으로 그립니다."""
    st.subheader(title)
    df = q(sql)
    if df.empty:
        st.warning("결과가 없습니다.")
        return df
    if chart == "bar":
        st.bar_chart(df.set_index(df.columns[0])[y], height=320)
    elif chart == "line":
        st.line_chart(df.set_index(df.columns[0])[y], height=320)
    if show_table:
        st.dataframe(df, width="stretch", hide_index=True)
    with st.expander("이 숫자의 정의와 SQL 보기"):
        st.markdown(definition)
        if caveat:
            st.warning(f"**믿을 수 없는 구간** — {caveat}")
        st.code(sql.strip(), language="sql")
    return df


st.title("배송 지연이 리뷰를 얼마나 깎는가")
st.caption("커머스 주문 데이터로 낮은 리뷰 점수의 원인을 상품과 배송으로 분해합니다.")

tab1, tab2, tab3 = st.tabs(["개요", "지연과 리뷰", "데이터 신뢰도"])

# ────────────────────────────────────────────────────────── 개요
with tab1:
    summary = q("""
        SELECT count(*) AS n,
               round(avg(review_score), 2) AS avg_score,
               round(100.0 * count(*) FILTER (WHERE is_late)
                     / count(*) FILTER (WHERE is_late IS NOT NULL), 1) AS late_rate
        FROM order_fact WHERE has_review
    """).iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("리뷰가 있는 주문", f"{int(summary.n):,}건",
              help="리뷰 없는 주문은 점수를 알 수 없어 제외했습니다.")
    c2.metric("평균 리뷰 점수", f"{summary.avg_score:.2f}점",
              help="리뷰를 남긴 고객의 평균입니다. 전체 고객의 만족도가 아닙니다.")
    c3.metric("지연율", f"{summary.late_rate:.1f}%",
              help="수령일이 기록된 주문만을 분모로 씁니다.")

    st.divider()
    block(
        "월별 리뷰 점수와 지연율",
        """
        SELECT purchase_month AS 월,
               round(avg(review_score), 3) AS 평균점수,
               round(100.0 * count(*) FILTER (WHERE is_late)
                     / nullif(count(*) FILTER (WHERE is_late IS NOT NULL), 0), 1) AS 지연율,
               count(*) AS 주문수
        FROM order_fact
        WHERE has_review
        GROUP BY 월
        ORDER BY 월
        """,
        definition=(
            "- **평균 리뷰 점수**: 해당 월에 *구매된* 주문 중 리뷰가 달린 건의 점수 평균 "
            "(리뷰 작성일 기준으로 바꾸면 그래프가 달라집니다)\n"
            "- **지연율**: 수령일이 예정일보다 하루라도 늦은 주문 ÷ 수령일이 기록된 주문 × 100"
        ),
        caveat="관측 기간의 첫 달과 마지막 달은 기간이 잘려 건수가 적습니다. 양 끝의 급등락은 실제 변화가 아닐 수 있습니다.",
        chart="line", y=["평균점수"],
    )

# ────────────────────────────────────────────────────────── 지연과 리뷰
with tab2:
    st.markdown("이 프로젝트의 핵심 질문입니다. **며칠 늦어질 때부터 고객이 등을 돌리는가.**")
    block(
        "지연 구간별 평균 점수와 1점 비율",
        """
        SELECT delay_bucket AS 지연구간,
               count(*) AS 주문수,
               round(avg(review_score), 3) AS 평균점수,
               round(100.0 * count(*) FILTER (WHERE review_score = 1) / count(*), 1) AS 최저점비율,
               round(100.0 * count(*) FILTER (WHERE review_score >= 4) / count(*), 1) AS 만족비율
        FROM order_fact
        WHERE delay_days IS NOT NULL AND has_review
        GROUP BY 지연구간
        ORDER BY 지연구간
        """,
        definition=(
            "- **지연일** = 실제 수령일 − 약속 예정일. 음수면 약속보다 빨리 도착.\n"
            "- 구간 경계는 `sql/base.sql` 의 `delay_bucket` 한 곳에서만 정의합니다.\n"
            "- 수령일 또는 리뷰가 없는 주문은 이 질문에 답할 수 없으므로 제외했습니다.\n"
            "- **1점 비율을 따로 보는 이유**: 평균은 완만해도 최저점 비율은 급격히 튀는 구간이 있습니다."
        ),
        caveat=(
            "상관관계이지 인과관계가 아닙니다. 늦게 오는 주문은 부피가 크거나 원거리이거나 "
            "특정 셀러에 몰려 있을 수 있고, 그 요인이 점수를 깎았을 수도 있습니다."
        ),
        chart="bar", y=["평균점수"],
    )

    st.divider()
    block(
        "카테고리별 지연 타격도",
        """
        SELECT category AS 카테고리,
               count(*) AS 주문수,
               round(avg(review_score) FILTER (WHERE NOT is_late), 3) AS 정시_평균점수,
               round(avg(review_score) FILTER (WHERE is_late), 3)     AS 지연_평균점수,
               round(avg(review_score) FILTER (WHERE NOT is_late)
                   - avg(review_score) FILTER (WHERE is_late), 3)     AS 하락폭
        FROM order_fact
        WHERE has_review AND is_late IS NOT NULL AND category <> 'unknown'
        GROUP BY 카테고리
        HAVING count(*) >= 200 AND count(*) FILTER (WHERE is_late) >= 30
        ORDER BY 하락폭 DESC NULLS LAST
        LIMIT 15
        """,
        definition=(
            "- **하락폭** = 정시 도착 주문의 평균 점수 − 지연 도착 주문의 평균 점수\n"
            "- 표본이 적으면 평균이 요동치므로 전체 200건·지연 30건 이상인 카테고리만 표시합니다."
        ),
        caveat="최소 표본 기준(200·30)은 임의값입니다. 기준을 바꾸면 순위가 바뀌므로 근거를 docs/METRICS.md 에 남기세요.",
        chart="bar", y=["하락폭"],
    )

    st.divider()
    st.info(
        "**추가할 자리** — `notebooks/03_카테고리_셀러.ipynb` 에서 셀러 순위 쿼리를 완성한 뒤 "
        "여기에 `block(...)` 한 번만 더 부르면 붙습니다."
    )

# ────────────────────────────────────────────────────────── 데이터 신뢰도
with tab3:
    st.markdown(
        "보통의 대시보드는 숫자만 보여줍니다. 이 탭은 **그 숫자를 어디까지 믿어도 되는지** 먼저 밝힙니다."
    )
    block(
        "1. 이 데이터로 답할 수 있는 범위",
        """
        SELECT '전체 주문' AS 항목, count(*) AS 건수 FROM order_fact
        UNION ALL SELECT '배송 완료',  count(*) FILTER (WHERE order_status = 'delivered') FROM order_fact
        UNION ALL SELECT '리뷰 있음',  count(*) FILTER (WHERE has_review) FROM order_fact
        UNION ALL SELECT '수령일 있음', count(*) FILTER (WHERE delivered_at IS NOT NULL) FROM order_fact
        UNION ALL SELECT '분석 가능 (지연일+리뷰)', count(*) FILTER (WHERE delay_days IS NOT NULL AND has_review) FROM order_fact
        ORDER BY 건수 DESC
        """,
        definition="'분석 가능' 건수가 전체보다 많이 작다면, 이 대시보드의 결론은 전체 주문이 아니라 그 부분집합에 대한 이야기입니다.",
        chart=None,
    )

    block(
        "2. 중복 리뷰 처리",
        """
        SELECT count(*) AS 중복_주문수,
               count(*) FILTER (WHERE mx <> mn) AS 점수가_다른_주문수,
               round(avg(mx - mn), 2) AS 평균_점수차
        FROM (
            SELECT order_id, max(CAST(review_score AS INT)) mx, min(CAST(review_score AS INT)) mn
            FROM reviews_raw WHERE review_score IS NOT NULL
            GROUP BY order_id HAVING count(*) > 1
        )
        """,
        definition=(
            "한 주문에 리뷰가 여러 건 달린 경우입니다. 이 프로젝트는 **가장 나중에 작성된 1건**만 씁니다. "
            "점수가 서로 다른 주문이 많다면 이 선택 자체가 결과를 움직이는 결정입니다."
        ),
        caveat="평균으로 처리하는 방법도 있습니다. 두 방식의 결과 차이를 한 번 계산해 기록해 두세요.",
        chart=None,
    )

    st.subheader("3. 지표 정의서")
    md = ROOT / "docs" / "METRICS.md"
    st.markdown(md.read_text(encoding="utf-8") if md.exists() else "`docs/METRICS.md` 가 없습니다.")
