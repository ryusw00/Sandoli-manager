import streamlit as st
import os
import requests
import json

# 1. 페이지 설정
st.set_page_config(page_title="산도리 통합 관리", page_icon="🍓", layout="wide")

# 🚨 방금 사장님이 만드신 구글 스프레드시트 DB 주소
DB_URL = "https://script.google.com/macros/s/AKfycbz_43zmUq1z95JBauFRtiqtvMv2jxDV7neGmQca8w8Z-NmIKivvc88QVWIsTNccCZ_IIg/exec"

# 2. 구글 시트에서 문자 기록 불러오기
def load_sms_logs():
    try:
        response = requests.get(DB_URL + "?action=read")
        if response.status_code == 200:
            raw_data = response.json()
            if len(raw_data) <= 1: # 데이터가 없거나 헤더만 있는 경우
                return []
            
            logs = []
            for row in raw_data[1:]: # 첫 번째 줄(헤더)은 제외하고 읽기
                if len(row) >= 4:
                    # row[0]:시간, row[1]:전화번호, row[2]:내용, row[3]:보낸사람
                    logs.append({
                        "time": row[0],
                        "phone": str("0" + str(row[1])) if str(row[1]).startswith("10") else str(row[1]), # 전화번호 앞자리 0 빠짐 방지
                        "message": row[2],
                        "sender": row[3]
                    })
            return logs
    except Exception as e:
        st.error("데이터베이스를 불러오는 중 오류가 발생했습니다.")
    return []

sms_data = load_sms_logs()

# ---------------------------------------------------------
# 3. AI 페르소나 및 설정 메모리 초기화
# ---------------------------------------------------------
if 'sando_persona' not in st.session_state:
    st.session_state.sando_persona = """당신은 프리미엄 디저트 카페 '산도리(sando.li)'의 친절하고 전문적인 고객 응대 매니저입니다.
제공된 정보에 한해서 답변해. 없는 정보에 대해서는 답변하지 말고, "확인 필요"라는 안내 메세지를 보내줘.
고객의 질문에 대답할 때, 항상 '함께 전달되는 실시간 재고/가격 정보'를 최우선으로 확인하고 답변해야 합니다.
없는 메뉴나 품절된 메뉴는 정중하게 품절을 안내하세요.
시작 문구는 "안녕하세요. 프리미엄 과일산도&모찌 전문점 산도리 입니다." 로 시작해줘.
친절하고 따뜻하고, 친근한 톤을 유지하고 적절한 이모티콘 도 섞어서 대답해줘, 부정적 표현(거절, 불가, 위험, 문제 등)은 직접적으로 사용하지 말고 완만한 표현으로 대체해줘.
(예 : 어려울 수 있어 안내 도와드립니다, 현재 제공되지 않는 점 양해 부탁드립니다 등)
기호나 # 기호 등 마크다운 서식은 절대 작성하지 마. (텍스트로만 깔끔하게 답변해)
산도 말할때 앞에 수식어를 붙이지 말아줘, 그리고 ~~하는게 어떨까요? 이런 권유도 하지 말아줘"""

if 'menu_list' not in st.session_state:
    st.session_state.menu_list = [
        {"메뉴 이름": "금실/죽향 딸기 산도", "가격": "8,000원"},
        {"메뉴 이름": "백자 메론 산도", "가격": "8,500원"},
        {"메뉴 이름": "자몽 소르베 에스프레소", "가격": "6,500원"}
    ]

if 'daily_notes' not in st.session_state:
    st.session_state.daily_notes = "오늘 백자 메론 당도가 매우 높습니다! 딸기 산도는 품절 임박입니다."
if 'webhook_url' not in st.session_state:
    st.session_state.webhook_url = ""

# ---------------------------------------------------------
# 4. 왼쪽 사이드바 (최신순 연락처 정렬)
# ---------------------------------------------------------
with st.sidebar:
    st.title("📞 과거 연락처 목록")
    
    unique_phones = []
    for msg in reversed(sms_data):
        if msg['phone'] not in unique_phones:
            unique_phones.append(msg['phone'])
            
    if not unique_phones:
        st.info("아직 수신된 연락처가 없습니다.")
        selected_phone = None
    else:
        selected_phone = st.radio("대화 내용을 확인할 번호 (최신순):", unique_phones)

# ---------------------------------------------------------
# 5. 오른쪽 메인 화면
# ---------------------------------------------------------
st.title("🍓 산도리(sando.li) 실시간 문자 관리")

tab1, tab2 = st.tabs(["💬 실시간 고객 문의", "⚙️ AI 페르소나 및 설정"])

# --- [탭 2] 설정 화면 ---
with tab2:
    st.subheader("🤖 AI 페르소나 (성격 및 행동 규칙)")
    st.session_state.sando_persona = st.text_area("이곳에 AI의 행동 지침을 자유롭게 수정하고 입력하세요.", value=st.session_state.sando_persona, height=220)
    
    st.markdown("---")
    
    col1, col2 = st.columns([6, 4])
    with col1:
        st.subheader("📋 메뉴 및 가격 관리 (표 수정 가능)")
        edited_menu = st.data_editor(
            st.session_state.menu_list,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "메뉴 이름": st.column_config.TextColumn("메뉴 이름", width="large", required=True),
                "가격": st.column_config.TextColumn("가격", width="medium", required=True)
            },
            key="menu_table_editor"
        )
        st.session_state.menu_list = edited_menu

    with col2:
        st.subheader("🚨 오늘의 특이사항")
        st.session_state.daily_notes = st.text_area("품절 여부, 당도 안내 등", value=st.session_state.daily_notes, height=180)
    
    st.markdown("---")
    st.subheader("📡 S21 자동 발송 연결 (웹훅)")
    st.session_state.webhook_url = st.text_input("🔗 매크로드로이드 웹훅 발송 주소", value=st.session_state.webhook_url)

# --- [탭 1] 실시간 채팅 및 발송 화면 ---
with tab1:
    if selected_phone:
        st.subheader(f"📞 [{selected_phone}] 고객님과의 대화")
        
        filtered_msgs = [msg for msg in sms_data if msg['phone'] == selected_phone]
        chat_history_str = ""
        formatted_menu_text = "\n".join([f"- {item['메뉴 이름']}: {item['가격']}" for item in st.session_state.menu_list if item.get('메뉴 이름')])
        
        # 카카오톡처럼 대화 내용 렌더링
        for i, msg in enumerate(filtered_msgs):
            # 보낸 사람이 '산도리'인지 '고객'인지에 따라 채팅방 UI 변경
            role = "assistant" if msg['sender'] == "산도리" else "user"
            
            with st.chat_message(role):
                st.markdown(f"`[{msg['time']}] {msg['sender']}`")
                st.write(msg['message'])
                
            # AI 프롬프트용 맥락 누적 (산도리가 한 말도 함께 기억함!)
            chat_history_str += f"{msg['sender']}: {msg['message']}\n"
        
        # 가장 마지막 대화 밑에 답장 달기 UI
        st.markdown("---")
        if st.button("✨ AI 답변 초안 생성", key=f"ai_btn_{selected_phone}"):
            final_prompt = f"""
            {st.session_state.sando_persona}
            
            [실시간 매장 메뉴 및 가격 정보]
            {formatted_menu_text}
            
            [오늘의 특이사항]
            {st.session_state.daily_notes}
            
            [해당 고객과의 과거 대화 맥락]
            {chat_history_str}
            
            위 규칙과 정보를 바탕으로 가장 마지막 고객의 질문에 대한 답변을 작성해.
            """
            
            # (임시) 진짜 AI 키가 들어가기 전 테스트 문구
            menu_summary_str = ", ".join([f"{item['메뉴 이름']}({item['가격']})" for item in st.session_state.menu_list if item.get('메뉴 이름')])
            reply_draft = f"안녕하세요. 프리미엄 과일산도&모찌 전문점 산도리 입니다. 문의하신 내용 확인했습니다. 현재 준비되어 있는 메뉴는 {menu_summary_str} 입니다. {st.session_state.daily_notes} 원하시는 메뉴와 픽업 시간을 말씀해 주시면 예약 안내 도와드리겠습니다. 😊"
            
            st.session_state[f"draft_{selected_phone}"] = reply_draft
            st.session_state[f"prompt_{selected_phone}"] = final_prompt
        
        if f"draft_{selected_phone}" in st.session_state:
            with st.expander("🔍 AI 두뇌로 들어간 최종 데이터 (클릭해서 확인)"):
                st.text(st.session_state[f"prompt_{selected_phone}"])
            
            edited_msg = st.text_area("📝 AI 답변 초안 (이곳에서 내용을 직접 수정할 수 있습니다.)", value=st.session_state[f"draft_{selected_phone}"], height=150)
            
            if st.button("🚀 S21로 진짜 문자 발송 및 기록하기", key=f"send_btn_{selected_phone}"):
                if not st.session_state.webhook_url:
                    st.error("❌ 발송 실패: [⚙️ 설정] 탭에서 웹훅 주소를 먼저 입력해주세요!")
                else:
                    try:
                        # 1. S21을 통해 실제 문자 발송 (매크로드로이드)
                        send_payload = {'phone': selected_phone, 'msg': edited_msg}
                        requests.get(st.session_state.webhook_url, params=send_payload)
                        
                        # 2. 구글 시트에 "산도리"가 보냈다고 기록 저장 
                        # (그래야 다음번에 AI가 자신이 한 말을 기억함)
                        log_payload = {'phone': selected_phone, 'msg': edited_msg, 'sender': '산도리'}
                        requests.get(DB_URL, params=log_payload)
                        
                        st.success("✅ 발송 완료 및 기록 저장 성공! (화면을 새로고침 합니다)")
                        del st.session_state[f"draft_{selected_phone}"] # 임시 저장 데이터 삭제
                        st.rerun() # 화면 즉시 새로고침
                        
                    except Exception as e:
                        st.error(f"❌ 오류 발생: {e}")
    else:
        st.info("👈 왼쪽 메뉴에서 연락처를 선택하거나, S21 폰으로 새 문자가 들어오기를 기다려주세요.")
