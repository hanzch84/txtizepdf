# app.py
# -*- coding: utf-8 -*-

import streamlit as st
import tempfile
import shutil
import os
from utils.pdf_extractor import (
    parse_skip_pages,
    extract_sentences_with_page
)

st.set_page_config(
    page_title="AI 학습용 PDF → 문장 추출기",
    layout="wide"
)

st.title("📚 AI 학습용 PDF → 문장 추출기")
st.write("""
PDF를 업로드하면,  
- “페이지 구분”을 고려해 문장이 페이지 사이에서 끊어지지 않도록 자동으로 이어 붙이고  
- 각 문장의 **시작 페이지 번호**를 함께 기록하여  
- AI가 나중에 “xx문서 x페이지”라고 참조할 수 있는 최적화된 출력물을 생성합니다.  
여러 필터(건너뛸 페이지, 텍스트 길이, 표/도표 캡션, 이미지 포함 여부, 텍스트 면적 비율, 헤더/푸터 제거 등)를 적용할 수 있습니다.
""")

# 1. 사이드바: 옵션 입력 영역
st.sidebar.header("1️⃣ PDF 업로드 및 필터 설정")

uploaded_file = st.sidebar.file_uploader(
    label="👉 PDF 파일 업로드 (.pdf)",
    type=["pdf"]
)

output_format = st.sidebar.selectbox(
    label="ㆍ결과 저장 포맷",
    options=["individual", "csv", "json"],
    index=0,
    help="individual: 문장별 개별 .txt 파일만, csv: 전체 문장을 한꺼번에 all_sentences.csv, json: 전체를 all_sentences.json"
)

skip_pages_str = st.sidebar.text_input(
    label="ㆍ건너뛸 페이지 넘버 (예: 1,2,5-7)",
    value="1",
    help="""
1-based 인덱스.  
콤마(,)로 이어서 여러 개 지정.  
하이픈(-)으로 범위 지정.  
예: 1,2,5-7 → {1,2,5,6,7}페이지를 Skip.
"""
)

min_text_len = st.sidebar.number_input(
    label="ㆍ페이지 최소 텍스트 길이",
    min_value=0,
    value=50,
    help="이 값 미만으로 텍스트가 추출되는 페이지는 건너뜁니다."
)

table_threshold = st.sidebar.number_input(
    label="ㆍ‘표/도표 캡션’ 임계 횟수",
    min_value=0,
    value=3,
    help="페이지 내 한글 ‘표 숫자’ + 영문 ‘Table/Figure 숫자’ 패턴 등장 횟수가 이 값 이상이면 Skip."
)

skip_if_image = st.sidebar.checkbox(
    label="ㆍ이미지 포함 페이지 무조건 Skip",
    value=False
)

min_text_ratio = st.sidebar.slider(
    label="ㆍ최소 텍스트 면적 비율",
    min_value=0.0,
    max_value=1.0,
    value=0.05,
    step=0.01,
    help="페이지 전체 면적 대비 텍스트 블록 면적 비율이 이 값보다 작으면 Skip."
)

remove_header_footer = st.sidebar.checkbox(
    label="ㆍ헤더/푸터 제거 후 텍스트 추출",
    value=False
)

header_height_ratio = st.sidebar.number_input(
    label="ㆍ헤더 높이 비율",
    min_value=0.0,
    max_value=0.5,
    value=0.05,
    step=0.01,
    help="페이지 높이 대비 상단 헤더 영역 비율 (예: 0.05 → 상단 5%)."
)

footer_height_ratio = st.sidebar.number_input(
    label="ㆍ푸터 높이 비율",
    min_value=0.0,
    max_value=0.5,
    value=0.05,
    step=0.01,
    help="페이지 높이 대비 하단 푸터 영역 비율 (예: 0.05 → 하단 5%)."
)

run_button = st.sidebar.button("▶️ 문장 추출 시작")

# 2. 업로드 파일 및 버튼 클릭 안내
if uploaded_file is None:
    st.info("왼쪽 사이드바에서 PDF를 업로드한 뒤, 옵션을 설정하고 ‘문장 추출 시작’ 버튼을 눌러주세요.")
    st.stop()

if run_button:
    # 3. 업로드된 PDF를 로컬 임시 파일로 저장
    with st.spinner("PDF 업로드 중... 잠시만 기다려주세요."):
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(uploaded_file.read())

    # 4. 옵션 파싱
    skip_pages_set = parse_skip_pages(skip_pages_str)

    # 5. 결과 저장용 임시 폴더 생성
    temp_output_dir = tempfile.mkdtemp(prefix="pdf_ai_sentences_")

    # 6. 본격적으로 문장 단위 추출 수행
    with st.spinner("문장 단위 추출 중... 페이지가 많은 경우 시간이 다소 걸릴 수 있습니다."):
        result = extract_sentences_with_page(
            pdf_path=tmp_path,
            output_dir=temp_output_dir,
            skip_pages=skip_pages_set,
            min_text_len=min_text_len,
            table_threshold=table_threshold,
            skip_if_image=skip_if_image,
            min_text_ratio=min_text_ratio,
            remove_header_footer=remove_header_footer,
            header_height_ratio=header_height_ratio,
            footer_height_ratio=footer_height_ratio,
            output_format=output_format
        )

    # 7. 결과 안내 및 다운로드 버튼 표시
    st.success("✅ 문장 단위 추출이 완료되었습니다!")

    # 7-1) 개별 문장별 .txt 파일 다운로드
    st.subheader("📄 추출된 문장별 .txt 파일 목록")
    sent_txt_list = result.get("sent_txt_files", [])
    if sent_txt_list:
        for txt_path in sent_txt_list:
            fname = os.path.basename(txt_path)
            with open(txt_path, "rb") as f:
                st.download_button(
                    label=f"✏️ {fname} 다운로드",
                    data=f.read(),
                    file_name=fname,
                    mime="text/plain"
                )
    else:
        st.info("개별 문장별 .txt 파일이 생성되지 않았습니다. (필터 기준이 매우 엄격했을 수 있습니다.)")

    # 7-2) CSV/JSON 다운로드
    if output_format == "csv":
        csv_path = result.get("csv_path")
        if csv_path:
            st.subheader("📥 전체 문장 CSV 다운로드")
            with open(csv_path, "rb") as f:
                st.download_button(
                    label="all_sentences.csv 다운로드",
                    data=f.read(),
                    file_name="all_sentences.csv",
                    mime="text/csv"
                )
        else:
            st.info("CSV 파일이 생성되지 않았습니다.")
    elif output_format == "json":
        json_path = result.get("json_path")
        if json_path:
            st.subheader("📥 전체 문장 JSON 다운로드")
            with open(json_path, "rb") as f:
                st.download_button(
                    label="all_sentences.json 다운로드",
                    data=f.read(),
                    file_name="all_sentences.json",
                    mime="application/json"
                )
        else:
            st.info("JSON 파일이 생성되지 않았습니다.")

    # 8. 임시 파일/폴더 정리 (필요 시 주석 처리 가능)
    try:
        os.remove(tmp_path)
        shutil.rmtree(temp_output_dir)
    except:
        pass

    st.info("📝 다른 PDF로 다시 시도하려면 페이지 새로고침(F5) 후 재실행하세요.")
