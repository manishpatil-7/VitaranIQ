"""
Feature Engineering for VitaranIQ LightGBM Quantile Forecaster.
Implements FR-FCT-01..03 and AIML Design §4.
Constructs 21 leakage-free features strictly using data <= origin day t
plus known-future promo and festival calendars.
"""

from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


FEATURE_NAMES = [
    "s1", "s7_norm", "s14_norm", "s28_norm",
    "sd7_norm", "sd28_norm", "trend",
    "wd_factor_sum", "promo_last28",
    "n_promo_win", "n_fest_win", "n_hol_win", "days_to_fest",
    "dow", "month",
    "store_idx", "sku_idx", "cat_idx",
    "size_mult", "price", "shelf_life"
]


def compute_weekday_indices(sales_df: pd.DataFrame, max_train_day: int = 620) -> Dict[int, float]:
    """Estimate mean sales by weekday / overall mean on training segment only."""
    train_sales = sales_df[sales_df["day"] <= max_train_day]
    overall_mean = train_sales["units"].mean()
    if overall_mean <= 0:
        overall_mean = 1.0

    dow_means = train_sales.groupby("dow")["units"].mean()
    wi = {}
    for dow in range(7):
        m = dow_means.get(dow, overall_mean)
        wi[dow] = float(m / overall_mean)
    return wi


def build_feature_matrix_for_origins(
    sales_df: pd.DataFrame,
    calendar_df: pd.DataFrame,
    stores_df: pd.DataFrame,
    products_df: pd.DataFrame,
    origins: List[int],
    weekday_indices: Dict[int, float],
    is_training: bool = True,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[Dict]]:
    """
    Build feature matrix X, targets Y, and scales for a list of origin days t.
    Returns:
    - X: (N, 21) feature matrix
    - y_ratio: (N,) target ratio Y / scale (or None if not training)
    - scales: (N,) scale values
    - meta: list of dicts with (origin_day, store_id, sku_id)
    """
    # Create fast lookups
    # sales pivot or 3D array: days 1..740, stores 25, products 12
    store_ids = sorted(stores_df["store_id"].unique())
    sku_ids = sorted(products_df["sku_id"].unique())
    s_map = {sid: i for i, sid in enumerate(store_ids)}
    p_map = {pid: i for i, pid in enumerate(sku_ids)}

    n_stores = len(store_ids)
    n_skus = len(sku_ids)
    max_day = calendar_df["day"].max()

    # Sales units array (max_day + 1, n_stores, n_skus)
    units_arr = np.zeros((max_day + 1, n_stores, n_skus), dtype=np.float32)
    promo_arr = np.zeros((max_day + 1, n_stores, n_skus), dtype=np.int8)

    for row in sales_df.itertuples():
        if row.day <= max_day and row.store_id in s_map and row.sku_id in p_map:
            s_i = s_map[row.store_id]
            p_i = p_map[row.sku_id]
            units_arr[row.day, s_i, p_i] = row.units
            promo_arr[row.day, s_i, p_i] = row.promo_flag

    # Calendar lookup
    cal_arr = np.zeros((max_day + 1, 4), dtype=np.int32)  # [dow, month, is_holiday, is_festival]
    for row in calendar_df.itertuples():
        if row.day <= max_day:
            cal_arr[row.day] = [row.dow, row.month, row.is_holiday, row.is_festival]

    # Precompute days to next festival for each day
    days_to_fest = np.zeros(max_day + 1, dtype=np.float32)
    next_f = 999
    for d in range(max_day, 0, -1):
        if cal_arr[d, 3] == 1:
            next_f = 0
        else:
            next_f = min(next_f + 1, 60)
        days_to_fest[d] = float(next_f)

    # Static lookups
    store_size = {row.store_id: row.size_mult for row in stores_df.itertuples()}
    sku_cat = {row.sku_id: row.category for row in products_df.itertuples()}
    categories = sorted(list(set(sku_cat.values())))
    cat_map = {cat: i for i, cat in enumerate(categories)}

    sku_price = {row.sku_id: row.price_paise / 100.0 for row in products_df.itertuples()}
    sku_shelf = {row.sku_id: row.shelf_life_days for row in products_df.itertuples()}

    rows_X = []
    rows_y = []
    rows_scales = []
    rows_meta = []

    for t in origins:
        if t < 28 or t + 9 > max_day:
            continue

        dow_t = cal_arr[t, 0]
        month_t = cal_arr[t, 1]
        dtf_t = days_to_fest[t]

        # Target window days: t+1 .. t+9
        target_days = np.arange(t + 1, t + 10)
        target_dow = cal_arr[target_days, 0]
        wd_factor_sum = sum(weekday_indices.get(dw, 1.0) for dw in target_dow)
        n_fest_win = float(np.sum(cal_arr[target_days, 3]))
        n_hol_win = float(np.sum(cal_arr[target_days, 2]))

        for s_id in store_ids:
            s_i = s_map[s_id]
            s_mult = float(store_size[s_id])

            for sku_id in sku_ids:
                p_i = p_map[sku_id]
                c_idx = cat_map[sku_cat[sku_id]]
                price = float(sku_price[sku_id])
                shelf = float(sku_shelf[sku_id])

                # Sales history slices up to origin day t
                hist_28 = units_arr[t - 27:t + 1, s_i, p_i]  # 28 days
                s1 = float(units_arr[t, s_i, p_i])
                s7 = float(np.sum(hist_28[-7:]))
                s14 = float(np.sum(hist_28[-14:]))
                s28 = float(np.sum(hist_28))

                sd7 = float(np.std(hist_28[-7:]))
                sd28 = float(np.std(hist_28))

                scale = max(s28 * (9.0 / 28.0), 5.0)

                s7_norm = s7 / scale
                s14_norm = s14 / scale
                s28_norm = s28 / scale
                sd7_norm = sd7 / (scale / 9.0)
                sd28_norm = sd28 / (scale / 9.0)

                trend = (s7 / 7.0) / max(s28 / 28.0, 0.5)

                promo_last28 = float(np.sum(promo_arr[t - 27:t + 1, s_i, p_i]))
                n_promo_win = float(np.sum(promo_arr[target_days, s_i, p_i]))

                feat_vector = [
                    s1, s7_norm, s14_norm, s28_norm,
                    sd7_norm, sd28_norm, trend,
                    wd_factor_sum, promo_last28,
                    n_promo_win, n_fest_win, n_hol_win, dtf_t,
                    float(dow_t), float(month_t),
                    float(s_i), float(p_i), float(c_idx),
                    s_mult, price, shelf
                ]

                rows_X.append(feat_vector)
                rows_scales.append(scale)
                rows_meta.append({"origin_day": t, "store_id": s_id, "sku_id": sku_id})

                if is_training:
                    # Target Y = cumulative 9-day sum
                    y_true = float(np.sum(units_arr[target_days, s_i, p_i]))
                    rows_y.append(y_true / scale)

    X = np.array(rows_X, dtype=np.float32)
    scales = np.array(rows_scales, dtype=np.float32)
    y = np.array(rows_y, dtype=np.float32) if is_training else None

    return X, y, scales, rows_meta
