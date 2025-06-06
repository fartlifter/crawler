import streamlit as st
import httpx
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime, date, time as dtime
import re
from zoneinfo import ZoneInfo

st.set_page_config(page_title="뉴스 키워드 수집기", layout="wide")

# ✅ 키워드 그룹 정의
keyword_groups = {
    '시경': ['서울경찰청'],
    '본청': ['경찰청'],
    '종혜북': ['종로', '종암', '성북', '고려대', '참여연대', '혜화', '동대문', '중랑',
             '성균관대', '한국외대', '서울시립대', '경희대', '경실련', '서울대병원',
             '노원', '강북', '도봉', '북부지법', '북부지검', '상계백병원', '국가인권위원회'],
    '마포중부': ['마포', '서대문', '서부', '은평', '서부지검', '서부지법', '연세대',
              '신촌세브란스병원', '군인권센터', '중부', '남대문', '용산', '동국대',
              '숙명여대', '순천향대병원'],
    '영등포관악': ['영등포', '양천', '구로', '강서', '남부지검', '남부지법', '여의도성모병원',
               '고대구로병원', '관악', '금천', '동작', '방배', '서울대', '중앙대', '숭실대', '보라매병원'],
    '강남광진': ['강남', '서초', '수서', '송파', '강동', '삼성의료원', '현대아산병원',
              '강남세브란스병원', '광진', '성동', '동부지검', '동부지법', '한양대', '건국대', '세종대']
}

# ✅ UI 구성
st.title("📰 뉴스 크롤러 (연합뉴스 + 뉴시스)")
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("시작 날짜", value=date.today())
    start_time = st.time_input("시작 시간", value=dtime(0, 0))
with col2:
    end_date = st.date_input("종료 날짜", value=date.today())
    now_seoul = datetime.now(ZoneInfo("Asia/Seoul")).time().replace(second=0, microsecond=0)
    end_time = st.time_input("종료 시간", value=now_seoul)

selected_groups = st.multiselect("키워드 그룹 선택", options=list(keyword_groups.keys()), default=['시경', '종혜북'])

# ✅ 시간 및 키워드 설정
start_dt = datetime.combine(start_date, start_time)
end_dt = datetime.combine(end_date, end_time)
selected_keywords = [kw for g in selected_groups for kw in keyword_groups[g]]
keyword_pattern = re.compile("|".join(re.escape(k) for k in selected_keywords))

progress_placeholder = st.empty()
status_placeholder = st.empty()

def highlight_keywords(text, keywords):
    for kw in keywords:
        text = re.sub(f"({re.escape(kw)})", r"<mark>\1</mark>", text)
    return text

# ✅ 본문 비동기 수집
async def fetch_content_async(url, selector):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(res.text, "html.parser")
            content = soup.find("div", class_=selector)
            return content.get_text(separator="\n", strip=True) if content else ""
    except:
        return ""

async def fetch_articles_async(article_list, selector):
    results = []
    progress_bar = progress_placeholder.progress(0.0, text="본문 수집 중...")
    total = len(article_list)

    tasks = []
    for art in article_list:
        tasks.append(fetch_content_async(art['url'], selector))

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for i, (art, content) in enumerate(zip(article_list, responses)):
        status_placeholder.info(f"📄 처리 중: {art['title']}")
        if isinstance(content, str) and keyword_pattern.search(content):
            art['content'] = content
            results.append(art)
        progress_bar.progress((i + 1) / total, text=f"{i+1}/{total} 기사 처리 완료")

    progress_placeholder.empty()
    status_placeholder.success("✅ 본문 수집 완료")
    return results

# ✅ 뉴시스 목록 수집 (비동기 병렬화)
async def fetch_newsis_page(page):
    url = f"https://www.newsis.com/realnews/?cid=realnews&day=today&page={page}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select("ul.articleList2 > li")
        results = []
        for item in items:
            title_tag = item.select_one("p.tit > a")
            time_tag = item.select_one("p.time")
            if not (title_tag and time_tag):
                continue
            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")
            if not href.startswith("/view/"):
                continue
            match = re.search(r"\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}", time_tag.text)
            if not match:
                continue
            dt = datetime.strptime(match.group(), "%Y.%m.%d %H:%M:%S")
            if start_dt <= dt <= end_dt:
                results.append({"source": "뉴시스", "datetime": dt, "title": title, "url": "https://www.newsis.com" + href})
        return results
    except:
        return []

async def parse_newsis_async():
    pages = range(1, 6)  # 최대 5페이지까지만 병렬 수집 (필요시 조절)
    status_placeholder.info("🔍 [뉴시스] 기사 목록 수집 중...")
    all_results = await asyncio.gather(*(fetch_newsis_page(p) for p in pages))
    collected = [item for sublist in all_results for item in sublist]
    return await fetch_articles_async(collected, "viewer")

# ✅ 연합뉴스 수집 (동기 방식 유지)
def parse_yonhap():
    collected, page = [], 1
    status_placeholder.info("🔍 [연합뉴스] 목록 수집 중...")
    while True:
        url = f"https://www.yna.co.kr/news/{page}?site=navi_latest_depth01"
        try:
            res = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5.0)
        except:
            break
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
            dt_str = time_tag.get_text(strip=True)
            try:
                dt = datetime.strptime(f"{start_dt.year}-{dt_str}", "%Y-%m-%d %H:%M")
            except:
                continue
            if dt < start_dt:
                return asyncio.run(fetch_articles_async(collected, "story-news article"))
            if start_dt <= dt <= end_dt:
                collected.append({
                    "source": "연합뉴스",
                    "datetime": dt,
                    "title": title_tag.text.strip(),
                    "url": f"https://www.yna.co.kr/view/{cid}"
                })
        page += 1
    return asyncio.run(fetch_articles_async(collected, "story-news article"))

# ✅ 실행 버튼
if st.button("📥 기사 수집 시작"):
    status_placeholder.info("기사 수집을 시작합니다...")
    newsis_articles = asyncio.run(parse_newsis_async())
    yonhap_articles = parse_yonhap()
    articles = newsis_articles + yonhap_articles

    status_placeholder.success(f"✅ 총 {len(articles)}건의 기사를 수집했습니다.")

    if articles:
        st.subheader("📰 기사 내용")
        for art in articles:
            matched_kw = [kw for kw in selected_keywords if kw in art["content"]]
            st.markdown(f"**[{art['title']}]({art['url']})**")
            st.markdown(f"{art['datetime'].strftime('%Y-%m-%d %H:%M')} | 필터링 키워드: {', '.join(matched_kw)}")
            st.markdown(highlight_keywords(art['content'], matched_kw).replace("\n", "<br>"), unsafe_allow_html=True)
            st.markdown("---")

        st.subheader("📋 복사용 요약 텍스트")
        text_block = ""
        for art in articles:
            text_block += f"△{art['title']}\n-" + art["content"].replace("\n", " ").strip()[:300] + "\n\n"
        st.text_area("복사하세요", text_block, height=300)
