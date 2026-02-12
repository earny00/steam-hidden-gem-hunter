import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
import re
import json
import os
import random
import streamlit.components.v1 as components
from datetime import datetime, timedelta

# --- [중요] 페이지 설정 ---
st.set_page_config(page_title="Steam Hunter", page_icon="🕵️", layout="wide")

# --- 설정 ---
CACHE_FILE = "today_games.json"
USD_RATE = 1450.0

# --- 커스텀 CSS (전체 스타일링) ---
st.markdown("""
<style>
    /* 1. 메인 게임 가격 박스 */
    .big-price-container {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100%;
        width: 100%;
        min-height: 100px;
    }
    .big-price {
        font-size: 2.0rem !important;
        font-weight: 800 !important;
        color: #4CAF50 !important;
        text-align: center;
        background-color: #1b2838;
        padding: 15px 20px;
        border-radius: 12px;
        border: 2px solid #4CAF50;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    }
    
    /* 2. 상단바 잔액 박스 (HTML/CSS) */
    .top-balance-box {
        background-color: #1b2838;
        border: 2px solid #4CAF50; /* 돈은 초록색 */
        border-radius: 10px;
        padding: 0;
        text-align: center;
        color: #4CAF50;
        font-weight: 800;
        font-size: 1.8rem;
        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 100px; /* 높이 고정 (타이머와 맞춤) */
    }
    .top-label {
        font-size: 0.9rem;
        color: #b0b0b0;
        font-weight: normal;
        margin-bottom: 2px;
    }
    
    /* 3. 게임 제목 */
    .game-title {
        font-size: 1.8rem !important;
        font-weight: 800 !important;
        margin-bottom: 8px !important;
        line-height: 1.2 !important;
        color: #1a1a1a !important; 
    }

    /* 4. 인벤토리 스타일 */
    [data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] > div {
        background-color: #1b2838 !important; 
        border: 1px solid #66c0f4 !important; 
        border-radius: 8px !important;
    }
    [data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] p,
    [data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] span,
    [data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] div {
        color: #e0e0e0 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 상태 초기화 ---
if "gallery_open" not in st.session_state:
    st.session_state.gallery_open = False
if "gallery_idx" not in st.session_state:
    st.session_state.gallery_idx = 0

# --- 갤러리 다이얼로그 ---
@st.dialog("📸 스크린샷 뷰어", width="large")
def show_gallery_dialog(screenshots):
    idx = st.session_state.gallery_idx
    if 0 <= idx < len(screenshots):
        st.image(screenshots[idx], caption=f"{idx + 1} / {len(screenshots)}", width="stretch")
    
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("⬅️ 이전 사진", key="gal_prev", width="stretch"):
            st.session_state.gallery_idx = (idx - 1) % len(screenshots)
            st.rerun()
    with c2:
        if st.button("❌ 닫기", key="gal_close", width="stretch"):
            st.session_state.gallery_open = False
            st.rerun()
    with c3:
        if st.button("다음 사진 ➡️", key="gal_next", width="stretch"):
            st.session_state.gallery_idx = (idx + 1) % len(screenshots)
            st.rerun()

# --- 유틸리티 함수 ---
def parse_date(date_str):
    date_str = date_str.strip()
    try:
        clean_str = re.sub(r'[년월일.\s]+', '-', date_str).strip('-') 
        return datetime.strptime(clean_str, "%Y-%m-%d")
    except: pass
    try:
        clean_str = date_str.replace(',', '')
        return datetime.strptime(clean_str, "%b %d %Y")
    except: pass
    try:
        clean_str = date_str.replace(',', '')
        return datetime.strptime(clean_str, "%d %b %Y")
    except: pass
    return None

def parse_price(price_text):
    if "Free" in price_text or "무료" in price_text:
        return 0.0, "$0.00"
    clean_num_str = re.sub(r'[^\d.]', '', price_text)
    if not clean_num_str: return 0.0, "$0.00"
    val = float(clean_num_str)
    if '₩' in price_text or '원' in price_text or val > 200:
        usd_val = val / USD_RATE 
        return round(usd_val, 2), f"${usd_val:.2f}"
    else:
        return val, f"${val:.2f}"

def get_steam_tier_info(rating):
    if rating >= 95: return "압도적으로 긍정적 💖", "blue", "#c5e8ff" 
    elif rating >= 80: return "매우 긍정적 👍", "green", "#d9f7be" 
    elif rating >= 70: return "대체로 긍정적 🙂", "green", "#f6ffed" 
    elif rating >= 40: return "혼합 (Mixed) 😐", "orange", "#fff7e6" 
    elif rating >= 20: return "대체로 부정적 👎", "red", "#fff1f0" 
    else: return "매우/압도적으로 부정적 💔", "red", "#ffa39e" 

def get_score_evaluation(score):
    if score >= 450: return "👑 **게이브 뉴웰의 후계자** (완벽합니다! 당신의 지갑은 명작으로 가득 찼습니다.)"
    elif score >= 350: return "🍷 **게임 소믈리에** (훌륭한 안목입니다. 숨은 보석을 제대로 알아보시는군요.)"
    elif score >= 250: return "🧢 **스팀 고인물** (나쁘지 않습니다. 세일 기간에 활약할 인재입니다.)"
    elif score >= 150: return "😐 **찍먹의 달인** (평범한 결과네요. 조금 더 과감한 투자가 필요합니다.)"
    else: return "💸 **환불 원정대** (지갑을 지키신 건가요? 게임을 좀 더 사보세요!)"

# --- 상세정보 가져오기 ---
def get_game_details(app_id):
    url = "https://store.steampowered.com/api/appdetails"
    params = {"appids": app_id, "l": "korean"} 
    desc_text = "설명 없음"
    tags_text = "태그 정보 없음"
    screenshots = [] 
    try:
        r = requests.get(url, params=params, timeout=3)
        data = r.json()
        if str(app_id) in data and data[str(app_id)]['success']:
            game_data = data[str(app_id)]['data']
            raw_desc = game_data.get('short_description', '설명 없음')
            desc_text = re.sub('<[^<]+?>', '', raw_desc)
            genres = game_data.get('genres', [])
            if genres:
                tags_text = ", ".join([g['description'] for g in genres])
            else:
                tags_text = "장르 미분류"
            raw_screenshots = game_data.get('screenshots', [])
            for shot in raw_screenshots:
                screenshots.append(shot.get('path_full', ''))
    except: pass
    return desc_text, tags_text, screenshots

# --- 크롤링 함수 ---
def fetch_steam_hidden_gems():
    games = []
    today = datetime.now()
    status_text = st.empty()
    status_text.info(f"🕵️ 스팀 탐색 시작... ({today.strftime('%Y-%m-%d')} 기준)")

    base_url = "https://store.steampowered.com/search/results/"
    cookies = {'Steam_Language': 'korean', 'birthtime': '0', 'lastagecheckage': '1-January-1990'}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    page = 0
    while len(games) < 20 and page < 20: 
        status_text.text(f"🔍 {page + 1}페이지 탐색 중... (확보: {len(games)}개)")
        params = {"query": "", "start": page * 25, "count": 25, "dynamic_data": "", "sort_by": "Released_DESC", "category1": "998", "infinite": "1"}
        try:
            r = requests.get(base_url, params=params, headers=headers, cookies=cookies)
            data = r.json()
            soup = BeautifulSoup(data.get('results_html', ''), 'html.parser')
            rows = soup.select('a.search_result_row')
            if not rows: break
            
            for row in rows:
                if len(games) >= 20: break
                title = row.select_one('.title').text.strip()
                game_url = row.get('href', '')
                app_id_match = re.search(r'/app/(\d+)', game_url)
                app_id = app_id_match.group(1) if app_id_match else None
                if not app_id: continue
                
                date_elem = row.select_one('.search_released')
                date_text = date_elem.text.strip() if date_elem else ""
                game_date = parse_date(date_text)
                if not game_date: continue
                
                days_diff = (today - game_date).days
                if days_diff < 0 or days_diff > 35: continue
                
                review_elem = row.select_one('.search_review_summary')
                if not review_elem: continue
                tooltip = review_elem.get('data-tooltip-html', '')
                match = re.search(r'([\d,]+)', tooltip)
                if not match: continue
                review_count = int(match.group(1).replace(',', ''))
                
                if 10 <= review_count <= 2000:
                    img_src = row.select_one('img').get('src', '')
                    price_elem = row.select_one('.discount_final_price') or row.select_one('.search_price')
                    raw_price = price_elem.text.strip() if price_elem else "$0.00"
                    price_val, price_str = parse_price(raw_price)
                    if price_val == 0: continue
                    rating_match = re.search(r'(\d+)%', tooltip)
                    rating = int(rating_match.group(1)) if rating_match else 0
                    
                    print(f"  ★ [확보] {title}")
                    desc_text, tags_text, screenshots = get_game_details(app_id)
                    
                    # 가장 안전한 header.jpg
                    header_img = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg"
                    
                    games.append({
                        "title": title, "price_str": price_str, "price_val": price_val, 
                        "img": header_img, 
                        "thumb": img_src,
                        "reviews": review_count, "rating": rating, 
                        "desc": f"{date_text} 출시 ({days_diff}일 전)", 
                        "full_desc": desc_text, "tags": tags_text,
                        "screenshots": screenshots
                    })
                    time.sleep(0.1)
            page += 1
            time.sleep(0.5)
        except: break
    status_text.empty()
    return games

# --- 데이터 로드 ---
def load_or_fetch_data():
    today_str = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if cached_data.get("date") == today_str and cached_data.get("games"):
                return cached_data.get("games", []), True
        except: pass
    games = fetch_steam_hidden_gems()
    if games:
        save_data = {"date": today_str, "games": games}
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=4)
    return games, False

# --- 초기화 ---
if "games" not in st.session_state:
    with st.spinner("🕵️ 스팀 차트를 분석하는 중..."):
        loaded_games, is_cached = load_or_fetch_data()
        random.shuffle(loaded_games)
        st.session_state.games = loaded_games
        if not st.session_state.games:
            st.error("데이터를 불러오지 못했습니다.")
            st.stop()

if "money" not in st.session_state:
    st.session_state.money = 50.0
    st.session_state.inventory = []
    st.session_state.game_idx = 0
    st.session_state.start_time = None
    st.session_state.game_over = False

# --- UI 메인 ---
if st.session_state.start_time is None:
    st.title("🕵️ Steam Hidden Gem Hunter")
    st.markdown("### $50로 3분 안에 최고의 인디 게임을 찾아라!")
    st.info(f"🎮 분석된 후보 게임: {len(st.session_state.games)}개")
    if st.button("🚀 사냥 시작", type="primary", width="stretch"):
        st.session_state.start_time = time.time()
        st.rerun()

else:
    elapsed = time.time() - st.session_state.start_time
    remaining = 180 - int(elapsed)
    
    if remaining <= 0 or st.session_state.game_idx >= len(st.session_state.games):
        st.session_state.game_over = True
        
    # --- [결과 화면] ---
    if st.session_state.game_over:
        st.title("🏁 최종 결과")
        
        if not st.session_state.inventory:
            st.warning("구매 내역이 없습니다. 너무 신중하셨군요! 🤔")
            total_score = 0
        else:
            total_score = 0
            tier_groups = {"blue": [], "green": [], "orange": [], "red": []}
            tier_titles = {
                "blue": "💖 압도적으로 긍정적",
                "green": "👍 긍정적",
                "orange": "😐 복합적",
                "red": "👎 부정적"
            }

            for g in st.session_state.inventory:
                score = g['price_val'] * (g['rating'] / 10)
                total_score += score
                g['calculated_score'] = score
                label, color, bg_hex = get_steam_tier_info(g['rating'])
                g['bg_hex'] = bg_hex
                tier_groups[color].append(g)

            st.subheader(f"🏆 최종 점수: :rainbow[{total_score:.1f}점]")
            st.info(get_score_evaluation(total_score))
            st.divider()

            for color in ["blue", "green", "orange", "red"]:
                games_in_tier = tier_groups[color]
                if games_in_tier:
                    st.markdown(f"### :{color}[{tier_titles[color]}] ({len(games_in_tier)}개)")
                    for g in games_in_tier:
                        thumb_img = g.get('thumb', g.get('img', ''))
                        html_card = f"""
                        <div style="background-color: {g['bg_hex']}; padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #ddd; color: #333;">
                            <div style="display: flex; align-items: center;">
                                <img src="{thumb_img}" style="width: 150px; height: auto; border-radius: 5px; margin-right: 15px; object-fit: cover;">
                                <div style="flex-grow: 1;">
                                    <h3 style="margin: 0 0 5px 0; font-size: 1.2rem; color: #000;">{g['title']}</h3>
                                    <p style="margin: 0; font-weight: bold; font-size: 1rem;">
                                        💵 {g['price_str']} | ⭐ {g['rating']}% | 🏆 {g['calculated_score']:.1f}점
                                    </p>
                                    <p style="margin: 5px 0 0 0; font-size: 0.85rem; color: #555;">
                                        {g['desc']}
                                    </p>
                                </div>
                            </div>
                        </div>
                        """
                        st.markdown(html_card, unsafe_allow_html=True)
                    st.write("") 

        st.divider()
        c1, c2 = st.columns(2)
        if c1.button("🔄 다시 하기", width="stretch"):
            st.session_state.money = 50.0
            st.session_state.inventory = []
            st.session_state.game_idx = 0
            st.session_state.start_time = None
            st.session_state.game_over = False
            st.session_state.gallery_open = False
            st.rerun()
        if c2.button("🆕 데이터 갱신", width="stretch"):
            if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
            st.session_state.clear()
            st.rerun()
            
    # --- [게임 진행 화면] ---
    else:
        # 상단 HUD 레이아웃
        c1, c2, c3 = st.columns([1, 1, 1])
        
        with c1:
            # [리얼타임 타이머] iframe으로 JS 실행 + CSS로 디자인 통일
            timer_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <style>
                body {{ margin: 0; padding: 0; background: transparent; font-family: "Source Sans Pro", sans-serif; }}
                .top-timer-box {{
                    background-color: #1b2838;
                    border: 2px solid #ff4b4b; /* 시간은 긴박하게 빨간색 */
                    border-radius: 10px;
                    padding: 0;
                    text-align: center;
                    color: #ff4b4b;
                    font-weight: 800;
                    font-size: 28px; /* 1.8rem과 유사 */
                    box-shadow: 0 2px 5px rgba(0,0,0,0.3);
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    height: 96px; /* Streamlit markdown 박스와 높이 맞춤 */
                    box-sizing: border-box;
                }}
                .top-label {{
                    font-size: 14px;
                    color: #b0b0b0;
                    font-weight: normal;
                    margin-bottom: 2px;
                }}
            </style>
            </head>
            <body>
                <div class="top-timer-box">
                    <div class="top-label">⏳ 남은 시간</div>
                    <div id="timer">{remaining}</div>
                </div>
                <script>
                    var timeleft = {remaining};
                    var timerElement = document.getElementById("timer");
                    var downloadTimer = setInterval(function(){{
                        if(timeleft <= 0){{
                            timerElement.innerHTML = "0";
                            clearInterval(downloadTimer);
                        }} else {{
                            timerElement.innerHTML = timeleft;
                        }}
                        timeleft -= 1;
                    }}, 1000);
                </script>
            </body>
            </html>
            """
            components.html(timer_html, height=100)
        
        with c2:
            # 잔액 표시 (HTML Box)
            balance_html = f"""
            <div class='top-balance-box'>
                <div class='top-label'>💰 현재 잔액</div>
                <div>${st.session_state.money:.2f}</div>
            </div>
            """
            st.markdown(balance_html, unsafe_allow_html=True)
            
        with c3:
            # 버튼 높이를 맞추기 위해 여백 추가 hack
            st.write("") 
            st.write("")
            if st.button("🏳️ 조기 종료", width="stretch"):
                st.session_state.game_over = True
                st.session_state.gallery_open = False 
                st.rerun()

        st.divider()

        col_main, col_sidebar = st.columns([3, 1])
        
        with col_sidebar:
            st.subheader("🎒 인벤토리")
            if not st.session_state.inventory:
                st.caption("비어있음")
            else:
                for idx, item in enumerate(st.session_state.inventory):
                    with st.container(border=True):
                        st.markdown(f"<div style='color: #66c0f4; font-weight: bold; margin-bottom: 5px;'>{item['title']}</div>", unsafe_allow_html=True)
                        thumb_img = item.get('thumb', item.get('img', ''))
                        st.image(thumb_img, width="stretch")
                        if st.button("반품", key=f"ret_{idx}", width="stretch"):
                            st.session_state.inventory.remove(item)
                            st.session_state.money += item['price_val']
                            st.session_state.gallery_open = False 
                            st.rerun()

        with col_main:
            # game 변수 정의 (안전)
            game = st.session_state.games[st.session_state.game_idx]
            is_owned = any(g['title'] == game['title'] for g in st.session_state.inventory)
            
            with st.container(border=True):
                c_img, c_info, c_price = st.columns([1.3, 2.7, 1], vertical_alignment="center")
                
                with c_img:
                    if game['img']: 
                        st.image(game['img'])
                    else:
                        st.text("No Image")
                
                with c_info:
                    st.markdown(f"<p class='game-title'>{game['title']}</p>", unsafe_allow_html=True)
                    if is_owned: st.success("✅ 보유 중")
                    
                    st.caption(f"📅 {game['desc']}")
                    st.markdown(f"🏷️ {game['tags']}")
                
                with c_price:
                    price_html = f"""
                    <div class='big-price-container'>
                        <div class='big-price'>{game['price_str']}</div>
                    </div>
                    """
                    st.markdown(price_html, unsafe_allow_html=True)

            st.info(f"📜 {game['full_desc']}")
            
            if game.get('screenshots'):
                st.markdown("##### 📸 스크린샷 (확대하려면 돋보기 클릭)")
                sc_cols = st.columns(3)
                shots = game['screenshots'][:3]
                for i, shot_url in enumerate(shots):
                    with sc_cols[i]:
                        st.image(shot_url, width="stretch")
                        if st.button(f"🔍 확대", key=f"zoom_{i}", width="stretch"):
                            st.session_state.gallery_idx = i
                            st.session_state.gallery_open = True
                            st.rerun()

            st.write("")
            b1, b2, b3 = st.columns([1, 2, 1])
            with b1:
                if st.session_state.game_idx > 0:
                    if st.button("⬅️ 이전", width="stretch"):
                        st.session_state.game_idx -= 1
                        st.session_state.gallery_open = False 
                        st.rerun()
            with b2:
                if is_owned:
                    if st.button("↩️ 환불하기", type="secondary", width="stretch"):
                        if game in st.session_state.inventory:
                            st.session_state.inventory.remove(game)
                            st.session_state.money += game['price_val']
                            st.toast("↩️ 환불 완료!")
                            st.session_state.gallery_open = False
                            st.rerun()
                else:
                    if st.button("💸 구매하기", type="primary", width="stretch"):
                        if st.session_state.money >= game['price_val']:
                            st.session_state.money -= game['price_val']
                            st.session_state.inventory.append(game)
                            st.toast("💰 구매 성공!")
                            st.session_state.gallery_open = False
                            st.rerun()
                        else:
                            st.error("잔액 부족")
            with b3:
                is_last = st.session_state.game_idx == len(st.session_state.games) - 1
                lbl = "결과 보기 🏁" if is_last else "다음 ⏭️"
                if st.button(lbl, width="stretch"):
                    st.session_state.game_idx += 1
                    st.session_state.gallery_open = False 
                    st.rerun()

            if st.session_state.gallery_open and game.get('screenshots'):
                show_gallery_dialog(game['screenshots'])