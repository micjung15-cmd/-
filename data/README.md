# 데이터

## 출처

**Brazilian E-Commerce Public Dataset by Olist**
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

2016–2018년 브라질 Olist 마켓플레이스 주문 약 10만 건. 라이선스 CC BY-NC-SA 4.0 (비상업적 이용).

## 받는 방법

1. Kaggle 계정으로 접속 → `Download` → 압축 해제
2. 아래 8개 파일을 `data/raw/` 에 넣습니다 (`olist_geolocation_dataset.csv` 는 쓰지 않습니다)

```
olist_orders_dataset.csv
olist_order_items_dataset.csv
olist_order_reviews_dataset.csv
olist_order_payments_dataset.csv
olist_customers_dataset.csv
olist_products_dataset.csv
olist_sellers_dataset.csv
product_category_name_translation.csv
```

3. `jupyter lab` → `notebooks/01_데이터_품질_진단.ipynb`

## 테이블 관계

```
orders ──┬── customers        (customer_id)
         ├── order_items ──┬── products   (product_id)
         │                 └── sellers    (seller_id)
         ├── order_reviews   (order_id)
         └── order_payments  (order_id)
```

## 미리 알아야 할 함정

| 함정 | 내용 |
|---|---|
| `customer_id` ≠ 사람 | 주문할 때마다 새로 발급되는 값입니다. 실제 사람은 **`customer_unique_id`**. 혼동하면 재구매율이 0%로 나옵니다 |
| 주문당 리뷰 2건 | 한 주문에 리뷰 행이 여러 개 붙은 경우가 있습니다. 어느 것을 남길지가 결과를 바꿉니다 |
| 배송일 결측 | 상태가 `delivered` 인데 수령일이 비어 있는 주문이 있습니다. **0으로 채우면 정시 도착으로 둔갑합니다** |
| 주문당 셀러 여러 명 | `order_items` 는 주문 1건에 여러 행입니다. 주문 단위로 접을 때 대표 셀러 기준을 정해야 합니다 |
| 재구매율이 매우 낮음 | 반복 구매가 드뭅니다. 리텐션 분석은 표본 부족으로 결론이 안 날 수 있습니다 |

## 저장소에 포함하지 않는 이유

라이선스상 재배포가 제한되고 용량이 크며, 누구나 같은 경로로 받을 수 있기 때문입니다.
`.gitignore` 로 `data/raw/*` 를 제외했습니다.
