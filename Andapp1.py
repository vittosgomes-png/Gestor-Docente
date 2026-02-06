from google.genai import errors
from datetime import datetime, date, timedelta
import io
import re
import json
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from streamlit_gsheets import GSheetsConnection

# --- 1. DESIGN PROFISSIONAL ---
st.set_page_config(page_title="Gestor Docente APK", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #ffffff; color: #000000; }
    .stButton>button { 
        width: 100%; height: 3.5rem; background-color: #003366;
        color: #ffffff !important; border-radius: 10px; font-weight: bold; border: none;
    }
    .metric-card { 
        background-color: #f8f9fa; padding: 15px; border-radius: 12px; 
        text-align: center; border: 1px solid #dee2e6; margin-bottom: 10px;
    }
    .metric-value { font-size: 24px; font-weight: bold; color: #003366; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXÃO GOOGLE SHEETS & IA ---
API_KEY = "AIzaSyBdvhiUtLcjdbaneNm5qWjzRnXhK8q9k7I"
client = genai.Client(api_key=API_KEY)
MODEL_ID = "gemini-2.0-flash"

conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. FUNÇÕES DE PERSISTÊNCIA (O Tanque de Dados) ---
def salvar_na_nuvem():
    # Serializa os dados para texto para caber em uma célula da planilha
    dados_serializados = json.dumps(st.session_state.dados, default=str)
    conn.update(worksheet="Sheet1", data=[[dados_serializados]])
    st.toast("Dados sincronizados com a nuvem! ☁️")

def carregar_da_nuvem():
    try:
        df = conn.read(worksheet="Sheet1", usecols=[0], nrows=1)
        if not df.empty:
            dados_json = df.iloc[0, 0]
            # Aqui precisaríamos de um parser mais robusto para datas, 
            # mas para o MVP vamos focar na estrutura
            st.session_state.dados = json.loads(dados_json)
            return True
    except:
        return False
    return False

# --- 4. FUNÇÕES TÉCNICAS (PDF) ---
def limpar_texto_para_pdf(texto):
    texto = texto.replace('<br>', '\n').replace('<br/>', '\n')
    texto = re.sub(r'\*\*(.*?)\*\*', r'\1', texto)
    return texto.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def gerar_pdf_planejamento(escola, turma, disciplina, planos, professor):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    cor_azul = colors.HexColor("#003366")
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=TA_CENTER, textColor=cor_azul)
    elements.append(Paragraph(f"Planejamento: {escola}", title_style))
    elements.append(Paragraph(f"Professor: {professor} | Disciplina: {disciplina} | Turma: {turma}", styles['Normal']))
    elements.append(Spacer(1, 20))
    data_tabela = [["Data", "Duração", "Conteúdo / Tema"]]
    for k in sorted(planos.keys()):
        aula = planos[k]
        dt_f = datetime.strptime(aula['data_pura'], '%Y-%m-%d').strftime('%d/%m/%Y')
        data_tabela.append([dt_f, f"{aula['duracao']} min", aula['tema']])
    t = Table(data_tabela, colWidths=[80, 70, 300])
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), cor_azul), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('GRID', (0,0), (-1,-1), 1, colors.grey)]))
    elements.append(t)
    doc.build(elements)
    return buffer.getvalue()

def gerar_pdf_aula(tema, conteudo):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [Paragraph(f"Roteiro: {tema}", styles['Heading1']), Spacer(1, 12)]
    texto_limpo = limpar_texto_para_pdf(conteudo)
    for linha in texto_limpo.split('\n'):
        elements.append(Paragraph(linha, styles['Normal']) if linha.strip() else Spacer(1, 6))
    doc.build(elements)
    return buffer.getvalue()

# --- 5. INICIALIZAÇÃO ---
if 'dados' not in st.session_state:
    if not carregar_da_nuvem():
        st.session_state.dados = {
            "usuario": "", "escolas": {}, "feriados": [],
            "bimestres": {i: [None, None] for i in range(1, 5)},
            "ferias_meio": [None, None]
        }

# --- 6. SIDEBAR ---
with st.sidebar:
    st.header("Configurações 📱")
    st.session_state.dados["usuario"] = st.text_input("Seu Nome", value=st.session_state.dados["usuario"])
    
    if st.button("☁️ Sincronizar Agora"):
        salvar_na_nuvem()

    with st.expander("🏫 Escolas"):
        n_esc = st.text_input("Nome da Escola")
        d_esc = st.selectbox("Disciplina", ["Ciências", "Matemática", "Português", "História"])
        if st.button("➕ Adicionar Unidade Escolar"):
            if n_esc:
                st.session_state.dados["escolas"][n_esc] = {"disciplina": d_esc, "turmas": []}
                salvar_na_nuvem()
                st.rerun()
        for e in list(st.session_state.dados["escolas"].keys()):
            if st.button(f"🗑️ Remover {e}"):
                del st.session_state.dados["escolas"][e]
                salvar_na_nuvem()
                st.rerun()

    with st.expander("📅 Bimestres"):
        for i in range(1, 5):
            st.write(f"**{i}º Bimestre**")
            st.session_state.dados["bimestres"][i][0] = st.date_input(f"Início B{i}", key=f"bi_{i}", value=st.session_state.dados["bimestres"][i][0])
            st.session_state.dados["bimestres"][i][1] = st.date_input(f"Fim B{i}", key=f"bf_{i}", value=st.session_state.dados["bimestres"][i][1])

    with st.expander("🌴 Férias e Feriados"):
        st.write("**Férias de Julho**")
        st.session_state.dados["ferias_meio"][0] = st.date_input("Início", key="fi", value=st.session_state.dados["ferias_meio"][0])
        st.session_state.dados["ferias_meio"][1] = st.date_input("Fim", key="ff", value=st.session_state.dados["ferias_meio"][1])
        st.divider()
        st.write("**Feriados/Recessos**")
        f_data = st.date_input("Bloquear Nova Data")
        if st.button("🙌 Inserir Feriado"):
            if f_data not in st.session_state.dados["feriados"]:
                st.session_state.dados["feriados"].append(f_data)
                salvar_na_nuvem()
        for d in sorted(st.session_state.dados["feriados"]):
            st.write(f"• {d.strftime('%d/%m/%Y')}")

# --- 7. PAINEL PRINCIPAL ---
st.title("Gestor Docente")

tab_turmas, tab_plano, tab_dash = st.tabs(["👥 Turmas", "🗓️ Plano", "📈 Dashboard"])

with tab_turmas:
    if st.session_state.dados["escolas"]:
        esc_alvo = st.selectbox("Selecione Escola", options=list(st.session_state.dados["escolas"].keys()))
        nome_t = st.text_input("Turma (Ex: 901)")
        ano_t = st.selectbox("Ano Escolar", ["6º", "7º", "8º", "9º"])
        st.divider()
        if 'temp_horarios' not in st.session_state: st.session_state.temp_horarios = []
        d_nome = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        dia_h = st.selectbox("Dia", range(7), format_func=lambda x: d_nome[x])
        ini_h = st.time_input("Hora Início")
        fim_h = st.time_input("Hora Fim")
        if st.button("➕ Adicionar Horário"):
            dur = (datetime.combine(datetime.today(), fim_h) - datetime.combine(datetime.today(), ini_h)).seconds // 60
            st.session_state.temp_horarios.append({"dia": dia_h, "inicio": ini_h, "fim": fim_h, "duracao": dur})
        for i, h in enumerate(st.session_state.temp_horarios):
            st.info(f"{d_nome[h['dia']]} | {h['inicio']} - {h['fim']}")
        if st.button("💾 SALVAR TURMA"):
            if nome_t and st.session_state.temp_horarios:
                st.session_state.dados["escolas"][esc_alvo]["turmas"].append({
                    "nome": nome_t, "ano": ano_t, "horarios": st.session_state.temp_horarios.copy(), "planos": {}, "temas_originais": []
                })
                st.session_state.temp_horarios = []
                salvar_na_nuvem()
                st.success("Turma Salva!")

with tab_plano:
    if st.session_state.dados["escolas"]:
        esc_p = st.selectbox("Escola para Plano", options=list(st.session_state.dados["escolas"].keys()), key="esc_p")
        turmas_p = [t["nome"] for t in st.session_state.dados["escolas"][esc_p]["turmas"]]
        if turmas_p:
            turma_p = st.selectbox("Escolher Turma", turmas_p)
            bimestre_p = st.selectbox("Bimestre Letivo", [1, 2, 3, 4])
            cont_raw = st.text_area("Lista de Conteúdos (Um por linha)")
            if st.button("👨‍💻 DISTRIBUIR CONTEÚDO"):
                data_ini = st.session_state.dados["bimestres"][bimestre_p][0]
                data_fim = st.session_state.dados["bimestres"][bimestre_p][1]
                if data_ini and data_fim:
                    t_obj = next(t for t in st.session_state.dados["escolas"][esc_p]["turmas"] if t["nome"] == turma_p)
                    temas = [c.strip() for c in cont_raw.split("\n") if c.strip()]
                    t_obj["temas_originais"] = temas
                    datas_letivas = []
                    curr = data_ini
                    while curr <= data_fim:
                        is_ferias = False
                        if st.session_state.dados["ferias_meio"][0] and st.session_state.dados["ferias_meio"][1]:
                            is_ferias = st.session_state.dados["ferias_meio"][0] <= curr <= st.session_state.dados["ferias_meio"][1]
                        if curr.weekday() in [h['dia'] for h in t_obj['horarios']] and not is_ferias and curr not in st.session_state.dados["feriados"]:
                            for h in t_obj['horarios']:
                                if curr.weekday() == h['dia']: datas_letivas.append((curr, h['duracao']))
                        curr += timedelta(days=1)
                    t_obj["planos"] = {}
                    for i, (dt, dur) in enumerate(datas_letivas):
                        idx = int((i/len(datas_letivas))*len(temas)) if temas else 0
                        t_obj["planos"][dt.strftime("%Y-%m-%d %H:%M")] = {"data_pura": dt.strftime("%Y-%m-%d"), "tema": temas[idx] if temas else "Revisão", "duracao": dur}
                    salvar_na_nuvem()
                    st.success("Plano Automático Gerado!")
                else: st.error("Defina as datas na lateral!")

with tab_dash:
    if st.session_state.dados["escolas"]:
        esc_v = st.selectbox("Filtrar Escola", list(st.session_state.dados["escolas"].keys()), key="esc_v")
        t_list = [t["nome"] for t in st.session_state.dados["escolas"][esc_v]["turmas"]]
        if t_list:
            turma_v = st.selectbox("Filtrar Turma", t_list, key="turma_v")
            t_obj = next(t for t in st.session_state.dados["escolas"][esc_v]["turmas"] if t["nome"] == turma_v)
            if t_obj["planos"]:
                hoje = date.today()
                a_ia = sum(1 for k in t_obj["planos"] if f"res_{k}" in st.session_state)
                a_rest = sum(1 for k in t_obj["planos"] if datetime.strptime(t_obj["planos"][k]["data_pura"], '%Y-%m-%d').date() >= hoje)
                
                m1, m2, m3 = st.columns(3)
                with m1: st.markdown(f'<div class="metric-card"><div class="metric-value">{int((a_ia/len(t_obj["planos"]))*100)}%</div><div class="metric-label">Preparado</div></div>', unsafe_allow_html=True)
                with m2: st.markdown(f'<div class="metric-card"><div class="metric-value">{a_rest}</div><div class="metric-label">Restantes</div></div>', unsafe_allow_html=True)
                with m3:
                    t_falt = len(t_obj.get("temas_originais", [])) - a_ia
                    sc = "#10b981" if a_rest >= t_falt else "#ef4444"
                    st.markdown(f'<div class="metric-card" style="border-top: 5px solid {sc}"><div class="metric-value" style="color: {sc}">{ "OK" if a_rest >= t_falt else "Falta" }</div><div class="metric-label">Status</div></div>', unsafe_allow_html=True)
                
                st.divider()
                pdf_p = gerar_pdf_planejamento(esc_v, turma_v, st.session_state.dados["escolas"][esc_v]["disciplina"], t_obj["planos"], st.session_state.dados["usuario"])
                st.download_button("📥 Baixar Plano (PDF)", data=pdf_p, file_name=f"Plano_{turma_v}.pdf")
                for k in sorted(t_obj["planos"].keys()):
                    aula = t_obj["planos"][k]
                    status_icon = "✅" if f"res_{k}" in st.session_state else "⏳"
                    with st.expander(f"{status_icon} {datetime.strptime(aula['data_pura'], '%Y-%m-%d').strftime('%d/%m/%Y')} — {aula['tema']}"):
                        aula['tema'] = st.text_input("Ajustar Tema", value=aula['tema'], key=f"ed_{k}")
                        if st.button("🧠 Gerar com IA", key=f"ai_{k}"):
                            try:
                                resp = client.models.generate_content(model=MODEL_ID, contents=f"Roteiro: {aula['tema']}")
                                st.session_state[f"res_{k}"] = resp.text
                                salvar_na_nuvem()
                                st.rerun()
                            except errors.ClientError: st.warning("Limite atingido.")
                        if f"res_{k}" in st.session_state:
                            st.markdown(st.session_state[f"res_{k}"])
                            pdf_a = gerar_pdf_aula(aula['tema'], st.session_state[f"res_{k}"])
                            st.download_button("📄 Salvar PDF", data=pdf_a, file_name=f"Aula_{k}.pdf", key=f"dl_{k}")
