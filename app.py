import streamlit as st
import requests
import json
import html
import re
import google.generativeai as genai

st.set_page_config(page_title="산도리 메신저", page_icon="🍓", layout="centered") 

DB_URL = "https://script.google.com/macros/s/AKfycbz_43zmUq1z95JBauFRtiqtvMv2jxDV7neGmQca8w8Z-NmIKivvc88QVWIsTNccCZ_IIg/exec"
INSTAGRAM_PREFIX = "instagram:"

# 기본 요일별 영업시간 템플릿
DEFAULT_HOURS = [
    {"요일": "월요일", "영업여부": True, "오픈시간": "11:00", "마감시간": "20:00", "비고": ""},
    {"요일": "화요일", "영업여부": True, "오픈시간": "11:00", "마감시간": "20:00", "비고": ""},
    {"요일": "수요일", "영업여부": True, "오픈시간": "11:00", "마감시간": "20:00", "비고": ""},
    {"요일": "목요일", "영업여부": True, "오픈시간": "11:00", "마감시간": "20:00", "비고": ""},
    {"요일": "금요일", "영업여부": True, "오픈시간": "11:00", "마감시간": "20:00", "비고": ""},
    {"요일": "토요일", "영업여부": True, "오픈시간": "11:00", "마감시간": "20:00", "비고": ""},
    {"요일": "일요일", "영업여부": True, "오픈시간": "11:00", "마감시간": "20:00", "비고": ""},
]

@st.cache_data(ttl=3)
def load_sms_logs():
    try:
        response = requests.get(DB_URL + "?action=read")
        if response.status_code == 200:
            raw_data = response.json()
            if len(raw_data) <= 1: return []
            logs = []
            # 같은 내용도 별개의 문자일 수 있으므로 저장된 행을 그대로 표시합니다.
            # 중복 수신 여부는 본문이나 시각 대신 고유 메시지 ID로 판단해야 합니다.
            for row in raw_data[1:]:
                if len(row) >= 4:
                    conversation_id = canonical_conversation_id(row[1])
                    logs.append({"time": row[0], "phone": conversation_id, "message": row[2], "sender": row[3]})
            return logs
    except:
        return []
    return []

@st.cache_data(ttl=10)
def load_settings():
    try:
        res = requests.get(DB_URL + "?action=read_settings")
        if res.status_code == 200: return res.json()
    except: pass
    return {}

def as_records(data):
    """st.data_editor의 반환 형식(list/DataFrame)을 dict 목록으로 통일합니다."""
    if hasattr(data, "to_dict"):
        return data.to_dict("records")
    return list(data)

def normalize_korean_mobile(value):
    digits = re.sub(r"\D", "", str(value))
    if digits.startswith("82"):
        digits = "0" + digits[2:]
    elif re.fullmatch(r"10\d{8}", digits):
        digits = "0" + digits
    return digits

def canonical_conversation_id(value):
    """하이픈 유무와 시트의 숫자 변환에 관계없이 같은 번호를 같은 ID로 만듭니다."""
    raw_value = str(value).strip()
    if raw_value.lower().startswith(INSTAGRAM_PREFIX):
        account = raw_value[len(INSTAGRAM_PREFIX):].strip()
        return INSTAGRAM_PREFIX + account

    phone = normalize_korean_mobile(raw_value)
    if re.fullmatch(r"010\d{8}", phone):
        return phone
    return raw_value

def format_mobile_number(value):
    phone = normalize_korean_mobile(value)
    if re.fullmatch(r"010\d{8}", phone):
        return f"{phone[:3]}-{phone[3:7]}-{phone[7:]}"
    return str(value)

def message_fingerprint(sender, message):
    normalized_sender = "산도리" if str(sender).strip() == "산도리" else "고객"
    normalized_message = re.sub(r"\s+", " ", str(message)).strip()
    return normalized_sender, normalized_message

def build_conversation_id(channel, title):
    """문자 번호와 인스타 계정이 같은 메시지 저장소에서 충돌하지 않게 구분합니다."""
    if channel == "문자":
        phone = canonical_conversation_id(title)
        if not re.fullmatch(r"010\d{8}", phone):
            raise ValueError("문자 대화는 010으로 시작하는 휴대전화 번호 11자리를 입력해주세요.")
        return phone

    account = str(title).strip()
    if not account:
        raise ValueError("인스타그램 대화는 고객 계정명이나 구분 이름을 입력해주세요.")
    if account.lower().startswith(INSTAGRAM_PREFIX):
        account = account[len(INSTAGRAM_PREFIX):].strip()
    return INSTAGRAM_PREFIX + account

def is_instagram_conversation(conversation_id):
    return str(conversation_id).lower().startswith(INSTAGRAM_PREFIX)

def conversation_label(conversation_id):
    if is_instagram_conversation(conversation_id):
        account = str(conversation_id)[len(INSTAGRAM_PREFIX):]
        return f"📷 인스타 · {account}"
    return f"📞 {format_mobile_number(conversation_id)}"

def save_restored_messages(channel, title, messages, existing_logs):
    """복원 메시지를 기존 구글 시트 대화 저장소에 순서대로 추가합니다."""
    conversation_id = build_conversation_id(channel, title)
    existing_fingerprints = {
        message_fingerprint(item.get("sender"), item.get("message"))
        for item in existing_logs
        if canonical_conversation_id(item.get("phone", "")) == conversation_id
    }
    messages_to_save = []
    skipped_count = 0
    for item in messages:
        fingerprint = message_fingerprint(item.get("보낸 사람"), item.get("내용"))
        if not fingerprint[1] or fingerprint in existing_fingerprints:
            skipped_count += 1
            continue
        existing_fingerprints.add(fingerprint)
        messages_to_save.append(item)

    saved_count = 0
    total_count = len(messages_to_save)

    for item in messages_to_save:
        try:
            response = requests.get(
                DB_URL,
                params={
                    "phone": conversation_id,
                    "msg": str(item.get("내용", "")).strip(),
                    "sender": "산도리" if item.get("보낸 사람") == "산도리" else "고객",
                    "original_time": str(item.get("시간", "")).strip(),
                    "source": "screenshot_restore",
                },
                timeout=15,
            )
            response.raise_for_status()
            saved_count += 1
        except Exception as exc:
            raise RuntimeError(f"{saved_count}/{total_count}개 저장 후 중단되었습니다: {exc}") from exc

    return conversation_id, saved_count, skipped_count

def parse_conversation_json(raw_text):
    """Gemini가 반환한 JSON에서 대화 내용을 안전하게 꺼냅니다."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("AI 응답에서 대화 JSON을 찾지 못했습니다.")
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict) or not isinstance(parsed.get("messages"), list):
        raise ValueError("AI 응답의 대화 형식이 올바르지 않습니다.")

    messages = []
    previous_fingerprint = None
    seen_timed_messages = set()
    for item in parsed.get("messages", []):
        if not isinstance(item, dict):
            continue
        message = str(item.get("message", "")).strip()
        if not message:
            continue

        raw_sender = str(item.get("sender", "고객")).strip().lower()
        sender = "산도리" if raw_sender in {"산도리", "나", "매장", "store", "business", "me"} else "고객"
        time_text = str(item.get("time", "")).strip()
        fingerprint = (sender, re.sub(r"\s+", " ", message), time_text)

        # 이어지는 스크린샷의 겹치는 구간에서 완전히 같은 메시지가 연속으로
        # 인식되는 경우 한 번만 남깁니다.
        if fingerprint == previous_fingerprint or (time_text and fingerprint in seen_timed_messages):
            continue
        messages.append({"보낸 사람": sender, "내용": message, "시간": time_text})
        previous_fingerprint = fingerprint
        if time_text:
            seen_timed_messages.add(fingerprint)

    if not messages:
        raise ValueError("스크린샷에서 대화 메시지를 찾지 못했습니다.")

    raw_warnings = parsed.get("warnings", [])
    if not isinstance(raw_warnings, list):
        raw_warnings = [raw_warnings]

    return {
        "platform": str(parsed.get("platform", "")).strip(),
        "conversation_title": str(parsed.get("conversation_title", "")).strip(),
        "messages": messages,
        "warnings": [str(w).strip() for w in raw_warnings if str(w).strip()],
    }

def restore_conversation_from_images(uploaded_files, platform_hint):
    """업로드된 스크린샷을 시간순 대화 JSON으로 변환합니다."""
    if not st.session_state.gemini_api_key:
        raise ValueError("시스템 연결 탭에서 Gemini API 키를 먼저 확인해주세요.")

    prompt = f"""
당신은 고객 상담 대화 스크린샷을 정확하게 전사하는 도구입니다.
첨부 이미지는 모두 같은 고객과의 대화이며, 사용자가 선택한 순서대로 오래된 화면부터 최신 화면까지 배열되어 있습니다.
플랫폼 힌트는 '{platform_hint}'입니다.

다음 규칙을 반드시 지키세요.
1. 화면 오른쪽 말풍선/내가 보낸 메시지는 '산도리', 왼쪽 말풍선/상대가 보낸 메시지는 '고객'으로 분류합니다.
2. 문자와 인스타그램 DM의 상태표시줄, 메뉴명, 입력창 안내, 추천 답장, 날짜 구분선은 메시지에서 제외합니다.
3. 메시지 문구, 이모지, 줄바꿈은 보이는 그대로 보존하고 오탈자를 임의로 고치지 않습니다.
4. 시간이 화면에 보일 때만 기록하며, 보이지 않는 시간은 빈 문자열로 둡니다. 날짜나 시간을 추측하지 않습니다.
5. 여러 스크린샷에 같은 말풍선이 겹쳐 보이면 한 번만 기록합니다.
6. 사진/영상/음성만 있는 말풍선은 각각 '[사진]', '[동영상]', '[음성 메시지]'로 기록합니다.
7. 읽기 어렵거나 잘린 내용은 추측하지 말고 warnings에 한국어로 적습니다.
8. 첨부 이미지 전체를 종합해 실제 대화 순서대로 정렬합니다.

아래 JSON 객체만 반환하세요.
{{
  "platform": "문자 또는 인스타그램 DM",
  "conversation_title": "화면에 보이는 전화번호나 계정명, 없으면 빈 문자열",
  "messages": [
    {{"sender": "고객 또는 산도리", "message": "메시지 원문", "time": "화면에 보이는 시간 또는 빈 문자열"}}
  ],
  "warnings": ["확인이 필요한 내용"]
}}
"""

    content_parts = [prompt]
    for image_index, uploaded_file in enumerate(uploaded_files, start=1):
        mime_type = uploaded_file.type or "image/png"
        content_parts.extend([
            f"[스크린샷 {image_index}]",
            {"mime_type": mime_type, "data": uploaded_file.getvalue()},
        ])

    genai.configure(api_key=st.session_state.gemini_api_key)
    model = genai.GenerativeModel(st.session_state.selected_model)
    response = model.generate_content(
        content_parts,
        generation_config={"temperature": 0, "response_mime_type": "application/json"},
    )
    return parse_conversation_json(response.text)

def get_store_context():
    menu_text = "\n".join([
        f"- {item['메뉴 이름']}: {item['가격']}"
        for item in as_records(st.session_state.menu_list)
        if item.get("메뉴 이름")
    ])

    hours_list = []
    for h in as_records(st.session_state.business_hours):
        if h.get("영업여부", True):
            extra = f" ({h['비고']})" if h.get("비고") else ""
            hours_list.append(f"- {h['요일']}: {h['오픈시간']} ~ {h['마감시간']}{extra}")
        else:
            hours_list.append(f"- {h['요일']}: 정기휴무")
    return menu_text, "\n".join(hours_list)

def generate_reply_draft(messages):
    menu_text, hours_text = get_store_context()
    chat_history = "\n".join([
        f"{item['보낸 사람']}: {item['내용']}"
        for item in messages
        if str(item.get("내용", "")).strip()
    ])
    final_prompt = f"""{st.session_state.sando_persona}

[메뉴/가격]
{menu_text}

[매장 영업시간]
{hours_text}

[기타 매장운영 정보]
{st.session_state.store_info}

[과거 대화 맥락]
{chat_history}

위 정보를 바탕으로 고객의 마지막 질문에 친절하고 정확하게 답해줘."""
    genai.configure(api_key=st.session_state.gemini_api_key)
    model = genai.GenerativeModel(st.session_state.selected_model)
    return model.generate_content(final_prompt).text

def render_chat(messages):
    chat_html = '<div class="chat-bg">\n'
    for msg in messages:
        sender = msg.get("보낸 사람", msg.get("sender", "고객"))
        message = msg.get("내용", msg.get("message", ""))
        time_text = msg.get("시간", msg.get("time", ""))
        role_class = "sando" if sender == "산도리" else "user"
        safe_message = html.escape(str(message)).replace("\n", "<br>")
        safe_time = html.escape(str(time_text))
        chat_html += f'<div class="msg-row {role_class}"><div class="bubble">{safe_message}</div>'
        if safe_time:
            chat_html += f'<div class="time">{safe_time}</div>'
        chat_html += '</div>\n'
    chat_html += '</div>'
    st.markdown(chat_html, unsafe_allow_html=True)

sms_data = load_sms_logs()
settings_data = load_settings()

# 세션 상태 초기화
if 'sando_persona' not in st.session_state: st.session_state.sando_persona = settings_data.get("persona", "")
if 'store_info' not in st.session_state: st.session_state.store_info = settings_data.get("store_info", settings_data.get("daily_notes", ""))
if 'menu_list' not in st.session_state:
    try:
        saved_menu = json.loads(settings_data.get("menu", "[]"))
        st.session_state.menu_list = saved_menu if saved_menu else [{"메뉴 이름": "", "가격": ""}]
    except:
        st.session_state.menu_list = [{"메뉴 이름": "", "가격": ""}]

if 'business_hours' not in st.session_state:
    try:
        saved_hours = json.loads(settings_data.get("business_hours", "[]"))
        st.session_state.business_hours = saved_hours if saved_hours else DEFAULT_HOURS
    except:
        st.session_state.business_hours = DEFAULT_HOURS

if 'gemini_api_key' not in st.session_state:
    try: st.session_state.gemini_api_key = st.secrets["GEMINI_API_KEY"]
    except: st.session_state.gemini_api_key = "" 
    
if 'webhook_url' not in st.session_state:
    try: st.session_state.webhook_url = st.secrets["WEBHOOK_URL"]
    except: st.session_state.webhook_url = "" 
    
if 'selected_model' not in st.session_state: st.session_state.selected_model = "gemini-3.5-flash-lite"
if 'current_chat' not in st.session_state: st.session_state.current_chat = None
if 'restored_conversation' not in st.session_state: st.session_state.restored_conversation = None
if 'restore_revision' not in st.session_state: st.session_state.restore_revision = 0
if 'saved_restore_revision' not in st.session_state: st.session_state.saved_restore_revision = -1

st.title("🍓 산도리 메신저")

if "sms_send_notice" in st.session_state:
    st.success(st.session_state.pop("sms_send_notice"))

if "restore_save_notice" in st.session_state:
    st.success(st.session_state.pop("restore_save_notice"))

st.markdown("""
<style>
.chat-bg { background-color: #f2f2f5; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
.msg-row { display: flex; flex-direction: column; margin-bottom: 12px; }
.msg-row.user { align-items: flex-start; }
.msg-row.sando { align-items: flex-end; }
.bubble { max-width: 80%; padding: 12px 16px; border-radius: 20px; font-size: 15px; line-height: 1.4; font-family: sans-serif; }
.msg-row.user .bubble { background-color: #ffffff; color: #000000; border-top-left-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
.msg-row.sando .bubble { background-color: #007aff; color: #ffffff; border-top-right-radius: 4px; }
.time { font-size: 11px; color: #888888; margin-top: 4px; padding: 0 4px; }
</style>
""", unsafe_allow_html=True)

tab1, tab_restore, tab2, tab3 = st.tabs(["💬 메시지", "📷 스크린샷 복원", "🍓 매장 및 AI 설정", "⚙️ 시스템 연결"])

with tab3:
    st.info("💡 API 키와 웹훅 주소는 Streamlit Secrets(금고)에 안전하게 영구 보관 중입니다. 변경이 필요할 경우 대시보드에서 수정하세요.")
    st.subheader("🔑 시스템 필수 연결 확인")
    col_a, col_b = st.columns(2)
    with col_a: 
        st.session_state.webhook_url = st.text_input("🔗 웹훅 주소 (금고 연동됨)", value=st.session_state.webhook_url, type="password")
    with col_b:
        st.session_state.gemini_api_key = st.text_input("🧠 Gemini API 키 (금고 연동됨)", value=st.session_state.gemini_api_key, type="password")
        
        available_models = []
        if st.session_state.gemini_api_key:
            try:
                genai.configure(api_key=st.session_state.gemini_api_key)
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name.replace("models/", ""))
                if available_models:
                    idx = available_models.index(st.session_state.selected_model) if st.session_state.selected_model in available_models else 0
                    st.session_state.selected_model = st.selectbox("🤖 AI 모델", available_models, index=idx)
            except: pass

with tab2:
    with st.form(key="settings_form"):
        st.subheader("1. AI 행동 규칙") 
        new_persona = st.text_area("규칙 입력", value=st.session_state.sando_persona, height=140, label_visibility="collapsed")
        
        st.subheader("2. 메뉴 및 가격 관리")
        new_menu = st.data_editor(st.session_state.menu_list, num_rows="dynamic", use_container_width=True, key="menu_table_editor")
        
        st.subheader("3. 영업시간 (월~일)")
        st.caption("💡 영업하는 요일은 체크(☑️)하고 오픈/마감 시간을 입력하세요. 정기휴무일은 체크를 해제하시면 됩니다.")
        new_hours = st.data_editor(
            st.session_state.business_hours,
            column_config={
                "요일": st.column_config.TextColumn("요일", disabled=True),
                "영업여부": st.column_config.CheckboxColumn("영업일 여부", default=True),
                "오픈시간": st.column_config.TextColumn("오픈 시간", default="11:00"),
                "마감시간": st.column_config.TextColumn("마감 시간", default="20:00"),
                "비고": st.column_config.TextColumn("비고 (라스트오더 등)", default="")
            },
            num_rows="fixed",
            use_container_width=True,
            key="hours_table_editor"
        )

        st.subheader("4. 기타 매장운영 정보")
        new_store_info = st.text_area(
            "기타 매장운영 정보 입력",
            value=st.session_state.store_info,
            height=120,
            placeholder="예: \n- 주차: 매장 앞 1대 가능 / 인근 공영주차장 이용\n- 예약: 당일 픽업 예약 가능 (포장 위주)\n- 재료 소진 시 조기 마감될 수 있습니다.",
            label_visibility="collapsed"
        )

        st.markdown("---")
        submitted = st.form_submit_button("💾 매장 설정 영구 저장하기", type="primary", use_container_width=True)
        
        if submitted:
            st.session_state.sando_persona = new_persona
            st.session_state.menu_list = new_menu
            st.session_state.business_hours = new_hours
            st.session_state.store_info = new_store_info
            
            payload = {
                "persona": new_persona,
                "menu": new_menu,
                "business_hours": new_hours,
                "store_info": new_store_info,
                "daily_notes": new_store_info
            }
            with st.spinner("구글 시트에 영구 저장 중..."): 
                requests.post(DB_URL, json=payload)
            st.cache_data.clear() 
            st.success("✅ 매장 설정이 성공적으로 저장되었습니다!")

with tab_restore:
    st.subheader("문자·인스타 DM 대화 복원")
    st.caption("같은 대화의 스크린샷을 오래된 화면부터 순서대로 올려주세요. 이미지는 대화 인식을 위해 설정된 Gemini API로 전송됩니다.")

    platform_hint = st.selectbox(
        "스크린샷 종류",
        ["자동 판별", "문자", "인스타그램 DM"],
        key="restore_platform_hint",
    )
    uploaded_files = st.file_uploader(
        "대화 스크린샷 선택",
        type=["png", "jpg", "jpeg", "webp", "heic"],
        accept_multiple_files=True,
        key="restore_images",
        help="최대 10장, 전체 20MB까지 한 번에 분석합니다.",
    )

    if uploaded_files:
        st.caption("분석 순서: " + " → ".join(file.name for file in uploaded_files))

    if st.button("🔎 스크린샷에서 대화 복원", type="primary", use_container_width=True):
        if not uploaded_files:
            st.error("스크린샷을 한 장 이상 선택해주세요.")
        elif len(uploaded_files) > 10:
            st.error("한 번에 최대 10장까지 올릴 수 있습니다.")
        elif sum(file.size for file in uploaded_files) > 20 * 1024 * 1024:
            st.error("스크린샷 전체 용량을 20MB 이하로 줄여주세요.")
        else:
            with st.spinner("말풍선과 대화 순서를 읽고 있습니다..."):
                try:
                    restored = restore_conversation_from_images(uploaded_files, platform_hint)
                    st.session_state.restored_conversation = restored
                    st.session_state.restore_revision += 1
                    st.session_state.pop("restored_draft", None)
                    st.success(f"✅ 메시지 {len(restored['messages'])}개를 복원했습니다. 아래에서 꼭 한 번 확인해주세요.")
                except Exception as e:
                    st.error(f"❌ 대화를 복원하지 못했습니다: {e}")

    restored = st.session_state.restored_conversation
    if restored:
        revision = st.session_state.restore_revision
        st.markdown("---")

        default_channel = 1 if "인스타" in restored.get("platform", "") else 0
        channel = st.radio(
            "답변 채널",
            ["문자", "인스타그램 DM"],
            index=default_channel,
            horizontal=True,
            key=f"restore_channel_{revision}",
        )

        detected_title = restored.get("conversation_title", "")
        if channel == "문자":
            direct_entry = "새 번호 직접 입력"
            existing_sms_conversations = list(dict.fromkeys(
                item["phone"] for item in sms_data
                if not is_instagram_conversation(item["phone"])
                and re.fullmatch(r"010\d{8}", canonical_conversation_id(item["phone"]))
            ))
            target_options = [direct_entry, *existing_sms_conversations]
            detected_id = canonical_conversation_id(detected_title)
            default_target_index = target_options.index(detected_id) if detected_id in target_options else 0
            selected_target = st.selectbox(
                "저장할 문자 대화",
                target_options,
                index=default_target_index,
                format_func=lambda value: value if value == direct_entry else conversation_label(value),
                key=f"restore_sms_target_{revision}",
                help="기존 번호를 선택하면 그 사람의 대화에 합쳐집니다.",
            )
            if selected_target == direct_entry:
                conversation_title = st.text_input(
                    "고객 전화번호",
                    value=detected_title,
                    placeholder="010-1234-5678",
                    key=f"restore_title_{revision}",
                )
            else:
                conversation_title = selected_target
                st.caption(f"{conversation_label(selected_target)} 대화에 합쳐서 저장합니다.")
        else:
            conversation_title = st.text_input(
                "인스타그램 고객 구분",
                value=detected_title,
                placeholder="인스타그램 계정명 또는 고객 이름",
                key=f"restore_title_{revision}",
            )

        if restored.get("warnings"):
            with st.expander("⚠️ AI가 확인을 요청한 부분", expanded=True):
                for warning in restored["warnings"]:
                    st.write(f"- {warning}")

        st.caption("인식이 잘못된 부분은 셀을 눌러 직접 수정하거나 행을 추가·삭제할 수 있습니다.")
        edited_messages = st.data_editor(
            restored["messages"],
            column_config={
                "보낸 사람": st.column_config.SelectboxColumn(
                    "보낸 사람",
                    options=["고객", "산도리"],
                    required=True,
                ),
                "내용": st.column_config.TextColumn("내용", required=True, width="large"),
                "시간": st.column_config.TextColumn("시간"),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"restored_editor_{revision}",
        )
        restored_messages = [
            item for item in as_records(edited_messages)
            if str(item.get("내용", "")).strip()
        ]
        st.session_state.restored_conversation["messages"] = restored_messages

        st.markdown("##### 복원된 대화")
        render_chat(restored_messages)

        already_saved = st.session_state.saved_restore_revision == revision
        if st.button(
            "✅ 메시지 목록에 저장됨" if already_saved else "💾 복원 대화를 메시지 목록에 저장",
            type="secondary" if already_saved else "primary",
            use_container_width=True,
            disabled=already_saved,
            key=f"restore_save_{revision}",
        ):
            if not restored_messages:
                st.error("저장할 대화 내용이 없습니다.")
            else:
                with st.spinner("복원한 대화를 메시지 목록에 저장 중입니다..."):
                    try:
                        conversation_id, saved_count, skipped_count = save_restored_messages(
                            channel,
                            conversation_title,
                            restored_messages,
                            sms_data,
                        )
                        st.session_state.saved_restore_revision = revision
                        st.session_state.current_chat = conversation_id
                        notice = f"✅ 새 메시지 {saved_count}개를 메시지 목록에 저장했습니다."
                        if skipped_count:
                            notice += f" 기존과 중복된 {skipped_count}개는 제외했습니다."
                        st.session_state.restore_save_notice = notice
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 메시지 목록에 저장하지 못했습니다: {e}")

        st.caption("저장된 대화의 목록 시간은 현재 구글 시트 구조에 따라 복원한 시각으로 표시됩니다.")

        export_data = {
            "channel": channel,
            "conversation_title": conversation_title,
            "messages": restored_messages,
        }
        st.download_button(
            "⬇️ 복원 대화 JSON 내려받기",
            data=json.dumps(export_data, ensure_ascii=False, indent=2),
            file_name="sandoli_restored_conversation.json",
            mime="application/json",
            use_container_width=True,
        )

        col_generate, col_clear = st.columns([2, 1])
        with col_generate:
            if st.button("✨ 이 대화로 AI 답변 초안 생성", use_container_width=True, key=f"restore_ai_{revision}"):
                if not st.session_state.gemini_api_key:
                    st.error("시스템 연결 탭에서 Gemini API 키를 확인해주세요.")
                elif not restored_messages:
                    st.error("답변을 만들 대화 내용이 없습니다.")
                else:
                    with st.spinner("AI가 답변 초안을 작성 중입니다..."):
                        try:
                            st.session_state.restored_draft = generate_reply_draft(restored_messages)
                        except Exception as e:
                            st.error(f"❌ 답변을 만들지 못했습니다: {e}")
        with col_clear:
            if st.button("🗑️ 복원 내용 지우기", use_container_width=True, key=f"restore_clear_{revision}"):
                st.session_state.restored_conversation = None
                st.session_state.pop("restored_draft", None)
                st.rerun()

        if "restored_draft" in st.session_state:
            edited_draft = st.text_area(
                "📝 답변 초안 (수정 가능)",
                value=st.session_state.restored_draft,
                height=140,
                key=f"restored_draft_editor_{revision}",
            )

            if channel == "문자":
                phone = normalize_korean_mobile(conversation_title)
                if not re.fullmatch(r"010\d{8}", phone):
                    phone = normalize_korean_mobile(st.text_input(
                        "답변을 보낼 휴대전화 번호",
                        placeholder="01012345678",
                        key=f"restored_phone_{revision}",
                    ))

                if st.button("🚀 문자로 전송하기", type="primary", use_container_width=True, key=f"restored_send_{revision}"):
                    if not re.fullmatch(r"010\d{8}", phone):
                        st.error("010으로 시작하는 휴대전화 번호 11자리를 입력해주세요.")
                    elif not st.session_state.webhook_url:
                        st.error("시스템 연결 탭에서 웹훅 주소를 확인해주세요.")
                    else:
                        try:
                            send_response = requests.get(
                                st.session_state.webhook_url,
                                params={"phone": phone, "msg": edited_draft},
                                timeout=15,
                            )
                            send_response.raise_for_status()
                            # 발신 기록은 영업용폰의 MacroDroid가 저장합니다.
                            st.success("✅ 영업용폰에 문자 발송을 요청했습니다. 발신 기록은 휴대폰에서 등록된 뒤 ‘새로운 메시지 확인’을 누르면 표시됩니다.")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"❌ 문자 전송 중 오류가 발생했습니다: {e}")
            else:
                st.info("인스타그램 자동 전송은 연결되어 있지 않습니다. 위 초안을 복사해 DM에 붙여넣어 주세요.")

with tab1:
    if st.button("🔄 새로운 메시지 확인", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    if st.session_state.current_chat is None:
        unique_phones = []
        for msg in reversed(sms_data):
            if msg['phone'] not in unique_phones: unique_phones.append(msg['phone'])
                
        if not unique_phones:
            st.info("📥 아직 도착한 메시지가 없습니다.")
        else:
            for phone in unique_phones:
                last_msg = next(m for m in reversed(sms_data) if m['phone'] == phone)
                with st.container():
                    col_text, col_btn = st.columns([75, 25])
                    with col_text:
                        sender_prefix = "산도리: " if last_msg['sender'] == "산도리" else ""
                        preview_text = sender_prefix + last_msg['message']
                        if len(preview_text) > 30: preview_text = preview_text[:30] + "..." 
                        safe_label = html.escape(conversation_label(phone))
                        safe_time = html.escape(str(last_msg['time']))
                        safe_preview = html.escape(str(preview_text))
                        st.markdown(f"<strong style='font-size:16px;'>{safe_label}</strong> &nbsp;&nbsp;<span style='color:#a0a0a0; font-size:12px;'>{safe_time}</span>", unsafe_allow_html=True)
                        st.markdown(f"<span style='color:#666; font-size:14px;'>{safe_preview}</span>", unsafe_allow_html=True)
                    with col_btn:
                        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                        if st.button("대화 보기", key=f"btn_{phone}", use_container_width=True):
                            st.session_state.current_chat = phone
                            st.rerun() 
                    st.markdown("<hr style='margin: 10px 0; border: 0; border-top: 1px solid #eee;'>", unsafe_allow_html=True)
    else:
        phone = st.session_state.current_chat
        if st.button("🔙 목록으로 돌아가기"):
            st.session_state.current_chat = None
            st.rerun()
            
        st.subheader(conversation_label(phone))
        filtered_msgs = [msg for msg in sms_data if msg['phone'] == phone]
        render_chat(filtered_msgs)
        chat_history_str = "\n".join(f"{msg['sender']}: {msg['message']}" for msg in filtered_msgs)
        
        # 메뉴 및 영업시간 포맷팅
        formatted_menu_text = "\n".join([f"- {item['메뉴 이름']}: {item['가격']}" for item in st.session_state.menu_list if item.get('메뉴 이름')])
        
        formatted_hours_list = []
        for h in st.session_state.business_hours:
            if h.get("영업여부", True):
                extra = f" ({h['비고']})" if h.get("비고") else ""
                formatted_hours_list.append(f"- {h['요일']}: {h['오픈시간']} ~ {h['마감시간']}{extra}")
            else:
                formatted_hours_list.append(f"- {h['요일']}: 정기휴무")
        formatted_hours_text = "\n".join(formatted_hours_list)
        
        if st.button("✨ AI 답변 초안 생성", key=f"ai_btn_{phone}"):
            if not st.session_state.gemini_api_key: st.error("❌ 시스템 연결 탭에서 Gemini API 키를 확인해주세요!")
            else:
                with st.spinner("AI가 최적의 답변을 작성 중입니다..."):
                    try:
                        final_prompt = f"""{st.session_state.sando_persona}

[메뉴/가격]
{formatted_menu_text}

[매장 영업시간]
{formatted_hours_text}

[기타 매장운영 정보]
{st.session_state.store_info}

[과거 대화 맥락]
{chat_history_str}

위 정보를 바탕으로 고객의 마지막 질문에 친절하고 정확하게 답해줘."""
                        genai.configure(api_key=st.session_state.gemini_api_key)
                        model = genai.GenerativeModel(st.session_state.selected_model)
                        response = model.generate_content(final_prompt)
                        st.session_state[f"draft_{phone}"] = response.text
                    except Exception as e: st.error(f"❌ 오류: {e}")
        
        if f"draft_{phone}" in st.session_state:
            editor_label = "📝 DM 답변 초안 (수정 가능)" if is_instagram_conversation(phone) else "📝 답변 발송 (수정 가능)"
            edited_msg = st.text_area(editor_label, value=st.session_state[f"draft_{phone}"], height=120)

            if is_instagram_conversation(phone):
                st.info("인스타그램 자동 전송은 연결되어 있지 않습니다. 위 초안을 복사해 DM에 붙여넣어 주세요.")
            elif st.button("🚀 문자로 전송하기", type="primary", use_container_width=True, key=f"send_btn_{phone}"):
                if not st.session_state.webhook_url: st.error("❌ 시스템 연결 탭에서 웹훅 주소를 확인해주세요!")
                else:
                    try:
                        send_response = requests.get(
                            st.session_state.webhook_url,
                            params={'phone': phone, 'msg': edited_msg},
                            timeout=15,
                        )
                        send_response.raise_for_status()
                        # 발신 기록은 영업용폰의 MacroDroid가 저장합니다.
                        st.session_state.sms_send_notice = "✅ 영업용폰에 문자 발송을 요청했습니다. 발신 기록은 휴대폰에서 등록된 뒤 ‘새로운 메시지 확인’을 누르면 표시됩니다."
                        del st.session_state[f"draft_{phone}"]
                        st.cache_data.clear() 
                        st.rerun()
                    except Exception as e: st.error(f"❌ 오류 발생: {e}")
