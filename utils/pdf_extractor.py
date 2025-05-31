# utils/pdf_extractor.py
# -*- coding: utf-8 -*-

import fitz    # PyMuPDF
import os
import re
import pandas as pd

def parse_skip_pages(skip_str: str) -> set[int]:
    """
    "1,2,5-7,10" 같은 문자열을 입력받아 {1,2,5,6,7,10} 형태의 정수 집합으로 반환합니다.
    - skip_str: 사용자가 입력한 콤마/하이픈 기반 페이지 범위 문자열
    """
    skips = set()
    parts = skip_str.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                lo, hi = part.split('-', maxsplit=1)
                lo_i = int(lo.strip())
                hi_i = int(hi.strip())
                if lo_i <= hi_i:
                    skips.update(range(lo_i, hi_i + 1))
            except:
                continue
        else:
            try:
                num = int(part)
                skips.add(num)
            except:
                continue
    return skips


def remove_header_footer_blocks(page_dict: dict,
                                header_height_ratio: float,
                                footer_height_ratio: float) -> list[dict]:
    """
    page.get_text("dict") 결과인 page_dict['blocks']에서
    헤더/푸터 영역(상단/하단)을 제거하고, 나머지 본문 블록(텍스트·이미지·도형 등)을 반환합니다.

    - header_height_ratio: 페이지 높이 대비 상단 헤더 영역 비율 (예: 0.05 -> 상단 5%)
    - footer_height_ratio: 페이지 높이 대비 하단 푸터 영역 비율 (예: 0.05 -> 하단 5%)

    반환: 헤더/푸터 블록이 제외된 블록들의 리스트 (각 블록은 딕셔너리 형태)
    """
    blocks = page_dict.get('blocks', [])
    H = page_dict.get('height', 0)
    header_limit = H * header_height_ratio
    footer_limit = H * (1.0 - footer_height_ratio)

    filtered = []
    for blk in blocks:
        if 'bbox' not in blk:
            continue
        _, y0, _, y1 = blk['bbox']
        # y1 < header_limit 이면 상단 헤더 블록
        if y1 < header_limit:
            continue
        # y0 > footer_limit 이면 하단 푸터 블록
        if y0 > footer_limit:
            continue
        filtered.append(blk)
    return filtered


def compute_text_block_area_ratio(page: fitz.Page,
                                  page_dict: dict,
                                  header_height_ratio: float,
                                  footer_height_ratio: float) -> float:
    """
    페이지 전체 면적 대비, '헤더/푸터 제거 후 남은 텍스트 블록 면적' 비율을 계산합니다.
    - 페이지 면적: page.rect.width * page.rect.height
    - 텍스트 블록 면적: 각 blk['type']==0(텍스트)인 블록별 bbox 면적 합
    """
    rect = page.rect
    page_area = rect.width * rect.height
    if page_area <= 0:
        return 0.0

    blocks = remove_header_footer_blocks(page_dict,
                                         header_height_ratio,
                                         footer_height_ratio)
    text_area = 0.0
    for blk in blocks:
        if blk.get('type', -1) == 0:  # type 0: 텍스트 블록
            x0, y0, x1, y1 = blk['bbox']
            w = max(0.0, x1 - x0)
            h = max(0.0, y1 - y0)
            text_area += (w * h)
    return text_area / page_area


def normalize_line_breaks(raw_page_text: str) -> str:
    """
    PDF에서 얻은 원본 텍스트(줄바꿈 포함)를 “문장 단위로 자연스럽게 연결”해 주는 함수.
    - 줄 끝이 하이픈 '-' 으로 끝나면 하이픈을 제거하고 바로 뒤의 줄과 붙임
    - 줄 끝에 마침표/물음표/느낌표 등 문장종결 기호가 없으면 다음 줄과 띄어쓰기 하나로 연결
    - 줄 끝에 문장종결 기호가 있으면 줄바꿈을 그대로 유지하여 문장 단위 분리에 도움
    """
    lines = raw_page_text.splitlines()
    normalized = ""
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        # 1) 하이픈으로 줄이 이어진 경우
        if line.endswith("-"):
            # 하이픈 제거 후 바로 뒤줄과 붙임
            normalized += line[:-1]
            continue
        # 2) 줄 끝이 문장종결 기호로 끝나지 않으면, 띄어쓰기 하나로 이어 줌
        if not re.search(r"[.!?…。？！]$", line):
            normalized += line + " "
        else:
            # 문장종결 기호 있으면 줄바꿈을 남겨서 문장 구분 시 도움
            normalized += line + "\n"
    return normalized


def split_into_sentences(text: str) -> list[str]:
    """
    한글·영문 혼용 텍스트를 문장 단위로 분리합니다.
    - 아래 정규식 기준으로 '.', '!', '?', '…', '。', '？', '！' 등의 기호에 따라 문장 구분
    - 마침표 뒤에 연속되는 큰따옴표(")나 작은따옴표(')가 붙을 경우도 처리
    - 최종적으로 문장 뒤 문장단위 구분 기호를 제거하고 반환
    """
    # 문장 끝 기호를 발견한 지점에서 분리 (기호 뒤의 공백 또는 개행 포함)
    sentence_endings = re.compile(r'(?<=[\.\!\?\…\。\？！])\s+')
    raw_sents = sentence_endings.split(text)
    sents = []
    for s in raw_sents:
        s = s.strip()
        if s:
            sents.append(s)
    return sents


def should_skip_page(page: fitz.Page,
                     page_num_1based: int,
                     skip_pages: set[int],
                     min_text_len: int,
                     table_threshold: int,
                     skip_if_image: bool,
                     min_text_ratio: float,
                     header_height_ratio: float,
                     footer_height_ratio: float) -> bool:
    """
    이 페이지를 ‘건너뛸지’ 여부를 판단하는 함수:
    1) page_num_1based가 skip_pages에 있으면 True
    2) 페이지 전체 텍스트 길이(raw_text.strip())가 min_text_len 미만이면 True
    3) ‘표 \d+’ 또는 ‘Table \d+’/‘Figure \d+’ 패턴 등장 횟수 합 >= table_threshold이면 True
    4) skip_if_image=True 이고, page.get_images() 결과가 비어 있지 않으면 True
    5) compute_text_block_area_ratio 결과가 min_text_ratio 미만이면 True
    """
    # 1) 사용자 지정 페이지 번호 무조건 Skip
    if page_num_1based in skip_pages:
        return True

    # 2) 텍스트 길이 검사
    raw_text = page.get_text("text") or ""
    if len(raw_text.strip()) < min_text_len:
        return True

    # 3) ‘표/도표 캡션’ 패턴 검사
    cnt_ko = len(re.findall(r"표\s*\d+", raw_text))
    cnt_en = len(re.findall(r"(Table|Figure)\s*\d+", raw_text, flags=re.IGNORECASE))
    if (cnt_ko + cnt_en) >= table_threshold:
        return True

    # 4) 이미지 포함 여부 검사
    if skip_if_image:
        img_list = page.get_images(full=True)
        if img_list:
            return True

    # 5) 텍스트 블록 면적 비율 검사
    page_dict = page.get_text("dict")
    ratio = compute_text_block_area_ratio(page,
                                          page_dict,
                                          header_height_ratio,
                                          footer_height_ratio)
    if ratio < min_text_ratio:
        return True

    return False


def extract_sentences_with_page(
        pdf_path: str,
        output_dir: str,
        skip_pages: set[int],
        min_text_len: int,
        table_threshold: int,
        skip_if_image: bool,
        min_text_ratio: float,
        remove_header_footer: bool,
        header_height_ratio: float,
        footer_height_ratio: float,
        output_format: str = "individual"
    ) -> dict:
    """
    PDF를 열어 페이지별로 문장 단위로 분리하고,
    각 문장의 ‘시작 페이지 번호’ 정보를 함께 기록합니다.

    - pdf_path: 입력 PDF 파일 경로
    - output_dir: 결과물을 저장할 디렉토리 (존재하지 않으면 생성)
    - skip_pages: 무조건 Skip할 1-based 페이지 번호 집합
    - min_text_len: 페이지 텍스트 길이 최소값 (이 값 미만 시 해당 페이지 전체 Skip)
    - table_threshold: ‘표/도표 캡션’ 패턴 최소 등장 횟수 (이 값 이상 시 Skip)
    - skip_if_image: True 시, 이미지 포함 페이지 무조건 Skip
    - min_text_ratio: 텍스트 면적 비율 최소값 (이 값 미만 시 Skip)
    - remove_header_footer: True 시, 헤더/푸터 영역 제거 후 텍스트 추출
    - header_height_ratio, footer_height_ratio: 헤더/푸터 제거 비율
    - output_format: "individual" (개별 문장별 .txt) / "csv" / "json"

    반환 (dict):
        {
            "sent_txt_files": [ ... ],   # 개별 문장별 .txt 파일 리스트
            "csv_path": "..." or None,
            "json_path": "..." or None
        }

    **동작 순서**
    1. output_dir 존재 여부 확인 후 생성
    2. PDF 열기 (fitz.open)
    3. page_index를 0부터 순회하며, page_num_1based=page_index+1
       └ should_skip_page 함수로 Skip 여부 결정
       └ Skip이 아니면 아래 작업 수행:
         3-1. remove_header_footer=True인 경우 → page.get_text("dict") → 헤더/푸터 제거 → 텍스트 블록만 모아 lines 결합
              (remove_header_footer=False인 경우 → page.get_text("text") 호출 → 바로 lines 결합)
         3-2. normalize_line_breaks(생성된 raw/blocks 기준 텍스트) 호출 → “줄바꿈 문제 해결”된 페이지 본문 반환
         3-3. split_into_sentences(위 본문) 호출 → 문장 리스트 반환
         3-4. “마지막 문장”이 문장종결 기호(., !, ?, … 등)로 끝나지 않으면 → 다음 페이지로 넘어갈 때까지
              page_buffer에 저장(이어서 처리). (다음 페이지 첫 번째 본문과 합쳐진 뒤 문장 분리)
         3-5. 각 문장이 “페이지가 바뀐 시점에서 문장이 시작된 페이지 번호”를 기록하도록 튜닝
         3-6. 최종적으로, 페이지 순회를 마친 뒤 “문장 단위”로 파일 저장 또는 레코드 누적
    4. PDF 닫기
    5. output_format에 따라 CSV/JSON 파일 생성
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    doc = fitz.open(pdf_path)
    total_pages = doc.page_count

    sent_txt_files = []
    records = []

    # 페이지를 넘기면서, “이어서 붙어야 할 문장 조각”을 담아 두는 버퍼
    carryover_fragment = ""
    carryover_page = None  # fragment가 시작된 페이지 번호

    for page_index in range(total_pages):
        page_num = page_index + 1
        page = doc.load_page(page_index)

        # 1) Skip 여부 판단
        if should_skip_page(page,
                            page_num,
                            skip_pages,
                            min_text_len,
                            table_threshold,
                            skip_if_image,
                            min_text_ratio,
                            header_height_ratio,
                            footer_height_ratio):
            continue

        # 2) 페이지 본문 텍스트 추출
        if remove_header_footer:
            page_dict = page.get_text("dict")
            valid_blocks = remove_header_footer_blocks(
                page_dict, header_height_ratio, footer_height_ratio)
            lines = []
            for blk in valid_blocks:
                if blk.get('type', -1) != 0:
                    continue
                for line in blk.get('lines', []):
                    for span in line.get('spans', []):
                        t = span.get('text', '').strip()
                        if t:
                            lines.append(t)
            raw_page_text = "\n".join(lines)
        else:
            raw_page_text = page.get_text("text") or ""

        # 3) 줄바꿈 보정
        normalized = normalize_line_breaks(raw_page_text)

        # 4) 이전 페이지에서 끊긴 조각과 결합
        if carryover_fragment:
            normalized = carryover_fragment + " " + normalized
            # 이 문장 조각이 시작된 페이지는 carryover_page
            start_page_for_carry = carryover_page
            carryover_fragment = ""
            carryover_page = None
        else:
            start_page_for_carry = page_num

        # 5) 문장 단위 분리
        sents = split_into_sentences(normalized)

        # 6) 마지막 문장이 문장종결 기호 없이 끝났다면 다음 페이지로 이음
        if sents:
            last_sent = sents[-1]
            if not re.search(r"[\.\!\?\…\。\？！]$", last_sent):
                # 종결 기호 없이 끝남 → 이 문장 조각은 carryover
                carryover_fragment = last_sent
                carryover_page = start_page_for_carry
                sents = sents[:-1]  # 분리된 리스트에서 마지막 조각 제거

        # 7) 분리된 문장들을 “페이지 정보와 함께” 저장/기록
        for sent in sents:
            # 문장이 carryover 없이 완전히 종료된 경우, 이 문장이 시작된 페이지는 바로 page_num
            # 만약 carryover로부터 넘어온 조각이었다면 이 문장의 시작 페이지는 carryover_page
            if carryover_page is not None and sent.startswith(carryover_fragment):
                # (실제로 carryover된 조각 포함 문장은 이전 페이지에 속하지만, 
                #  발췌된 조각과 합쳐진 뒤 첫 문장일 경우를 대비)
                st_pg = carryover_page
            else:
                st_pg = page_num

            # 7-1) 개별 .txt 파일로 저장 (파일명 예: sent_페이지번호_순번.txt)
            #     예: sent_005_0001.txt (5페이지에서 시작된 첫 번째 문장)
            #     내부적으로, 같은 페이지 번호에서 여러 문장이라면 인덱스 붙임
            base_name = f"page_{st_pg:03d}"
            # 페이지별로 순번 카운터 관리: 파일명 중복 방지
            # (단순 구현: 파일명 끝에 UUID나 인덱스를 붙여도 무방)
            sent_index = len([f for f in sent_txt_files if f.startswith(os.path.join(output_dir, base_name))]) + 1
            fname = os.path.join(output_dir, f"{base_name}_{sent_index:04d}.txt")
            with open(fname, "w", encoding="utf-8") as fout:
                fout.write(sent)
            sent_txt_files.append(fname)

            # 7-2) CSV/JSON 용 레코드 누적
            if output_format in ("csv", "json"):
                records.append({
                    "page_num": st_pg,
                    "sentence": sent
                })

    doc.close()

    csv_path = None
    json_path = None
    if output_format == "csv" and records:
        df = pd.DataFrame(records)
        csv_path = os.path.join(output_dir, "all_sentences.csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    elif output_format == "json" and records:
        df = pd.DataFrame(records)
        json_path = os.path.join(output_dir, "all_sentences.json")
        df.to_json(json_path, orient="records", force_ascii=False, indent=2)

    return {
        "sent_txt_files": sent_txt_files,
        "csv_path": csv_path,
        "json_path": json_path
    }
