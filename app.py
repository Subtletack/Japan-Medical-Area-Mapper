import streamlit as st
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib
import japanize_matplotlib
from shapely.affinity import translate
import os

st.set_page_config(page_title="Japan Medical Area Mapper", layout="wide")

# タイトル
st.title("Japan Medical Area Mapper")
st.markdown("二次医療圏単位でのデータ可視化（ヒートマップ・コロプレスマップ）ツール")

# サイドバー：設定エリア
st.sidebar.header("1. データと設定")

# 年度の選択（浜松市や秋田県の区割りに対応）
year_choice = st.sidebar.radio(
    "マップの区割り年度を選択してください",
    ("2024年以降 (秋田県・浜松市の新区分)", "2023年以前")
)

# データのアップロード
uploaded_file = st.sidebar.file_uploader("データファイル (CSVまたはExcel) をアップロード", type=["csv", "xlsx"])

@st.cache_data
def load_map_data(year_choice):
    base_dir = os.path.dirname(__file__)
    if "2024" in year_choice:
        file_path = os.path.join(base_dir, "data", "map_2024_simplified.geojson")
    else:
        file_path = os.path.join(base_dir, "data", "map_2023_simplified.geojson")
    
    if os.path.exists(file_path):
        return gpd.read_file(file_path)
    return None

gdf_map = load_map_data(year_choice)

if gdf_map is None:
    st.error("マップデータが見つかりません。必要なGeoJSONファイルが `data/` フォルダに配置されているか確認してください。")
    st.stop()

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            # SJISやUTF-8などエンコーディング対応
            try:
                df_user = pd.read_csv(uploaded_file, encoding='utf-8')
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df_user = pd.read_csv(uploaded_file, encoding='shift_jis')
        else:
            df_user = pd.read_excel(uploaded_file)
            
        # コード列の自動選択（デフォルト値を設定しつつ、ユーザーが手動で選べるようにする）
        candidate_cols = [c for c in df_user.columns if 'コード' in c or 'code' in c.lower()]
        default_index = 0
        if len(candidate_cols) > 0:
            default_index = list(df_user.columns).index(candidate_cols[0])
            
        code_col = st.sidebar.selectbox("二次医療圏コード（4桁）が入っている列を選択", df_user.columns, index=default_index)
            
        df_user[code_col] = df_user[code_col].astype(str).str.zfill(4)
        
        # 描画対象の列を選択
        target_col = st.sidebar.selectbox("色分けに使用するデータ列を選択", [c for c in df_user.columns if c != code_col])
        
        # 結合
        gdf_merged = gdf_map.merge(df_user, left_on='二次医療圏', right_on=code_col, how='left')
        
        st.sidebar.header("2. 描画オプション")
        plot_type = st.sidebar.radio("変数の種類", ["連続変数 (グラデーション)", "カテゴリカル変数 (離散色)"])
        
        # カラーマップ選択
        if "連続変数" in plot_type:
            cmap = st.sidebar.selectbox("カラーマップ", ["OrRd", "Blues", "Greens", "viridis", "coolwarm", "YlOrRd"])
            # 境界値の調整
            min_val = float(df_user[target_col].min())
            max_val = float(df_user[target_col].max())
            
            # NoneやNaNが含まれている場合のエラー回避
            if pd.isna(min_val) or pd.isna(max_val):
                min_val, max_val = 0.0, 100.0
                
            vmin, vmax = st.sidebar.slider("数値の境界 (最小値 - 最大値)", 
                                           min_value=min_val, 
                                           max_value=max_val, 
                                           value=(min_val, max_val))
        else:
            cmap = st.sidebar.selectbox("カラーマップ", ["tab10", "Set1", "Set2", "Set3", "Pastel1"])
            vmin, vmax = None, None
            
        # 描画ボタン
        if st.sidebar.button("マップを描画する"):
            with st.spinner('地図を描画しています...'):
                fig, ax = plt.subplots(1, 1, figsize=(14, 16), dpi=150)
                
                # 沖縄県の移動処理（描画用コピー）
                gdf_plot = gdf_merged.copy()
                is_okinawa = gdf_plot['prefecture'] == '47'
                
                # 移動距離設定
                x_offset = 6.0
                y_offset = 15.0
                gdf_plot.loc[is_okinawa, 'geometry'] = gdf_plot[is_okinawa].geometry.translate(xoff=x_offset, yoff=y_offset)
                
                # プロット
                if "連続変数" in plot_type:
                    gdf_plot.plot(
                        ax=ax, 
                        column=target_col,
                        cmap=cmap,
                        vmin=vmin,
                        vmax=vmax,
                        edgecolor='#444444',
                        linewidth=0.2,
                        legend=True,
                        missing_kwds={'color': 'lightgrey', 'label': 'データなし'}
                    )
                else:
                    gdf_plot.plot(
                        ax=ax, 
                        column=target_col,
                        cmap=cmap,
                        categorical=True,
                        edgecolor='#444444',
                        linewidth=0.2,
                        legend=True,
                        missing_kwds={'color': 'lightgrey', 'label': 'データなし'}
                    )
                
                # 都道府県境界を太く描画する（都道府県単位で結合）
                # 簡略化によって生じた微小な隙間（cleft/gap）を埋めるため、バッファを広げて結合した後に縮める Closing 処理を行います
                gdf_temp = gdf_plot.copy()
                gdf_temp['geometry'] = gdf_temp.geometry.buffer(0.005)
                gdf_pref_bound = gdf_temp.dissolve(by='prefecture')
                gdf_pref_bound['geometry'] = gdf_pref_bound.geometry.buffer(-0.005)
                gdf_pref_bound.boundary.plot(ax=ax, edgecolor='#111111', linewidth=0.5)
                
                # 表示範囲の限定と枠線
                ax.set_xlim([128.3, 148.9])
                ax.set_ylim([27.0, 45.7])
                ax.plot([128.3, 134.5, 134.5], [38.5, 38.5, 45.7], color='gray', linestyle='--', linewidth=1.0)
                ax.set_axis_off()
                
                st.pyplot(fig, dpi=300, use_container_width=True)
                st.success("描画完了！画像を保存する場合は、右クリック（または長押し）から「名前を付けて画像を保存」を選択してください。")

    except Exception as e:
        st.error(f"データの処理中にエラーが発生しました: {e}")
else:
    st.info("← 左のサイドバーからデータファイル（CSV/Excel）をアップロードしてください。")
    st.markdown("""
    **【データフォーマットの注意】**
    アップロードするファイルは、必ず **「二次医療圏」または「二次医療圏コード」** という名前の列（4桁のコード、例：`0101`）を含んでいる必要があります。
    """)
