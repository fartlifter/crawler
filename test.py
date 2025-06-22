import streamlit as st
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="통신기사 수집기_경찰팀", layout="wide")

# === 키워드 카테고리 ===
keyword_groups = {
    '시경': ['서울경찰청'],
    '본청': ['경찰청'],
    '종혜북': ['종로', '종암', '성북', '고려대', '참여연대', '혜화', '동대문', '중랑',
        '성균관대', '한국외대', '서울시립대', '경희대', '경실련', '서울대병원',
        '노원', '강북', '도봉', '북부지법', '북부지검', '상계백병원', '국가인권위원회'],
    '마포중부': ['마포', '서대문', '서부', '은평', '서부지검', '서부지법', '연세대', '반부패범죄수사대', '공공범죄수사대',
        '금융범죄수사대', '마약범죄수사대', '신촌세브란스병원', '군인권센터', '중부', '중구', 
        '남대문', '용산', '동국대', '숙명여대', '순천향대병원'],
    '남부지검법': ['남부지검', '남부지법'],
    '영등포관악': ['영등포', '양천', '구로', '강서', '여의도성모병원',
        '고대구로병원', '관악', '금천', '동작', '방배', '서울대', '중앙대', '숭실대', '보라매병원'],
    '강남광진': ['강남', '서초', '수서', '송파', '강동', '삼성의료원', '현대아산병원',
        '강남세브란스병원', '광진', '성동', '동부지검', '동부지법', '한양대', '건국대', '세종대']
}

st.title("📰 통신기사 수집기_경찰팀")
st.markdown("✅ 통신기사를 수집하고 선택한 키워드가 본문에 포함된 기사만 필터링합니다. 선택한 기사만 최하단 복사용 박스에 표시됩니다. 업데이트:250622")

now = datetime.now(ZoneInfo("Asia/Seoul"))
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("시작 날짜", value=now.date())
    start_time = st.time_input("시작 시간", value=dtime(0, 0))
with col2:
    end_date = st.date_input("종료 날짜", value=now.date())
    end_time = st.time_input("종료 시간", value=dtime(now.hour, now.minute))

selected_groups = st.multiselect("키워드 그룹 선택", options=list(keyword_groups.keys()), default=['시경', '종혜북'])
selected_keywords = [kw for g in selected_groups for kw in keyword_groups[g]]

start_dt = datetime.combine(start_date, start_time).replace(tzinfo=ZoneInfo("Asia/Seoul"))
end_dt = datetime.combine(end_date, end_time).replace(tzinfo=ZoneInfo("Asia/Seoul"))

progress_placeholder = st.empty()
status_placeholder = st.empty()

# ✅ 세션 상태 초기화
if "articles" not in st.session_state:
    st.session_state.articles = []

def highlight_keywords(text, keywords):
    for kw in keywords:
        text = re.sub(f"({re.escape(kw)})", r'<mark style="background-color: #fffb91">\1</mark>', text)
    return text

def get_content(url, selector):
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(res.text, "html.parser")
            content = soup.select_one(selector)
            return content.get_text(separator="\n", strip=True) if content else ""
    except:
        return ""

def fetch_articles_concurrently(article_list, selector):
    results = []
    progress_bar = progress_placeholder.progress(0.0, text="본문 수집 중...")
    total = len(article_list)
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(get_content, art['url'], selector): art for art in article_list}
        for i, future in enumerate(as_completed(futures)):
            art = futures[future]
            try:
                content = future.result()
                if any(kw in content for kw in selected_keywords):
                    art['content'] = content
                    results.append(art)
            except:
                continue
            progress_bar.progress((i + 1) / total, text=f"{i+1}/{total} 기사 처리 완료")
    progress_placeholder.empty()
    return results

def parse_yonhap():
    collected, page = [], 1
    status_placeholder.info("🔍 [연합뉴스] 기사 목록 수집 중...")
    while True:
        url = f"https://www.yna.co.kr/news/{page}?site=navi_latest_depth01"
        res = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5.0)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select("ul.list01 > li[data-cid]")
        if not items:
            break
        for item in items:
            cid = item.get("data-cid")
            title_tag = item.select_one(".title01")
            time_tag = item.select_one(".txt-time")
            if not (cid and title_tag and time_tag):
                continue
            try:
                dt = datetime.strptime(f"{start_dt.year}-{time_tag.text.strip()}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Seoul"))
            except:
                continue
            if dt < start_dt:
                return fetch_articles_concurrently(collected, "div.story-news.article")
            if start_dt <= dt <= end_dt:
                collected.append({
                    "source": "연합뉴스", "datetime": dt, "title": title_tag.text.strip(),
                    "url": f"https://www.yna.co.kr/view/{cid}"
                })
        page += 1
    return fetch_articles_concurrently(collected, "div.story-news.article")

def parse_newsis():
    collected, page = [], 1
    status_placeholder.info("🔍 [뉴시스] 기사 목록 수집 중...")
    while True:
        url = f"https://www.newsis.com/realnews/?cid=realnews&day=today&page={page}"
        res = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5.0)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select("ul.articleList2 > li")
        if not items:
            break
        for item in items:
            title_tag = item.select_one("p.tit > a")
            time_tag = item.select_one("p.time")
            if not (title_tag and time_tag):
                continue
            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")
            match = re.search(r"\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}", time_tag.text)
            if not match:
                continue
            dt = datetime.strptime(match.group(), "%Y.%m.%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
            if dt < start_dt:
                return fetch_articles_concurrently(collected, "div.viewer")
            if start_dt <= dt <= end_dt:
                collected.append({
                    "source": "뉴시스", "datetime": dt, "title": title,
                    "url": "https://www.newsis.com" + href
                })
        page += 1
    return fetch_articles_concurrently(collected, "div.viewer")

# ✅ 기사 수집 버튼
if st.button("📥 기사 수집 시작"):
    status_placeholder.info("기사 수집을 시작합니다...")
    newsis_articles = parse_newsis()
    yonhap_articles = parse_yonhap()
    st.session_state.articles = newsis_articles + yonhap_articles
    status_placeholder.success(f"✅ 총 {len(st.session_state.articles)}건의 기사를 수집했습니다.")

# ✅ 기사 표시 및 선택
selected_articles = []
articles = st.session_state.articles
if articles:
    st.subheader("📰 기사 내용")
    for i, art in enumerate(articles):
        matched_kw = [kw for kw in selected_keywords if kw in art["content"]]
        with st.expander(art["title"], expanded=False):
            is_selected = st.checkbox("이 기사 선택", key=f"select_{i}")
            st.markdown(f"[원문 보기]({art['url']})")
            st.markdown(f"{art['datetime'].strftime('%Y-%m-%d %H:%M')} | 필터링 키워드: {', '.join(matched_kw)}")
            st.markdown(highlight_keywords(art['content'], matched_kw).replace("\n", "<br>"), unsafe_allow_html=True)
            if is_selected:
                selected_articles.append(art)

# ✅ 복사용 텍스트 박스
if selected_articles:
    st.subheader("📋 복사용 텍스트 (선택된 기사만)")
    text_block = ""
    for row in selected_articles:
        text_block += f"△{row['title']}\n- {row['content'].strip()}\n\n"
    st.code(text_block.strip(), language="markdown")
    st.caption("✅ 복사 버튼을 눌러 선택한 기사 내용을 복사하세요.")
else:
    if articles:
        st.subheader("📋 복사용 텍스트 (선택된 기사 없음)")
        st.info("체크박스로 기사 선택 시 이 영역에 텍스트가 표시됩니다.")
