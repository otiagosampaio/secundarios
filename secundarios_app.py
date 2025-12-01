import streamlit as st
import datetime
from dateutil.relativedelta import relativedelta
import base64
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
import requests
from PIL import Image as PILImage
from io import BytesIO as PIOBytesIO
import pandas as pd
import numpy as np

# ===================== CONFIGURAÇÃO =====================
st.set_page_config(page_title="Traders Corretora - Secundários", layout="wide")

# ===================== CSS PARA CENTRALIZAR =====================
st.markdown("""
<style>
.main .block-container {max-width: 70% !important; padding-left: 2rem; padding-right: 2rem;}
.stMarkdown > div > img {display: block; margin-left: auto; margin-right: auto; max-width: 400px; height: auto;}
</style>
""", unsafe_allow_html=True)

# ===================== CONSTANTES =====================
URL_LOGO = "https://ik.imagekit.io/aufhkvnry/logo-traders__bg-white.png"
AZUL_TRADERS = "#6B48FF"
VERDE = "#2E8B57"

# ===================== FUNÇÃO LOGO COM PROPORÇÃO CORRETA =====================
def carregar_logo():
    response = requests.get(URL_LOGO)
    img = PILImage.open(PIOBytesIO(response.content))
    largura, altura = img.size
    proporcao = altura / largura
    largura_desejada = 140
    altura_calculada = largura_desejada * proporcao
    return Image(PIOBytesIO(response.content), width=largura_desejada, height=altura_calculada)

# ===================== FUNÇÃO DE FORMATAÇÃO =====================
brl = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ===================== CÁLCULO DE CADA PAPEL =====================
def calcular_papel(papel, data_aplicacao, cdi_benchmark):
    try:
        valor = float(papel['Valor'])
        taxa_input = float(papel['Taxa'])
        tipo = papel['Tipo']
        vencimento = pd.to_datetime(papel['Data Vencimento']).date()
    except:
        return None, "Dados inválidos"

    prazo_dias = (vencimento - data_aplicacao).days
    if prazo_dias <= 0 or valor <= 0 or taxa_input <= 0:
        return None, "Prazo ou valor inválido"

    # Taxa anual real
    if tipo == "Pós-fixado (% do CDI)":
        taxa_anual = cdi_benchmark * (taxa_input / 100)
    else:
        taxa_anual = taxa_input

    taxa_diaria = (1 + taxa_anual/100)**(1/360) - 1
    montante_bruto = valor * (1 + taxa_diaria)**prazo_dias
    rendimento_bruto = montante_bruto - valor

    # IOF (só se < 30 dias)
    iof = 0.0
    if prazo_dias < 30:
        tabela_iof = [0.96,0.93,0.90,0.86,0.83,0.80,0.76,0.73,0.70,0.66,0.63,0.60,0.56,0.53,0.50,
                      0.46,0.43,0.40,0.36,0.33,0.30,0.26,0.23,0.20,0.16,0.13,0.10,0.06,0.03,0.00]
        iof = tabela_iof[prazo_dias - 1]
        rendimento_apos_iof = rendimento_bruto * (1 - iof)
    else:
        rendimento_apos_iof = rendimento_bruto

    # IR regressivo
    aliquota_ir = 22.5 if prazo_dias <= 180 else 20.0 if prazo_dias <= 360 else 17.5 if prazo_dias <= 720 else 15.0
    ir = rendimento_apos_iof * (aliquota_ir / 100)

    montante_liquido = valor + rendimento_apos_iof - ir
    rendimento_liquido = montante_liquido - valor

    return {
        'Valor Investido': round(valor, 2),
        'Montante Bruto': round(montante_bruto, 2),
        'Rendimento Bruto': round(rendimento_bruto, 2),
        'IOF': round(rendimento_bruto * iof, 2),
        'Alíquota IR': aliquota_ir,
        'IR': round(ir, 2),
        'Total Impostos': round(rendimento_bruto * iof + ir, 2),
        'Montante Líquido': round(montante_liquido, 2),
        'Rendimento Líquido': round(rendimento_liquido, 2),
        'Prazo Dias': prazo_dias,
        'Vencimento': vencimento,
    }, None

# ===================== SESSION STATE =====================
if 'papeis' not in st.session_state:
    st.session_state.papeis = []
if 'cdi_benchmark' not in st.session_state:
    st.session_state.cdi_benchmark = 14.90

# ===================== INTERFACE =====================
st.markdown(f'<img src="{URL_LOGO}" style="max-width:400px; display:block; margin:auto;">', unsafe_allow_html=True)
st.markdown("<h3 style='text-align:center;'>Calculadora de Simulação de Papéis Secundários</h3>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;'>Adicione e gerencie os papéis para simular o resultado consolidado.</p>", unsafe_allow_html=True)
st.markdown("---")

# ===================== DADOS GERAIS =====================
st.subheader("Dados Gerais da Simulação")
c1, c2 = st.columns(2)
with c1:
    nome_cliente = st.text_input("Nome do Cliente", "João Silva")
    nome_assessor = st.text_input("Nome do Assessor", "Marcelo Ferreira")
with c2:
    data_simulacao = st.date_input("Data da Simulação", datetime.date.today(), format="DD/MM/YYYY")
    data_aplicacao = st.date_input("Data de Aplicação", datetime.date.today(), format="DD/MM/YYYY")

st.session_state.cdi_benchmark = st.number_input("Taxa CDI Benchmark (%)", value=st.session_state.cdi_benchmark, step=0.05)

# ===================== TABELA DE PAPÉIS =====================
st.subheader("Papéis para Simulação")
if st.session_state.papeis:
    df = pd.DataFrame(st.session_state.papeis)
    df['Data Vencimento'] = pd.to_datetime(df['Data Vencimento']).dt.date
else:
    df = pd.DataFrame(columns=['Emissor', 'Ticker', 'Valor', 'Tipo', 'Taxa', 'Data Vencimento'])

edited = st.data_editor(
    df.rename(columns={
        'Valor': 'Valor Investido (R$)',
        'Tipo': 'Tipo de Taxa',
        'Taxa': 'Taxa (%)',
        'Data Vencimento': 'Vencimento'
    }),
    num_rows="dynamic",
    column_config={
        "Valor Investido (R$)": st.column_config.NumberColumn(format="%.2f", min_value=0.01),
        "Tipo de Taxa": st.column_config.SelectboxColumn(options=["Pré-fixado", "Pós-fixado (% do CDI)"]),
        "Taxa (%)": st.column_config.NumberColumn(format="%.2f", min_value=0.01),
        "Vencimento": st.column_config.DateColumn(format="DD/MM/YYYY", min_value=datetime.date.today()+datetime.timedelta(days=1))
    },
    hide_index=True
)

# Atualiza session state
df_new = edited.rename(columns={
    'Valor Investido (R$)': 'Valor',
    'Tipo de Taxa': 'Tipo',
    'Taxa (%)': 'Taxa',
    'Vencimento': 'Data Vencimento'
})
st.session_state.papeis = df_new.dropna(subset=['Valor', 'Taxa', 'Data Vencimento']).to_dict('records')

if st.button("Limpar Todos os Papéis", type="secondary"):
    st.session_state.papeis = []
    st.rerun()

# ===================== CÁLCULOS CONSOLIDADOS =====================
if not st.session_state.papeis:
    st.info("Adicione pelo menos um papel para calcular.")
    st.stop()

resultados = []
for p in st.session_state.papeis:
    res, erro = calcular_papel(p, data_aplicacao, st.session_state.cdi_benchmark)
    if res:
        resultados.append({**p, **res})

total_investido = sum(r['Valor Investido'] for r in resultados)
total_bruto = sum(r['Montante Bruto'] for r in resultados)
total_iof = sum(r['IOF'] for r in resultados)
total_ir = sum(r['IR'] for r in resultados)
total_impostos = total_iof + total_ir
total_liquido = sum(r['Montante Líquido'] for r in resultados)
rendimento_liquido_total = total_liquido - total_investido
rentabilidade = (rendimento_liquido_total / total_investido) * 100 if total_investido > 0 else 0

st.markdown("---")
st.subheader("Resultado Consolidado")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Investido", brl(total_investido))
c2.metric("Montante Bruto", brl(total_bruto))
c3.metric("Impostos (IR + IOF)", brl(total_impostos))
c4.metric("Montante Líquido", brl(total_liquido))

st.markdown(f"**Rendimento Líquido Total:** {brl(rendimento_liquido_total)}")
st.markdown(f"**Rentabilidade Líquida Efetiva:** {rentabilidade:.2f}%")

# ===================== PDF CORRETO =====================
def grafico_png():
    df = pd.DataFrame(resultados)
    df['Mês/Ano'] = pd.to_datetime(df['Vencimento']).dt.strftime('%m/%Y')
    timeline = df.groupby('Mês/Ano')['Valor Investido'].sum().reset_index()
    timeline = timeline.sort_values('Mês/Ano')

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(timeline['Mês/Ano'], timeline['Valor Investido'], color=AZUL_TRADERS, alpha=0.9)
    ax.set_title("Timeline de Liquidez", fontsize=14, pad=20)
    ax.set_xlabel("")
    ax.grid(axis='x', alpha=0.3)

    for bar in bars:
        width = bar.get_width()
        ax.text(width + max(timeline['Valor Investido'])*0.01, bar.get_y() + bar.get_height()/2,
                brl(width), va='center', ha='left', fontsize=9, fontweight='bold')

    ax.set_xlim(right=max(timeline['Valor Investido'])*1.25)
    ax.xaxis.set_major_formatter(mticker.NullFormatter())

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close()
    return buf

def criar_pdf():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    story = []

    story.append(carregar_logo())
    story.append(Spacer(1, 15*mm))
    story.append(Paragraph("<b>Simulação Personalizada de Investimentos</b>", ParagraphStyle(name='Title', fontSize=20, alignment=1)))
    story.append(Paragraph("Projeção considerando IR e IOF", ParagraphStyle(name='Sub', fontSize=12, alignment=1, textColor=colors.grey)))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey, spaceBefore=10, spaceAfter=15))

    story.append(Paragraph("<b>DADOS DA SIMULAÇÃO</b>", ParagraphStyle(name='H3', fontSize=14, spaceAfter=10)))
    dados = [
        ["Nome do cliente", nome_cliente, "Data da simulação", data_simulacao.strftime('%d/%m/%Y')],
        ["Valor investido", brl(total_investido), "Tipo de CDB", "Múltiplos"],
    ]
    t = Table(dados, colWidths=[65*mm, 65*mm, 65*mm, 65*mm])
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (0,1), colors.HexColor("#f3f4f6")),
                           ('BACKGROUND', (2,0), (2,1), colors.HexColor("#f3f4f6")),
                           ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
                           ('FONTSIZE', (0,1), (-1,1), 13)]))
    story.append(t)
    story.append(Spacer(1, 20*mm))

    story.append(Image(grafico_png(), width=170*mm, height=80*mm))
    story.append(Spacer(1, 20*mm))

    res = [["VALOR BRUTO", "IMPOSTOS", "VALOR LÍQUIDO"],
           [brl(total_bruto), brl(total_impostos), brl(total_liquido)]]
    t_res = Table(res, colWidths=[56*mm]*3)
    t_res.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1e3a8a")),
                               ('TEXTCOLOR', (0,0), (-1,-1), colors.white),
                               ('FONTSIZE', (0,1), (-1,1), 18),
                               ('GRID', (0,0), (-1,-1), 0, colors.transparent),
                               ('ROUNDEDCORNERS', (0,0), (-1,-1), 15)]))
    story.append(t_res)

    story.append(Spacer(1, 20*mm))
    story.append(Paragraph(f"Simulação elaborada por <b>{nome_assessor}</b>", ParagraphStyle(name='Footer', fontSize=11, alignment=1)))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ===================== BOTÃO PDF =====================
if st.button("BAIXAR PROPOSTA PREMIUM", type="primary", use_container_width=True):
    with st.spinner("Gerando PDF..."):
        pdf = criar_pdf()
        b64 = base64.b64encode(pdf).decode()
        href = f'<a href="data:application/pdf;base64,{b64}" download="Proposta_Secundarios.pdf"><h3>BAIXAR PDF</h3></a>'
        st.markdown(href, unsafe_allow_html=True)
        st.success("PDF gerado com sucesso!")

st.markdown(f"<p style='text-align:center; margin-top:40px;'>Simulação elaborada por <b>{nome_assessor}</b></p>", unsafe_allow_html=True)
