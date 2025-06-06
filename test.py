import streamlit as st
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo
import re
import asyncio

st.set_page_config(page_title="뉴스 키워드 수집기", layout="wide")

# ✅ 키워드 그룹 정의
keyword_groups = {
    '시경': ['서울경찰청'],
    '본청': ['경찰청'],
    '종혜북': [
        '종로', '종암', '성북', '고려대', '참여연대', '혜화', '동대문', '중랑',
        '성균관대', '한국외대', '서울시립대', '경희대', '경실련', '서울대병원',
        '노원', '강북', '도봉', '북부지법', '북부지검', '상계백병원', '국가인권위원회'
    ],
    '마포중부': [
        '마포', '서대문', '서부', '은평', '서부지검', '서부지법', '연세대',
        '신촌세브란스병원', '군인권센터', '중부', '남대문', '용산', '동국대',
        '숙명여대', '순천향대병원'
    ],
    '영등포관악': [
        '영등포', '양천', '구로', '강서', '남부지검', '남부지법', '여의도성모병원',
        '고대구로병원', '관악', '금천', '동작', '방배', '서울대', '중앙대', '숭실대', '보라매병원'
    ],
    '강남광진': [
        '강남', '서초', '수서', '송파', '강동', '삼성의료원', '현대아산병원',
        '강남세브란스병원', '광진', '성동', '동부지검', '동부지법', '한양대',
        '건국대', '세종대'
    ]
}

# ✅ UI 구성
st.title("\U0001F4F0 뉴스 키워드 수집기")

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

# ✅ 본문 키워드 강조
def highlight_keywords(text, keywords):
    for kw in keywords:
        text = re.sub(f"({re.escape(kw)})", r"**\\1**", text)
    return text

# ✅ 비동기 본문 수집 함수
async def get_content_async(client, url, selector):
    try:
        res = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        content = soup.select_one(selector)
        return content.get_text(separator="\n", strip=True) if content else ""
    except:
        return ""

# ✅ 비동기 기사 병렬 수집
def fetch_articles_concurrently(article_list, selector):
    progress_bar = progress_placeholder.progress(0.0, text="본문 수집 중...")
    total = len(article_list)

    async def collect():
        results = []
        timeout = httpx.Timeout(10.0)
        limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            tasks = [get_content_async(client, art['url'], selector) for art in article_list]
            contents = await asyncio.gather(*tasks)
            for i, content in enumerate(contents):
                progress_bar.progress((i + 1) / total, text=f"{i+1}/{total} 기사 처리 완료")
                if any(kw in content for kw in selected_keywords):
                    article_list[i]['content'] = content
                    results.append(article_list[i])
        return results

    result = asyncio.run(collect())
    progress_placeholder.empty()
    return result

# ✅ 연합뉴스 수집
def parse_yonhap():
    collected, page = [], 1
    status_placeholder.info("\U0001F50D [연합뉴스] 목록 수집 중...")
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

# ✅ 뉴시스 수집
def parse_newsis():
    collected, page = [], 1
    status_placeholder.info("\U0001F50D [뉴시스] 목록 수집 중...")
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

# ✅ 수집 버튼 클릭 시 실행
if st.button("\U0001F4E5 기사 수집 시작"):
    status_placeholder.info("기사 수집을 시작합니다...")
    newsis_articles = parse_newsis()
    yonhap_articles = parse_yonhap()
    articles = newsis_articles + yonhap_articles

    status_placeholder.success(f"✅ 총 {len(articles)}건의 기사를 수집했습니다.")

    if articles:
        st.subheader("\U0001F4F0 기사 내용")
        for art in articles:
            matched_kw = [kw for kw in selected_keywords if kw in art["content"]]
            st.markdown(f"**[{art['title']}]({art['url']})**")
            st.markdown(f"{art['datetime'].strftime('%Y-%m-%d %H:%M')} | 필터링 키워드: {', '.join(matched_kw)}")
            st.markdown(highlight_keywords(art['content'], matched_kw).replace("\n", "\n\n"))
            st.markdown("---")

        # 📋 복사용 텍스트 생성
        st.subheader("\ud83d\udccb 복사용 요약 텍스트")
        text_block = ""
        for art in articles:
            text_block += f"\u25b3{art['title']}\n-" + art["content"].replace("\n", " ").strip()[:300] + "\n\n"

        st.text_area("복사할 내용", text_block, height=300, key="copy_text")

        st.markdown(f"""
        <textarea id="copy-target" style="height:0; opacity:0">{text_block}</textarea>
        <button onclick="navigator.clipboard.writeText(document.getElementById('copy-target').value).then(()=>alert('클립보드에 복사되었습니다!'))"
            style="padding:10px; font-size:16px;">\ud83d\udccb 클립보드에 복사</button>
        """, unsafe_allow_html=True)
