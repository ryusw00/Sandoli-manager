import streamlit as st
import requests
import json
import google.generativeai as genai

st.set_page_config(page_title="산도리 메신저", page_icon="🍓", layout="centered") 

DB_URL = "https://script.google.com/macros/s/AKfycbz_43zmUq1z95JBauFRtiqtvMv2jxDV7neGmQca8w8Z-NmIKivvc88QVWIsTNccCZ_IIg/exec"

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
            for row in raw_data[1:]:
                if len(row) >= 4:
                    logs.append({"time": row[0], "phone": str("0" + str(row[1])) if str(row[1]).startswith("10") else str(row[1]), "message": row[2], "sender": row[3]})
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

st.title("🍓 산도리 메신저")

tab1, tab2, tab3 = st.tabs(["💬 메시지", "🍓 매장 및 AI 설정", "⚙️ 시스템 연결"])

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
                        st.markdown(f"<strong style='font-size:16px;'>📞 {phone}</strong> &nbsp;&nbsp;<span style='color:#a0a0a0; font-size:12px;'>{last_msg['time']}</span>", unsafe_allow_html=True)
                        st.markdown(f"<span style='color:#666; font-size:14px;'>{preview_text}</span>", unsafe_allow_html=True)
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
            
        st.subheader(f"📞 {phone}")
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
        
        filtered_msgs = [msg for msg in sms_data if msg['phone'] == phone]
        chat_history_str = ""
        chat_html = '<div class="chat-bg">\n'
        for msg in filtered_msgs:
            role_class = "sando" if msg['sender'] == "산도리" else "user"
            chat_html += f'<div class="msg-row {role_class}"><div class="bubble">{msg["message"]}</div><div class="time">{msg["time"]}</div></div>\n'
            chat_history_str += f"{msg['sender']}: {msg['message']}\n"
        chat_html += '</div>'
        st.markdown(chat_html, unsafe_allow_html=True)
        
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
            edited_msg = st.text_area("📝 답변 발송 (수정 가능)", value=st.session_state[f"draft_{phone}"], height=120)
            if st.button("🚀 문자로 전송하기", type="primary", use_container_width=True, key=f"send_btn_{phone}"):
                if not st.session_state.webhook_url: st.error("❌ 시스템 연결 탭에서 웹훅 주소를 확인해주세요!")
                else:
                    try:
                        requests.get(st.session_state.webhook_url, params={'phone': phone, 'msg': edited_msg})
                        requests.get(DB_URL, params={'phone': phone, 'msg': edited_msg, 'sender': '산도리'})
                        st.success("✅ 전송 완료!")
                        del st.session_state[f"draft_{phone}"]
                        st.cache_data.clear() 
                        st.rerun()
                    except Exception as e: st.error(f"❌ 오류 발생: {e}")
