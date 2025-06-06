import streamlit as st
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, date, time as dtime
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="뉴스 키워드 수집기", layout="wide")

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

st.title("📰 뉴스 크롤러 (연합뉴스 + 뉴시스)")
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("시작 날짜", value=date.today())
    start_time = st.time_input("시작 시간", value=dtime(18, 0))
with col2:
    end_date = st.date_input("종료 날짜", value=date.today())
    end_time = st.time_input("종료 시간", value=dtime(22, 0))

selected_groups = st.multiselect("키워드 그룹 선택", options=list(keyword_groups.keys()), default=['시경', '종혜북'])

start_dt = datetime.combine(start_date, start_time)
end_dt = datetime.combine(end_date, end_time)
selected_keywords = [kw for g in selected_groups for kw in keyword_groups[g]]

progress_placeholder = st.empty()
status_placeholder = st.empty()

if st.button("📥 기사 수집 시작"):
    status_placeholder.info("기사 수집을 시작합니다...")

    def highlight_keywords(text, keywords):
        for kw in keywords:
            text = re.sub(f"({re.escape(kw)})", r"**\1**", text)
        return text

    def get_newsis_content(url):
        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                soup = BeautifulSoup(res.text, "html.parser")
                content = soup.find("div", class_="viewer")
                return content.get_text(separator="\n", strip=True) if content else ""
        except:
            return ""

    def get_yonhap_content(url):
        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                soup = BeautifulSoup(res.text, "html.parser")
                content = soup.find("div", class_="story-news article")
                return content.get_text(separator="\n", strip=True) if content else ""
        except:
            return ""

    def fetch_articles_concurrently(article_list, fetch_func):
        results = []
        progress_bar = progress_placeholder.progress(0.0, text="본문 수집 중...")
        total = len(article_list)
        with ThreadPoolExecutor(max_workers=30) as executor:
            future_to_article = {executor.submit(fetch_func, art['url']): art for art in article_list}
            for i, future in enumerate(as_completed(future_to_article)):
                art = future_to_article[future]
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

    def parse_newsis():
        collected, page = [], 1
        status_placeholder.info("🔍 [뉴시스] 목록 수집 중...")
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
                if not href.startswith("/view/"):
                    continue
                match = re.search(r"\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}", time_tag.text)
                if not match:
                    continue
                dt = datetime.strptime(match.group(), "%Y.%m.%d %H:%M:%S")
                if dt < start_dt:
                    return fetch_articles_concurrently(collected, get_newsis_content)
                if start_dt <= dt <= end_dt:
                    collected.append({"source": "뉴시스", "datetime": dt, "title": title, "url": "https://www.newsis.com" + href})
            page += 1
        return fetch_articles_concurrently(collected, get_newsis_content)

    def parse_yonhap():
        collected, page = [], 1
        status_placeholder.info("🔍 [연합뉴스] 목록 수집 중...")
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
                dt_str = time_tag.get_text(strip=True)
                try:
                    dt = datetime.strptime(f"{start_dt.year}-{dt_str}", "%Y-%m-%d %H:%M")
                except:
                    continue
                if dt < start_dt:
                    return fetch_articles_concurrently(collected, get_yonhap_content)
                if start_dt <= dt <= end_dt:
                    collected.append({"source": "연합뉴스", "datetime": dt, "title": title_tag.text.strip(), "url": f"https://www.yna.co.kr/view/{cid}"})
            page += 1
        return fetch_articles_concurrently(collected, get_yonhap_content)

    newsis_articles = parse_newsis()
    yonhap_articles = parse_yonhap()
    articles = newsis_articles + yonhap_articles

    status_placeholder.success(f"✅ 총 {len(articles)}건의 기사를 수집했습니다.")

    if articles:
        st.subheader("📰 기사 내용")
        for art in articles:
            matched_kw = [kw for kw in selected_keywords if kw in art["content"]]
            st.markdown(f"**[{art['title']}]({art['url']})**")
            st.markdown(f"{art['datetime'].strftime('%Y-%m-%d %H:%M')} | 필터링 키워드: {', '.join(matched_kw)}")
            st.markdown(highlight_keywords(art['content'], matched_kw).replace("\n", "\n\n"))
            st.markdown("---")

        st.subheader("📋 복사용 요약 텍스트")
        text_block = ""
        for art in articles:
            text_block += f"△{art['title']}\n-" + art["content"].replace("\n", " ").strip()[:300] + "\n\n"
        st.text_area("복사하세요", text_block, height=300)
