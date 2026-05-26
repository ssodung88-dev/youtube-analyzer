import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime, timedelta, timezone
from collections import Counter
from io import BytesIO
import re
import os
import whisper
import yt_dlp
import uuid
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
from matplotlib.ticker import FuncFormatter

st.set_page_config(layout="wide")

API_KEY = st.secrets["YOUTUBE_API_KEY"]

youtube = build(
    "youtube",
    "v3",
    developerKey=API_KEY
)

FAVORITE_FILE = "favorite_channels.csv"
FAVORITE_ITEMS_FILE = "favorite_items.csv"


def load_favorites():

    if os.path.exists(FAVORITE_FILE):

        df_fav = pd.read_csv(FAVORITE_FILE)

        return df_fav["채널명"].tolist()

    return []


def load_favorite_items():

    if os.path.exists(FAVORITE_ITEMS_FILE):

        return pd.read_csv(FAVORITE_ITEMS_FILE)

    return pd.DataFrame()


def save_favorites(favorite_channels):

    df_fav = pd.DataFrame(
        favorite_channels,
        columns=["채널명"]
    )

    df_fav.to_csv(
        FAVORITE_FILE,
        index=False,
        encoding="utf-8-sig"
    )


def save_favorite_items(favorite_items):

    favorite_items.to_csv(
        FAVORITE_ITEMS_FILE,
        index=False,
        encoding="utf-8-sig"
    )

if "favorite_channels" not in st.session_state:
    st.session_state["favorite_channels"] = load_favorites()

if "favorite_items" not in st.session_state:
    st.session_state["favorite_items"] = load_favorite_items()


def parse_duration(duration):

    minutes = 0
    seconds = 0

    minute_match = re.search(r"(\d+)M", duration)
    second_match = re.search(r"(\d+)S", duration)

    if minute_match:
        minutes = int(minute_match.group(1))

    if second_match:
        seconds = int(second_match.group(1))

    return f"{minutes}:{seconds:02d}"


def get_transcript(video_id):

    try:

        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=["ko"]
        )

        full_text = " ".join(
            [item["text"] for item in transcript]
        )

        return full_text

    except:

        return "공식 자막 수집 불가"


def get_whisper_transcript(video_url):

    audio_filename = f"temp_audio_{uuid.uuid4().hex}.webm"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": audio_filename,
        "quiet": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    model = whisper.load_model("medium")

    result = model.transcribe(
        audio_filename,
        fp16=False,
        language="ko"
    )

    if os.path.exists(audio_filename):
        os.remove(audio_filename)

    return result["text"]

def get_recent_channel_videos(channel_id, max_results=20):

    channel_response = youtube.channels().list(
        part="contentDetails",
        id=channel_id
    ).execute()

    uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    playlist_response = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads_playlist_id,
        maxResults=max_results
    ).execute()

    video_ids = [
        item["snippet"]["resourceId"]["videoId"]
        for item in playlist_response["items"]
    ]

    videos_response = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids)
    ).execute()

    recent_videos = []

    for video in videos_response["items"]:

        snippet = video["snippet"]
        stats = video["statistics"]

        recent_videos.append({
            "제목": snippet["title"],
            "게시일": snippet["publishedAt"][:10],
            "조회수": int(stats.get("viewCount", 0)),
            "좋아요": int(stats.get("likeCount", 0)),
            "댓글수": int(stats.get("commentCount", 0)),
            "영상링크": f"https://www.youtube.com/watch?v={video['id']}"
        })

    return pd.DataFrame(recent_videos)

    try:

        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=["ko"]
        )

        text = " ".join(
            [x["text"] for x in transcript]
        )

        return text

    except:

        return "자막 수집 불가"


def to_excel(df):

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False
        )

    return output.getvalue()


st.title("유튜브 쇼핑 쇼츠 분석기")

# =========================
# 사이드바 필터
# =========================

st.sidebar.title("필터 설정")

shorts_filter = st.sidebar.selectbox(
    "영상 유형",
    [
        "전체",
        "쇼츠만",
        "일반영상만"
    ]
)

sort_option = st.sidebar.selectbox(
    "정렬 기준",
    [
        "떡상점수 높은순",
        "조회수 높은순",
        "참여율 높은순",
        "조회수배율 높은순",
        "최신순"
    ]
)

crazy_view_filter = st.sidebar.checkbox(
    "🚀 구독자 대비 미친 조회수만 보기"
)

min_ratio = st.sidebar.number_input(
    "최소 조회수배율",
    min_value=0.0,
    value=0.0,
    step=1.0
)

min_engagement = st.sidebar.number_input(
    "최소 참여율(%)",
    min_value=0.0,
    value=0.0,
    step=0.1
)

if "view_mode_radio" not in st.session_state:
    st.session_state["view_mode_radio"] = "검색 결과 보기"

view_mode = st.sidebar.radio(
    "화면 선택",
    ["검색 결과 보기", "⭐ 즐겨찾기 채널 보기"],
    key="view_mode_radio"
)

show_favorites_only = view_mode == "⭐ 즐겨찾기 채널 보기"

if show_favorites_only:
    st.subheader("⭐ 즐겨찾기 채널 목록")

    if "favorite_items" in st.session_state and not st.session_state["favorite_items"].empty:

        fav_display_df = st.session_state["favorite_items"].copy()

        if "번호" in fav_display_df.columns:
            fav_display_df = fav_display_df.drop(columns=["번호"])

        fav_display_df.insert(
            0,
            "번호",
            range(1, len(fav_display_df) + 1)
        )

        fav_display_df["⭐즐겨찾기"] = True
        cols = fav_display_df.columns.tolist()

        cols.insert(
            1,
            cols.pop(cols.index("⭐즐겨찾기"))
        )

        fav_display_df = fav_display_df[cols]

        favorite_edited_df = st.data_editor(
            fav_display_df,
            column_config={
                "썸네일": st.column_config.ImageColumn(
                    "썸네일",
                    width="small"
                ),
                "제목": st.column_config.TextColumn(
                    "제목",
                    width="large"
                ),
                "영상링크": st.column_config.LinkColumn(
                    "영상 링크",
                    width="small"
                ),
                "⭐즐겨찾기": st.column_config.CheckboxColumn(
                    "⭐즐겨찾기",
                    width="small"
                ),
            },
            hide_index=True,
            use_container_width=True,
            height=500,
            key="favorite_editor"
        )
        unchecked_favorites = favorite_edited_df[
            favorite_edited_df["⭐즐겨찾기"] == False
        ]["채널명"].tolist()

        if unchecked_favorites:

            st.session_state["favorite_items"] = (
                st.session_state["favorite_items"][
                    ~st.session_state["favorite_items"]["채널명"].isin(
                        unchecked_favorites
                    )
                ]
            )

            st.session_state["favorite_channels"] = (
                st.session_state["favorite_items"]["채널명"]
                .tolist()
            )

            save_favorites(
                st.session_state["favorite_channels"]
            )

            save_favorite_items(
                st.session_state["favorite_items"]
            )

            st.rerun()

        st.subheader("자막 수집")

        fav_df = st.session_state["favorite_items"].copy()
        
        selected_title = st.selectbox(
            "즐겨찾기 영상 선택",
            fav_df["제목"].tolist(),
            key="favorite_caption_select"
        )

        selected_row = fav_df[
            fav_df["제목"] == selected_title
        ].iloc[0]

        st.write("선택한 영상:", selected_row["제목"])

        if st.button("Whisper로 자막 생성", key="favorite_whisper_button"):

            with st.spinner("음성을 분석해서 자막을 생성하는 중이에요..."):

                transcript = get_whisper_transcript(
                    selected_row["영상링크"]
                )

                st.session_state["favorite_transcript_result"] = transcript
                st.session_state["favorite_transcript_title"] = selected_row["제목"]

        if "favorite_transcript_result" in st.session_state:

            st.write(
                "자막 생성 영상:",
                st.session_state["favorite_transcript_title"]
            )

            st.text_area(
                "생성된 자막",
                st.session_state["favorite_transcript_result"],
                height=300,
                key="favorite_transcript_area"
            )

    else:
        st.info("아직 즐겨찾기한 영상 정보가 없어요.")

    st.stop()

# =========================
# 검색 영역
# =========================

keyword = st.text_input(
    "검색 키워드 입력",
    value=""
)

if keyword.strip() == "":
    keyword = "a"

period = st.selectbox(
    "검색 기간",
    [
        "전체",
        "7일 이내",
        "1개월 이내",
        "3개월 이내",
        "6개월 이내",
        "1년 이내"
    ]
)

now = datetime.now(timezone.utc)

if period == "7일 이내":
    published_after = (now - timedelta(days=7)).isoformat()
elif period == "1개월 이내":
    published_after = (now - timedelta(days=30)).isoformat()
elif period == "3개월 이내":
    published_after = (now - timedelta(days=90)).isoformat()
elif period == "6개월 이내":
    published_after = (now - timedelta(days=180)).isoformat()
elif period == "1년 이내":
    published_after = (now - timedelta(days=365)).isoformat()
else:
    published_after = None

search_button = st.button("검색")

# =========================
# 검색 실행
# =========================

if search_button:

    search_params = {
        "q": keyword,
        "part": "snippet",
        "type": "video",
        "maxResults": 50,
        "order": "viewCount",
        "regionCode": "KR",
        "relevanceLanguage": "ko",
    }

    if published_after:
        search_params["publishedAfter"] = published_after

    search_response = youtube.search().list(**search_params).execute()

    videos = []

    for item in search_response["items"]:

        video_id = item["id"]["videoId"]

        video_response = youtube.videos().list(
            part="statistics,contentDetails,snippet",
            id=video_id
        ).execute()

        if len(video_response["items"]) == 0:
            continue

        video_item = video_response["items"][0]

        stats = video_item["statistics"]

        snippet = video_item["snippet"]

        published_at = snippet["publishedAt"]

        published_date = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )

        now = datetime.now(timezone.utc)

        if period == "1개월 이내":
            limit_date = now - timedelta(days=30)

        elif period == "3개월 이내":
            limit_date = now - timedelta(days=90)

        elif period == "6개월 이내":
            limit_date = now - timedelta(days=180)

        elif period == "1년 이내":
            limit_date = now - timedelta(days=365)

        else:
            limit_date = None

        if limit_date:

            if published_date < limit_date:
                continue

        views = int(stats.get("viewCount", 0))

        likes = int(stats.get("likeCount", 0))

        comments = int(stats.get("commentCount", 0))

        subscribers = 0

        try:

            channel_id = snippet["channelId"]

            channel_response = youtube.channels().list(
                part="statistics",
                id=channel_id
            ).execute()

            subscribers = int(
                channel_response["items"][0]["statistics"].get(
                    "subscriberCount",
                    0
                )
            )

        except:

            subscribers = 0

        engagement = round(
            ((likes + comments) / views) * 100,
            2
        ) if views > 0 else 0

        ratio = round(
            views / subscribers,
            2
        ) if subscribers > 0 else 0

        if ratio >= 100:
            grade = "🚀 폭발"

        elif ratio >= 30:
            grade = "🔥 급상승"

        elif ratio >= 10:
            grade = "🟡 관심"

        else:
            grade = "⚪ 일반"

        score = round(
            engagement * ratio,
            2
        )

        title = snippet["title"]

        keywords = re.findall(
            r"[가-힣a-zA-Z0-9]+",
            title
        )

        stopwords = [
            "추천",
            "추천템",
            "쇼츠",
            "shorts",
            "다이소",
            "쿠팡"
        ]

        item_keywords = [
            word for word in keywords
            if len(word) >= 2 and word not in stopwords
        ]

        try:
            YouTubeTranscriptApi.get_transcript(video_id)
            transcript_available = True

        except:
            transcript_available = False

        tags = snippet.get("tags", [])    
            
        videos.append(
            {
                "썸네일": snippet["thumbnails"]["high"]["url"],
                "제목": title,
                "영상링크": f"https://www.youtube.com/watch?v={video_id}",
                "채널명": snippet["channelTitle"],
                "게시일": published_date.strftime("%Y-%m-%d"),
                "영상길이": parse_duration(
                    video_item["contentDetails"]["duration"]
                ),
                "쇼츠여부": "쇼츠",
                "조회수": views,
                "좋아요": likes,
                "댓글수": comments,
                "구독자수": subscribers,
                "참여율(%)": engagement,
                "조회수배율": ratio,
                "등급": grade,
                "떡상점수": score,
                "자막상태": (
                    "가능"
                    if transcript_available
                    else "불가"
                ),
                "아이템키워드": ", ".join(tags[:15]),
                "video_id": video_id,
                "채널ID": snippet["channelId"]
            }
        )

    df = pd.DataFrame(videos)

    st.session_state["df"] = df

# =========================
# 결과 출력
# =========================

if "df" in st.session_state:

    df = st.session_state["df"]
    if shorts_filter == "쇼츠만":

        df = df[
            df["쇼츠여부"] == "쇼츠"
        ]

    elif shorts_filter == "일반영상만":

        df = df[
            df["쇼츠여부"] == "일반영상"
        ]

    if "조회수배율" in df.columns and "참여율(%)" in df.columns:
        df = df[
            (df["조회수배율"] >= min_ratio)
            &
            (df["참여율(%)"] >= min_engagement)
        ]

    if show_favorites_only:

        df = df[
            df["채널명"].isin(
                st.session_state["favorite_channels"]
            )
        ]

    if crazy_view_filter:
        df = df[
            (df["조회수배율"] >= 30)
            &
            (df["조회수"] >= 100000)
        ]

    if sort_option == "떡상점수 높은순":
        df = df.sort_values(by="떡상점수", ascending=False)

    elif sort_option == "조회수 높은순":
        df = df.sort_values(by="조회수", ascending=False)

    elif sort_option == "참여율 높은순":
        df = df.sort_values(by="참여율(%)", ascending=False)

    elif sort_option == "조회수배율 높은순":
        df = df.sort_values(by="조회수배율", ascending=False)

    elif sort_option == "최신순":
        df = df.sort_values(by="게시일", ascending=False)        

    st.subheader("분석 결과")
    st.info(
    """
    📌 지표 보는 법

    - 조회수배율: 조회수가 구독자수보다 몇 배 많이 나왔는지 보여줍니다. 높을수록 작은 채널도 크게 터진 영상일 가능성이 있습니다.
    - ex. 구독자 1만 명 채널인데 조회수 100만일 경우 (100배) 
    - 100배 이상 = 🚀 폭발, 30배 이상 = 🔥 급상승, 10배 이상 = 🟡 관심, 10배 미만 = ⚪ 일반
    - 참여율(%): 조회수 대비 좋아요+댓글 반응률. 높을수록 사람들이 반응한 영상입니다.
    - 떡상점수: 조회수배율x참여율. 높을수록 조회수와 반응이 동시에 좋은 레퍼런스 영상으로 볼 수 있습니다.

    추천 기준:
    조회수배율이 높고, 참여율도 함께 높은 영상일수록 벤치마킹 가치가 높습니다.
    """
)

    display_df = df.drop(columns=["video_id"])

    display_df.insert(
        0,
        "번호",
        range(1, len(display_df) + 1)
    )

    display_df["⭐즐겨찾기"] = display_df["채널명"].apply(
        lambda x: x in st.session_state["favorite_channels"]
    )

    cols = [
        "번호",
        "게시일",
        "썸네일",
        "채널명",
        "제목",
        "영상링크",
        "⭐즐겨찾기",
        "등급",
        "조회수배율",
        "참여율(%)",
        "떡상점수",
        "구독자수",
        "조회수",
        "좋아요",
        "댓글수",
        "아이템키워드",
        "영상길이",
        "쇼츠여부",
        "채널ID"
    ]

    display_df = display_df[cols]

    edited_df = st.data_editor(
        display_df,
        column_config={
            "썸네일": st.column_config.ImageColumn(
                "썸네일",
                width="small"
            ),
            "제목": st.column_config.TextColumn(
                "제목",
                width="large"
            ),
            "영상링크": st.column_config.LinkColumn(
                "영상 링크",
                width="small"
            ),
            "채널명": st.column_config.TextColumn(
                "채널명",
                width="small"
            ),
            "⭐즐겨찾기": st.column_config.CheckboxColumn(
                "⭐즐겨찾기",
                width="small"
            ),
            "등급": st.column_config.TextColumn(
                "등급",
                width="small"
            ),
            "게시일": st.column_config.TextColumn(
                "게시일",
                width="small"
            ),
        },
        hide_index=True,
        use_container_width=True,
        height=700
    )
    checked_df = edited_df[
        edited_df["⭐즐겨찾기"] == True
    ].copy()

    unchecked_channels = edited_df.loc[
        edited_df["⭐즐겨찾기"] == False,
        "채널명"
    ].drop_duplicates().tolist()

    if "favorite_items" not in st.session_state:
        st.session_state["favorite_items"] = pd.DataFrame()

    if not st.session_state["favorite_items"].empty:
        st.session_state["favorite_items"] = st.session_state["favorite_items"][
            ~st.session_state["favorite_items"]["채널명"].isin(unchecked_channels)
        ]

    if not checked_df.empty:
        checked_df = checked_df.drop(
            columns=["⭐즐겨찾기"],
            errors="ignore"
        )

        st.session_state["favorite_items"] = pd.concat(
            [
                st.session_state["favorite_items"],
                checked_df
            ],
            ignore_index=True
        )

        st.session_state["favorite_items"] = (
            st.session_state["favorite_items"]
            .drop_duplicates(
                subset=["채널명"],
                keep="first"
            )
        )

    if not st.session_state["favorite_items"].empty:
        st.session_state["favorite_channels"] = (
            st.session_state["favorite_items"]["채널명"]
            .tolist()
        )
    else:
        st.session_state["favorite_channels"] = []

    save_favorites(
        st.session_state["favorite_channels"]
    )

    save_favorite_items(
        st.session_state["favorite_items"]
    )
    # =========================
    # 인기 키워드 분석
    # =========================


    # =========================
    # 자막 수집
    # =========================

    st.subheader("자막 수집")

    selected_title = st.selectbox(
        "영상 선택",
        df["제목"].tolist()
    )

    selected_row = df[
        df["제목"] == selected_title
    ].iloc[0]

    st.write("선택한 영상:", selected_row["제목"])

    if st.button("Whisper로 자막 생성"):

        with st.spinner("음성을 분석해서 자막을 생성하는 중이에요..."):

            transcript = get_whisper_transcript(
                selected_row["영상링크"]
            )

            st.session_state["transcript_result"] = transcript
            st.session_state["transcript_title"] = selected_row["제목"]

    if "transcript_result" in st.session_state:

        st.write("자막 생성 영상:", st.session_state["transcript_title"])

        st.text_area(
            "생성된 자막",
            st.session_state["transcript_result"],
            height=300
        )

    st.subheader("📊 채널 분석")

    channel_options = df[["채널명", "채널ID"]].drop_duplicates()

    selected_channel_name = st.selectbox(
        "채널 선택",
        channel_options["채널명"].tolist(),
        key="main_channel_select"
    )

    selected_channel_id = channel_options[
        channel_options["채널명"] == selected_channel_name
    ]["채널ID"].iloc[0]

    if st.button("선택한 채널 최근 영상 20개 분석"):

        recent_df = get_recent_channel_videos(
            selected_channel_id,
            max_results=20
        )

        st.session_state["recent_channel_df"] = recent_df
        st.session_state["recent_channel_name"] = selected_channel_name

    if "recent_channel_df" in st.session_state:

        recent_df = st.session_state["recent_channel_df"]

        st.write("분석 채널:", st.session_state["recent_channel_name"])
        st.write("최근 영상 개수:", len(recent_df))
        st.write("최근 영상 평균 조회수:", f"{int(recent_df['조회수'].mean()):,}")
        st.write("최근 영상 최고 조회수:", f"{int(recent_df['조회수'].max()):,}")

        st.dataframe(
            recent_df,
            column_config={
                "영상링크": st.column_config.LinkColumn("영상 링크"),
                "제목": st.column_config.TextColumn("제목", width="large"),
            },
            use_container_width=True,
            hide_index=True
        )

        recent_df = recent_df.sort_values(by="게시일")

        fig, ax = plt.subplots(figsize=(10, 4))

        ax.plot(
            recent_df["게시일"],
            recent_df["조회수"],
            marker="o"
        )

        ax.set_title(f"{st.session_state['recent_channel_name']} 최근 영상 조회수 추이")
        ax.set_xlabel("게시일")
        ax.set_ylabel("조회수")

        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda x, p: format(int(x), ","))
        )

        plt.xticks(rotation=45)

        st.pyplot(fig)

    # =========================
    # 엑셀 다운로드
    # =========================

    excel_data = to_excel(display_df)

    st.download_button(
        label="엑셀 다운로드",
        data=excel_data,
        file_name=f"{keyword}_분석결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )