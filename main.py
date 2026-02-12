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

# --- 국가별 설정 ---
REGION_CONFIG = {
    "Korea (KRW)": {"code": "kr", "symbol": "₩", "budget": 70000, "flag": "🇰🇷"},
    "USA (USD)":   {"code": "us", "symbol": "$", "budget": 50,    "flag": "🇺🇸"},
    "Japan (JPY)": {"code": "jp", "symbol": "¥", "budget": 7000,  "flag": "🇯🇵"},
}

# --- 사이드바: 국가 선택 ---
with st.sidebar:
    st.header("🌐 지역 설정")
    selected_region = st.selectbox("접속 국가를 선택하세요", list(REGION_CONFIG.keys()), index=0)
    current_config = REGION_CONFIG[selected_region]
    CC_CODE = current_config["code"]
    CURRENCY = current_config["symbol"]
    START_BUDGET = current_config["budget"]
    CACHE_FILE = f"today_games_{CC_CODE}.json"
    
    st.caption(f"현재 스토어: {selected_region} ({current_config['flag']})")
    st.info("※ 이미지가 깨지거나 오류가 나면 '데이터 갱신' 버튼을 눌러주세요.")

# --- 커스텀 CSS ---
st.markdown(f"""
<style>
    /* 가격 박스 */
    .big-price-container {{
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100%;
        width: 100%;
        min-height: 100px;
    }}
    .big-price {{
        font-size: 2.0rem !important;
        font-weight: 800 !important;
        color: #4CAF50 !important;
        text-align: center;
        background-color: #1b2838;
        padding: 15px 20px;
        border-radius: 12px;
        border: 2px solid #4CAF50;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    }}
    /* 상단바 잔액 박스 (복구됨!) */
    .top-balance-box {{
        background-color: #1b2838;
        border: 2px solid #4CAF50;
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
        height: 100px;
    }}
    .top-label {{
        font-size: 0.9rem;
        color: #b0b0b0;
        font-weight: normal;
        margin-bottom: 2px;
    }}
    /* 게임 제목 (가독성) */
    .game-title {{
        font-size: 1.8rem !important;
        font-weight: 800 !important;
        margin-bottom: 8px !important;
        line-height: 1.2 !important;
        color: var(--text-color) !important; 
    }}
    /* 인벤토리 스타일 */
    [data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] > div {{
        background-color: #1b2838 !important; 
        border: 1px solid #66c0f4 !important; 
        border-radius: 8px !important;
    }}
    [data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] p,
    [data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] span,
    [data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] div {{
        color: #e0e0e0 !important;
    }}
</style>
""", unsafe_allow_html=True)

# --- 상태 초기화 ---
if "gallery_open" not in st.session_state: st.session_state.gallery_open = False
if "gallery_idx" not in st.session_state: st.session_state.gallery_idx = 0
if "last_region" not in st.session_state: st.session_state.last_region = CC_CODE

if st.session_state.last_region != CC_CODE:
    st.session_state.money = START_BUDGET
    st.session_state.inventory = []
    st.session_state.game_idx = 0
    st.session_state.start_time = None
    st.session_state.game_over = False
    st.session_state.last_region = CC_CODE
    if "games" in st.session_state: del st.session_state["games"]
    st.rerun()

# --- 갤러리 다이얼로그 ---
@st.dialog("📸 스크린샷 뷰어", width="large")
def show_gallery_dialog(screenshots):
    idx = st.session_state.gallery_idx
    if 0 <= idx < len(screenshots):
        st.image(screenshots[idx], caption=f"{idx + 1} / {len(screenshots)}", width="stretch")
    c1, c2, c3 = st.columns([1, 1, 1])
    if c1.button("⬅️ 이전", key="gal_prev", width="stretch"):
        st.session_state.gallery_idx = (idx - 1) % len(screenshots)
        st.rerun()
    if c2.button("❌ 닫기", key="gal_close", width="stretch"):
        st.session_state.gallery_open = False
        st.rerun()
    if c3.button("다음 ➡️", key="gal_next", width="stretch"):
        st.session_state.gallery_idx = (idx + 1) % len(screenshots)
        st.rerun()

# --- 유틸리티 함수 ---
def parse_date(date_str):
    try: return datetime.strptime(re.sub(r'[년월일.\s]+', '-', date_str.strip()).strip('-'), "%Y-%m-%d")
    except: pass
    try: return datetime.strptime(date_str.replace(',', ''), "%b %d %Y")
    except: pass
    try: return datetime.strptime(date_str.replace(',', ''), "%d %b %Y")
    except: return None

def parse_price(price_text):
    if "Free" in price_text or "무료" in price_text: return 0.0, f"{CURRENCY}0"
    clean_num = re.sub(r'[^\d.]', '', price_text)
    if not clean_num: return 0.0, f"{CURRENCY}0"
    return float(clean_num), price_text

def get_steam_tier_info(rating):
    if rating >= 95: return "압도적으로 긍정적 💖", "blue", "#c5e8ff" 
    elif rating >= 80: return "매우 긍정적 👍", "green", "#d9f7be" 
    elif rating >= 70: return "대체로 긍정적 🙂", "green", "#f6ffed" 
    elif rating >= 40: return "혼합 (Mixed) 😐", "orange", "#fff7e6" 
    elif rating >= 20: return "대체로 부정적 👎", "red", "#fff1f0" 
    else: return "매우/압도적으로 부정적 💔", "red", "#ffa39e" 

def get_score_evaluation(score, budget):
    ratio = score / budget if budget > 0 else 0
    if ratio >= 8: return "👑 **게이브 뉴웰의 후계자** (완벽합니다! 당신의 지갑은 명작으로 가득 찼습니다.)"
    elif ratio >= 6: return "🍷 **게임 소믈리에** (훌륭한 안목입니다. 숨은 보석을 제대로 알아보시는군요.)"
    elif ratio >= 4: return "🧢 **스팀 고인물** (나쁘지 않습니다. 세일 기간에 활약할 인재입니다.)"
    elif ratio >= 2: return "😐 **찍먹의 달인** (평범한 결과네요. 조금 더 과감한 투자가 필요합니다.)"
    else: return "💸 **환불 원정대** (지갑을 지키신 건가요? 게임을 좀 더 사보세요!)"

def get_game_details(app_id):
    url = "https://store.steampowered.com/api/appdetails"
    try:
        r = requests.get(url, params={"appids": app_id, "l": "korean", "cc": CC_CODE}, timeout=3)
        data = r.json()
        if str(app_id) in data and data[str(app_id)]['success']:
            gd = data[str(app_id)]['data']
            desc = re.sub('<[^<]+?>', '', gd.get('short_description', '설명 없음'))
            tags = ", ".join([g['description'] for g in gd.get('genres', [])])
            shots = [s.get('path_full', '') for s in gd.get('screenshots', [])]
            return desc, tags, shots
    except: pass
    return "설명 없음", "장르 미분류", []

# --- 크롤링 함수 (이미지 복구 강화) ---
def fetch_steam_hidden_gems():
    games = []
    today = datetime.now()
    status_text = st.empty()
    status_text.info(f"🕵️ 스팀 탐색 시작... ({today.strftime('%Y-%m-%d')} 기준, 지역: {CC_CODE.upper()})")

    base_url = "https://store.steampowered.com/search/results/"
    cookies = {'Steam_Language': 'korean', 'birthtime': '0', 'lastagecheckage': '1-January-1990'}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    page = 0
    while len(games) < 30 and page < 20: 
        status_text.text(f"🔍 {page + 1}페이지 탐색 중... (확보: {len(games)}개)")
        params = {"query": "", "start": page*25, "count": 25, "dynamic_data": "", "sort_by": "Released_DESC", "category1": "998", "infinite": "1", "cc": CC_CODE}
        
        try:
            r = requests.get(base_url, params=params, headers=headers, cookies=cookies)
            soup = BeautifulSoup(r.json().get('results_html', ''), 'html.parser')
            rows = soup.select('a.search_result_row')
            if not rows: break
            
            for row in rows:
                if len(games) >= 20: break
                title = row.select_one('.title').text.strip()
                game_url = row.get('href', '')
                app_id_match = re.search(r'/app/(\d+)', game_url)
                if not app_id_match: continue
                app_id = app_id_match.group(1)
                
                date_elem = row.select_one('.search_released')
                if not date_elem: continue
                game_date = parse_date(date_elem.text.strip())
                if not game_date: continue
                
                days_diff = (today - game_date).days
                if days_diff < 0 or days_diff > 35: continue # 35일 이내 신작만
                
                review_elem = row.select_one('.search_review_summary')
                if not review_elem: continue
                match = re.search(r'([\d,]+)', review_elem.get('data-tooltip-html', ''))
                if not match: continue
                review_count = int(match.group(1).replace(',', ''))
                
                if 10 <= review_count <= 2000:
                    # [이미지 복구 로직] 1.srcset -> 2.src -> 3.Fallback
                    img_tag = row.select_one('img')
                    img_src = ""
                    if img_tag:
                        srcset = img_tag.get('srcset', '')
                        if srcset:
                            img_src = srcset.split(',')[0].strip().split(' ')[0]
                        if not img_src or len(img_src) < 10:
                            img_src = img_tag.get('src', '')
                    
                    # 그래도 없거나 이상하면 공식 CDN 주소 강제 할당
                    if not img_src or len(img_src) < 10 or 'blank' in img_src:
                        img_src = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg"

                    price_elem = row.select_one('.discount_final_price') or row.select_one('.search_price')
                    raw_price = price_elem.text.strip() if price_elem else f"{CURRENCY}0"
                    price_val, price_str = parse_price(raw_price)
                    if price_val == 0: continue
                    
                    rating_match = re.search(r'(\d+)%', review_elem.get('data-tooltip-html', ''))
                    rating = int(rating_match.group(1)) if rating_match else 0
                    
                    print(f"  ★ [확보] {title}")
                    desc_text, tags_text, screenshots = get_game_details(app_id)
                    
                    games.append({
                        "title": title, "price_str": price_str, "price_val": price_val, 
                        "img": img_src,
                        "thumb": img_src, # [KeyError 방지] thumb 키 명시적 추가
                        "reviews": review_count, "rating": rating, 
                        "desc": f"{date_elem.text.strip()} 출시 ({days_diff}일 전)", 
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
                cached = json.load(f)
            if cached.get("date") == today_str and cached.get("games"):
                return cached.get("games", []), True
        except: pass
    games = fetch_steam_hidden_gems()
    if games:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"date": today_str, "games": games}, f, ensure_ascii=False, indent=4)
    return games, False

# --- 초기화 ---
if "games" not in st.session_state:
    with st.spinner(f"🕵️ {selected_region} 스토어 탐색 중..."):
        loaded_games, _ = load_or_fetch_data()
        random.shuffle(loaded_games)
        st.session_state.games = loaded_games
        if not st.session_state.games: st.error("데이터 로드 실패."); st.stop()

if "money" not in st.session_state:
    st.session_state.money = START_BUDGET
    st.session_state.inventory = []
    st.session_state.game_idx = 0
    st.session_state.start_time = None
    st.session_state.game_over = False

# --- UI 메인 ---
if st.session_state.start_time is None:
    st.title("🕵️ Steam Hidden Gem Hunter")
    budget_fmt = f"{st.session_state.money:,.0f}" if CC_CODE in ['kr', 'jp'] else f"{st.session_state.money:.2f}"
    st.markdown(f"### {CURRENCY}{budget_fmt}로 3분 안에 최고의 인디 게임을 찾아라!")
    st.info(f"🎮 분석된 후보 게임: {len(st.session_state.games)}개 (지역: {CC_CODE.upper()})")
    if st.button("🚀 사냥 시작", type="primary", width="stretch"):
        st.session_state.start_time = time.time()
        st.rerun()

else:
    elapsed = time.time() - st.session_state.start_time
    remaining = 180 - int(elapsed)
    
    if remaining <= 0 or st.session_state.game_idx >= len(st.session_state.games):
        st.session_state.game_over = True
        
    # --- 결과 화면 ---
    if st.session_state.game_over:
        st.title("🏁 최종 결과")
        if not st.session_state.inventory: st.warning("구매 내역이 없습니다!")
        else:
            total = sum([g['price_val'] * (g['rating']/10) for g in st.session_state.inventory])
            st.subheader(f"🏆 최종 점수: :rainbow[{total:,.0f}점]")
            st.info(get_score_evaluation(total, START_BUDGET))
            st.divider()
            
            # 티어별 출력
            tier_groups = {"blue":[], "green":[], "orange":[], "red":[]}
            tier_titles = {"blue":"💖 압도적 긍정","green":"👍 긍정","orange":"😐 복합","red":"👎 부정"}
            for g in st.session_state.inventory:
                _, c, bg = get_steam_tier_info(g['rating'])
                g['bg'] = bg; tier_groups[c].append(g)
            
            for c in ["blue","green","orange","red"]:
                if tier_groups[c]:
                    st.markdown(f"### :{c}[{tier_titles[c]}]")
                    for g in tier_groups[c]:
                        st.markdown(f"""
                        <div style="background-color:{g['bg']}; padding:15px; border-radius:10px; margin-bottom:10px; border:1px solid #ddd; color:#333;">
                            <div style="display:flex; align-items:center;">
                                <img src="{g['img']}" style="width:150px; border-radius:5px; margin-right:15px;">
                                <div>
                                    <h3 style="margin:0; font-size:1.2rem; color:#000;">{g['title']}</h3>
                                    <p style="margin:0; font-weight:bold;">💵 {g['price_str']} | ⭐ {g['rating']}%</p>
                                </div>
                            </div>
                        </div>""", unsafe_allow_html=True)
        
        st.divider()
        c1, c2 = st.columns(2)
        if c1.button("🔄 다시 하기", width="stretch"):
            st.session_state.money = START_BUDGET
            st.session_state.inventory = []
            st.session_state.game_idx = 0
            st.session_state.start_time = None
            st.session_state.game_over = False
            st.rerun()
        if c2.button("🆕 데이터 갱신", width="stretch"):
            if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
            st.session_state.clear(); st.rerun()

    # --- 게임 진행 ---
    else:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            components.html(f"""<div style='background:#1b2838; border:2px solid #ff4b4b; border-radius:10px; text-align:center; color:#ff4b4b; font-weight:800; font-size:28px; height:96px; display:flex; flex-direction:column; justify-content:center; font-family:sans-serif;'><div style='font-size:14px; color:#b0b0b0; font-weight:normal;'>⏳ 남은 시간</div><div id='t'>{remaining}</div></div><script>var t={remaining},e=document.getElementById('t'),i=setInterval(()=>{{t<=0?(e.innerHTML='0',clearInterval(i)):e.innerHTML=t,t--}},1000)</script>""", height=100)
        with c2:
            m_fmt = f"{st.session_state.money:,.0f}" if CC_CODE in ['kr','jp'] else f"{st.session_state.money:.2f}"
            st.markdown(f"<div class='top-balance-box'><div class='top-label'>💰 현재 잔액</div><div>{CURRENCY}{m_fmt}</div></div>", unsafe_allow_html=True)
        with c3:
            st.write(""); st.write("")
            if st.button("🏳️ 조기 종료", width="stretch"):
                st.session_state.game_over = True; st.rerun()
        
        components.html(f"<script>setTimeout(function(){{window.location.reload();}}, 1000);</script>", height=0)

        st.divider()
        col_m, col_s = st.columns([3, 1])
        
        with col_s:
            st.subheader("🎒 인벤토리")
            for i, item in enumerate(st.session_state.inventory):
                with st.container(border=True):
                    st.markdown(f"<div style='color:#66c0f4; font-weight:bold;'>{item['title']}</div>", unsafe_allow_html=True)
                    # [KeyError 방지] thumb가 없으면 img 사용
                    st.image(item.get('thumb', item['img']), width="stretch")
                    if st.button("반품", key=f"ret_{i}", width="stretch"):
                        st.session_state.inventory.remove(item)
                        st.session_state.money += item['price_val']
                        st.rerun()

        with col_m:
            game = st.session_state.games[st.session_state.game_idx]
            is_owned = any(g['title'] == game['title'] for g in st.session_state.inventory)
            
            with st.container(border=True):
                ci, cd, cp = st.columns([1.3, 2.7, 1], vertical_alignment="center")
                with ci: st.image(game['img'], width="stretch") # 안전한 이미지 사용
                with cd:
                    st.markdown(f"<p class='game-title'>{game['title']}</p>", unsafe_allow_html=True)
                    if is_owned: st.success("✅ 보유 중")
                    st.caption(f"📅 {game['desc']}")
                    st.markdown(f"🏷️ {game['tags']}")
                with cp:
                    st.markdown(f"<div class='big-price-container'><div class='big-price'>{game['price_str']}</div></div>", unsafe_allow_html=True)
            
            st.info(f"📜 {game['full_desc']}")
            
            if game.get('screenshots'):
                st.markdown("##### 📸 스크린샷")
                sc = st.columns(3)
                for i, s in enumerate(game['screenshots'][:3]):
                    with sc[i]:
                        st.image(s, width="stretch")
                        if st.button("🔍 확대", key=f"z_{i}", width="stretch"):
                            st.session_state.gallery_idx = i; st.session_state.gallery_open = True; st.rerun()

            st.write("")
            b1, b2, b3 = st.columns([1, 2, 1])
            if b1.button("⬅️ 이전", width="stretch") and st.session_state.game_idx > 0:
                st.session_state.game_idx -= 1; st.rerun()
            
            if is_owned:
                if b2.button("↩️ 환불하기", width="stretch"):
                    st.session_state.inventory.remove(game)
                    st.session_state.money += game['price_val']
                    st.toast("환불 완료!"); st.rerun()
            else:
                if b2.button("💸 구매하기", type="primary", width="stretch"):
                    if st.session_state.money >= game['price_val']:
                        st.session_state.money -= game['price_val']
                        st.session_state.inventory.append(game)
                        st.toast("구매 성공!"); st.rerun()
                    else: st.error("잔액 부족")
            
            lbl = "결과 보기 🏁" if st.session_state.game_idx == len(st.session_state.games)-1 else "다음 ⏭️"
            if b3.button(lbl, width="stretch"):
                st.session_state.game_idx += 1; st.rerun()

            if st.session_state.gallery_open and game.get('screenshots'):
                show_gallery_dialog(game['screenshots'])