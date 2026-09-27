-- 이 파일 하나가 '숫자의 정의'를 담당합니다.
-- 노트북과 대시보드가 모두 이 파일을 먼저 실행하므로,
-- 지표 기준을 바꾸고 싶으면 여기만 고치면 양쪽에 동시에 반영됩니다.
--
-- {data} 자리에는 CSV 폴더 경로가 들어갑니다. (노트북: ../data/raw, 앱: data/raw)
-- DuckDB는 CSV를 그대로 읽을 수 있어서 따로 적재할 필요가 없습니다.

CREATE OR REPLACE VIEW orders   AS SELECT * FROM read_csv_auto('{data}/olist_orders_dataset.csv');
CREATE OR REPLACE VIEW items    AS SELECT * FROM read_csv_auto('{data}/olist_order_items_dataset.csv');
CREATE OR REPLACE VIEW reviews_raw AS SELECT * FROM read_csv_auto('{data}/olist_order_reviews_dataset.csv');
CREATE OR REPLACE VIEW customers AS SELECT * FROM read_csv_auto('{data}/olist_customers_dataset.csv');
CREATE OR REPLACE VIEW products AS SELECT * FROM read_csv_auto('{data}/olist_products_dataset.csv');
CREATE OR REPLACE VIEW sellers  AS SELECT * FROM read_csv_auto('{data}/olist_sellers_dataset.csv');
CREATE OR REPLACE VIEW category_ko AS SELECT * FROM read_csv_auto('{data}/product_category_name_translation.csv');


-- 리뷰: 한 주문에 리뷰가 여러 건 달린 경우가 있어 '가장 나중 것' 1건만 남깁니다.
-- (평균으로 바꾸려면 아래 ROW_NUMBER 대신 AVG를 쓰세요. 어느 쪽이든 docs/METRICS.md에 이유를 적을 것)
CREATE OR REPLACE VIEW reviews AS
SELECT order_id, review_score, reviewed_at FROM (
    SELECT order_id,
           CAST(review_score AS INTEGER) AS review_score,
           CAST(review_creation_date AS TIMESTAMP) AS reviewed_at,
           ROW_NUMBER() OVER (PARTITION BY order_id
                              ORDER BY CAST(review_creation_date AS TIMESTAMP) DESC, review_id DESC) AS rn
    FROM reviews_raw
    WHERE review_score IS NOT NULL
) WHERE rn = 1;


-- 주문 상품: 주문 1건에 여러 행이므로 주문 단위로 접습니다.
-- 대표 셀러는 '금액이 가장 큰 상품의 셀러'로 정했습니다. (여러 셀러가 섞인 주문의 한계는 문서에 기록)
CREATE OR REPLACE VIEW order_items AS
WITH agg AS (
    SELECT order_id, count(*) AS item_count,
           sum(CAST(price AS DOUBLE)) AS gmv,
           sum(CAST(freight_value AS DOUBLE)) AS freight
    FROM items GROUP BY order_id
),
top_item AS (
    SELECT order_id, seller_id, product_id FROM (
        SELECT order_id, seller_id, product_id,
               ROW_NUMBER() OVER (PARTITION BY order_id
                                  ORDER BY CAST(price AS DOUBLE) DESC, order_item_id) AS rn
        FROM items
    ) WHERE rn = 1
)
SELECT a.*, t.seller_id, t.product_id FROM agg a LEFT JOIN top_item t USING (order_id);


-- ★ 분석의 기준 테이블. 1행 = 주문 1건.
--   노트북과 대시보드는 전부 이 뷰만 봅니다. 같은 지표가 화면마다 다르게 나오는 일을 막기 위해서입니다.
CREATE OR REPLACE VIEW order_fact AS
SELECT
    o.order_id,
    c.customer_unique_id,                 -- ※ customer_id 가 아니라 이 컬럼이 '사람'입니다
    c.customer_state,
    o.order_status,
    CAST(o.order_purchase_timestamp AS TIMESTAMP)      AS purchased_at,
    date_trunc('month', CAST(o.order_purchase_timestamp AS TIMESTAMP)) AS purchase_month,
    CAST(o.order_delivered_customer_date AS TIMESTAMP) AS delivered_at,

    -- 배송 지연일 = 실제 수령일 − 약속 예정일.  음수면 약속보다 빨리 온 것.
    -- 수령일이 없으면 NULL. 0으로 채우면 '정시 도착'으로 둔갑하므로 절대 채우지 않습니다.
    CASE WHEN o.order_delivered_customer_date IS NULL THEN NULL
         ELSE date_diff('day', CAST(o.order_estimated_delivery_date AS TIMESTAMP),
                               CAST(o.order_delivered_customer_date AS TIMESTAMP)) END AS delay_days,

    CASE WHEN o.order_delivered_customer_date IS NULL THEN NULL
         ELSE date_diff('day', CAST(o.order_estimated_delivery_date AS TIMESTAMP),
                               CAST(o.order_delivered_customer_date AS TIMESTAMP)) > 0 END AS is_late,

    -- 지연 구간. 지금은 임의 구간이니 02 노트북에서 분포를 보고 근거를 만들어 고치세요.
    CASE
        WHEN o.order_delivered_customer_date IS NULL THEN '미상'
        WHEN date_diff('day', CAST(o.order_estimated_delivery_date AS TIMESTAMP), CAST(o.order_delivered_customer_date AS TIMESTAMP)) <= -8 THEN '① 8일+ 조기'
        WHEN date_diff('day', CAST(o.order_estimated_delivery_date AS TIMESTAMP), CAST(o.order_delivered_customer_date AS TIMESTAMP)) <= -1 THEN '② 1~7일 조기'
        WHEN date_diff('day', CAST(o.order_estimated_delivery_date AS TIMESTAMP), CAST(o.order_delivered_customer_date AS TIMESTAMP)) =  0 THEN '③ 정시'
        WHEN date_diff('day', CAST(o.order_estimated_delivery_date AS TIMESTAMP), CAST(o.order_delivered_customer_date AS TIMESTAMP)) <=  7 THEN '④ 1~7일 지연'
        WHEN date_diff('day', CAST(o.order_estimated_delivery_date AS TIMESTAMP), CAST(o.order_delivered_customer_date AS TIMESTAMP)) <= 20 THEN '⑤ 8~20일 지연'
        ELSE '⑥ 21일+ 지연'
    END AS delay_bucket,

    oi.item_count, oi.gmv, oi.freight, oi.seller_id, s.seller_state,
    COALESCE(ck.product_category_name_english, p.product_category_name, 'unknown') AS category,
    r.review_score,
    (r.review_score IS NOT NULL) AS has_review
FROM orders o
LEFT JOIN customers   c  ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON o.order_id = oi.order_id
LEFT JOIN products    p  ON oi.product_id = p.product_id
LEFT JOIN category_ko ck ON p.product_category_name = ck.product_category_name
LEFT JOIN sellers     s  ON oi.seller_id = s.seller_id
LEFT JOIN reviews     r  ON o.order_id = r.order_id;
