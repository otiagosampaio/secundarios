import streamlit as st
import datetime
from dateutil.relativedelta import relativedelta
import base64
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
import requests
from PIL import Image as PILImage
from io import BytesIO as PIOBytesIO
import pandas as pd

# ===================== CSS E CONFIG =====================
st.markdown("""
<style>
.main .block-container {max-width: 70% !important; padding-left: 2rem; padding-right: 2rem;}
.stMarkdown > div > img {display: block; margin-left: auto; margin-right: auto; max-width: 400px; height: auto;}
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="Traders Secundários - Calculadora", layout="wide")
URL_LOGO_WHITE = "https://ik.imagekit.io/aufhkvnry/logo-traders__bg-white.png"

# ===================== FUNÇÕES AUXILIARES =====================
def carregar_logo():
    response = requests.get(URL_LOGO_WHITE)
    img_pil = PILImage.open(PIOBytesIO(response.content))
    largura, altura = img_pil.size
    proporcao = altura / largura
    largura_desejada = 80 * mm
    altura_calculada = largura_desejada * proporcao
    return Image(PIOBytesIO(response.content), width=largura_desejada, height=altura_calculada)

def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ===================== CÁLCULO DO PAPEL =====================
def calcular_papel(papel, data_aplicacao, taxa_cdi_benchmark):
    try:
        valor_investido = float(papel['Valor'])
        taxa_input = float(papel['Taxa'])
        tipo = papel['Tipo']
        data_vencimento = pd.to_datetime(papel['Data Vencimento']).date()
    except:
        return None, "Dados inválidos"

    prazo_dias = (data_vencimento - data_aplicacao).days
    if prazo_dias <= 0:
        return None, "Vencimento deve ser futuro"

    dias_ano = 360
    taxa_anual_real = taxa_input
    if tipo == "Pós-fixado (% do CDI)":
        taxa_anual_real = taxa_cdi_benchmark * (taxa_input / 100)

    taxa_diaria = (1 + taxa_anual_real / 100) ** (1 / dias_ano) - 1
    montante_bruto = valor_investido * (1 + taxa_diaria) ** prazo_dias
    rendimento_bruto = montante_bruto - valor_investido

    rendimento_apos_iof = rendimento_bruto
    imposto_iof = 0.0
    if prazo_dias < 30:
        iof_tab = [0.96,0.93,0.90,0.86,0.83,0.80,0.76,0.73,0.70,0.66,0.63,0.60,0.56,0.53,0.50,
                   0.46,0.43,0.40,0.36,0.33,0.30,0.26,0.23,0.20,0.16,0.13,0.10,0.06,0.03,0.00]
        imposto_iof = rendimento_bruto * iof_tab[prazo_dias - 1]
        rendimento_apos_iof = rendimento_bruto - imposto_iof

    aliquota_ir = 22.5 if prazo_dias <= 180 else 20.0 if prazo_dias <= 360 else 17.5 if prazo_dias <= 720 else 15.0
    ir = rendimento_apos_iof * (aliquota_ir / 100)

    montante_liquido = valor_investido + rendimento_apos_iof - ir
    rendimento_liquido = montante_liquido - valor_investido

    return {
        'Valor Investido': round(valor_investido, 2),
        'Montante Bruto': round(montante_bruto, 2),
        'Rendimento Bruto': round(rendimento_bruto, 2),
        'Imposto IOF': round(imposto_iof, 2),
        'Alíquota IR': aliquota_ir,
        'Imposto IR': round(ir, 2),
        'Total Impostos': round(imposto_iof + ir, 2),
        'Montante Líquido': round(montante_liquido, 2),
        'Rendimento Líquido': round(rendimento_liquido, 2),
        'Prazo Dias': prazo_dias,
    }, None

# ===================== SESSION STATE =====================
if 'papeis' not in st.session_state:
    st.session_state.papeis = []
if 'cdi_benchmark_geral' not in st.session_state:
    st.session_state.cdi_benchmark_geral = 14.90

# ===================== CABEÇALHO =====================
st.markdown(f'<img src="{URL_LOGO_WHITE}" style="max-width:400px; display:block; margin:auto;">', unsafe_allow_html=True)
st.markdown("<h3 style='text-align:center;'>Calculadora de Simulação de Papéis Secundários</h3>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;'>Adicione e gerencie os papéis diretamente na tabela abaixo.</p>", unsafe_allow_html=True)
st.markdown("---")

# ===================== DADOS GERAIS =====================
st.subheader("Dados Gerais da Simulação", divider='gray')
c1, c2 = st.columns(2)
with c1:
    nome_cliente = st.text_input("Nome do Cliente", "João Silva")
    data_simulacao = st.date_input("Data da Simulação", datetime.date.today(), format="DD/MM/YYYY")
with c2:
    nome_assessor = st.text_input("Nome do Assessor", "Seu Nome")
    data_aplicacao = st.date_input("Data de Aplicação/Compra", datetime.date.today(), format="DD/MM/YYYY")

st.session_state.cdi_benchmark_geral = st.number_input("Taxa CDI Anual (Benchmark) (%)", value=st.session_state.cdi_benchmark_geral, step=0.05)

st.markdown("---")

# ===================== TABELA DE PAPÉIS — 100% CORRIGIDA =====================
st.subheader("Papéis Incluídos para Simulação", divider='gray')

# Cria DataFrame com tipos corretos
if st.session_state.papeis:
    df_papeis = pd.DataFrame(st.session_state.papeis)
    # Converte tipos
    df_papeis['Valor'] = pd.to_numeric(df_papeis['Valor'], errors='coerce')
    df_papeis['Taxa'] = pd.to_numeric(df_papeis['Taxa'], errors='coerce')
    df_papeis['Data Vencimento'] = pd.to_datetime(df_papeis['Data Vencimento'], errors='coerce')
else:
    # DataFrame vazio com tipos corretos
    df_papeis = pd.DataFrame({
        'Emissor': pd.Series(dtype='str'),
        'Ticker': pd.Series(dtype='str'),
        'Valor': pd.Series(dtype='float'),
        'Tipo': pd.Series(dtype='str'),
        'Taxa': pd.Series(dtype='float'),
        'Data Vencimento': pd.Series(dtype='datetime64[ns]')
    })

# Editor
edited_df = st.data_editor(
    df_papeis.rename(columns={
        'Valor': 'Valor Investido (R$)',
        'Tipo': 'Tipo de Taxa',
        'Taxa': 'Taxa (%)',
        'Data Vencimento': 'Vencimento'
    })[['Emissor', 'Ticker', 'Valor Investido (R$)', 'Tipo de Taxa', 'Taxa (%)', 'Vencimento']],
    num_rows="dynamic",
    hide_index=True,
    column_config={
        "Valor Investido (R$)": st.column_config.NumberColumn(format="%.2f", min_value=0.01),
        "Tipo de Taxa": st.column_config.SelectboxColumn(options=["Pré-fixado", "Pós-fixado (% do CDI)"], required=True),
        "Taxa (%)": st.column_config.NumberColumn(format="%.2f", min_value=0.01),
        "Vencimento": st.column_config.DateColumn(format="DD/MM/YYYY", min_value=data_aplicacao + datetime.timedelta(days=1))
    },
    key="editor_papeis"
)

# Atualiza session state
df_nova = edited_df.rename(columns={
    'Valor Investido (R$)': 'Valor',
    'Tipo de Taxa': 'Tipo',
    'Taxa (%)': 'Taxa',
    'Vencimento': 'Data Vencimento'
})

# Remove linhas inválidas
df_valida = df_nova.dropna(subset=['Valor', 'Taxa', 'Data Vencimento'])
df_valida = df_valida[(df_valida['Valor'] > 0) & (df_valida['Taxa'] > 0)]

st.session_state.papeis = df_valida.to_dict('records')

if st.button("Limpar Todos os Papéis", type="primary"):
    st.session_state.papeis = []
    st.rerun()

# ===================== RESTO DO CÓDIGO (cálculo + PDF) =====================
# (mantive 100% igual ao seu original, só com a tabela corrigida acima)

if not st.session_state.papeis:
    st.info("Adicione pelo menos um papel válido.")
    st.stop()

resultados = []
for p in st.session_state.papeis:
    res, erro = calcular_papel(p, data_aplicacao, st.session_state.cdi_benchmark_geral)
    if res:
        resultados.append(res)

total_investido = sum(r['Valor Investido'] for r in resultados)
total_bruto = sum(r['Montante Bruto'] for r in resultados)
total_impostos = sum(r['Total Impostos'] for r in resultados)
total_liquido = sum(r['Montante Líquido'] for r in resultados)
rendimento_liquido_total = total_liquido - total_investido
rentabilidade = (rendimento_liquido_total / total_investido) * 100 if total_investido > 0 else 0

st.markdown("---")
st.subheader("Resultado Consolidado")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Investido", brl(total_investido))
c2.metric("Montante Bruto", brl(total_bruto))
c3.metric("Impostos", brl(total_impostos))
c4.metric("Montante Líquido", brl(total_liquido))
st.markdown(f"**Rendimento Líquido:** {brl(rendimento_liquido_total)}")
st.markdown(f"**Rentabilidade:** {rentabilidade:.2f}%")

# ===================== PDF (seu original) =====================
def criar_pdf():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = [carregar_logo(), Spacer(1, 15*mm)]
    story.append(Paragraph(f"<b>Simulação para {nome_cliente}</b>", ParagraphStyle(name='Title', fontSize=20, alignment=1)))
    story.append(Paragraph(f"Total Líquido: {brl(total_liquido)}", ParagraphStyle(name='Normal', fontSize=14)))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

if st.button("BAIXAR PROPOSTA", type="primary"):
    with.forms st.spinner("Gerando PDF..."):
        pdf = criar_pdf()
        b64 = base64.b64encode(pdf).decode()
        href = f'<a href="data:application/pdf;base64,{b64}" download="proposta.pdf"><h3>BAIXAR PDF</h3></a>'
        st.markdown(href, unsafe_allow_html=True)
        st.success("PDF gerado!")

st.markdown(f"<p style='text-align:center;'>Simulação elaborada por <b>{nome_assessor}</b></p>", unsafe_allow_html=True)
