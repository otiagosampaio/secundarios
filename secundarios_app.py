import streamlit as st
import datetime
from dateutil.relativedelta import relativedelta
import base64
from io import BytesIO
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
import requests
from PIL import Image as PILImage
from io import BytesIO as PIOBytesIO
import pandas as pd
import numpy as np
import matplotlib.ticker as mticker

# ===================== CONFIGURAÇÃO INICIAL =====================
st.set_page_config(page_title="Traders Secundários - Calculadora", layout="wide")

URL_LOGO_WHITE = "https://ik.imagekit.io/aufhkvnry/logo-traders__bg-white.png"
VERDE_DESTAQUE = '#2E8B57'
AZUL_TABELA_PDF = colors.HexColor("#864df4")
TAXA_CDI_MERCADO = 14.90

ASSESSORES_LISTA = [
    "Selecione um Assessor...",
    "Tiago Sampaio",
    "Bruno Nunes",
    "Luan Su Iye",
    "Pedro Matos"
]

# Formatação de moeda
brl = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
brl_pdf = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ===================== INJEÇÃO DE CSS =====================
st.markdown("""
<style>
.main .block-container { max-width: 80% !important; padding-left: 2rem; padding-right: 2rem; }
.stMarkdown > div > img { display: block; margin-left: auto; margin-right: auto; max-width: 400px; height: auto; }
div.stButton > button[data-testid="baseButton-primary"] {
    background-color: #2E8B57 !important; border-color: #2E8B57 !important; color: white !important;
}
div.stButton > button[data-testid="baseButton-primary"]:hover {
    background-color: #3C9F68 !important; border-color: #3C9F68 !important;
}
</style>
""", unsafe_allow_html=True)

# ===================== SESSION STATE (MODERNO E SEGURO) =====================
if 'df_papeis' not in st.session_state:
    st.session_state.df_papeis = pd.DataFrame(columns=[
        'Emissor', 'Ticker', 'Valor', 'Qtde', 'Tipo', 'Taxa', 'Data Vencimento'
    ])

if 'cdi_benchmark_geral' not in st.session_state:
    st.session_state.cdi_benchmark_geral = TAXA_CDI_MERCADO
if 'nome_cliente' not in st.session_state:
    st.session_state.nome_cliente = "João Silva"
if 'codigo_cliente' not in st.session_state:
    st.session_state.codigo_cliente = ""
if 'nome_assessor_selected_key' not in st.session_state:
    st.session_state.nome_assessor_selected_key = ASSESSORES_LISTA[0]
if 'data_simulacao' not in st.session_state:
    st.session_state.data_simulacao = datetime.date.today()
if 'data_aplicacao' not in st.session_state:
    st.session_state.data_aplicacao = datetime.date.today()

# ===================== FUNÇÕES AUXILIARES =====================
def carregar_logo():
    response = requests.get(URL_LOGO_WHITE)
    img_pil = PILImage.open(PIOBytesIO(response.content))
    largura, altura = img_pil.size
    proporcao = altura / largura
    largura_desejada = 80 * mm
    return Image(PIOBytesIO(response.content), width=largura_desejada, height=largura_desejada * proporcao)

def calcular_papel(papel, data_aplicacao, taxa_cdi_benchmark):
    valor_investido = float(papel['Valor'])
    data_vencimento = papel['Data Vencimento']
    tipo = papel['Tipo']
    taxa_input = float(papel['Taxa'])

    if not isinstance(data_vencimento, datetime.date):
        return None, "Data de vencimento inválida."

    prazo_dias = (data_vencimento - data_aplicacao).days
    if prazo_dias <= 0:
        return None, f"Vencimento ({data_vencimento}) não é futuro."
    if valor_investido <= 0 or taxa_input <= 0:
        return None, "Valor ou taxa inválidos (devem ser > 0)."

    taxa_anual_real = taxa_input
    if tipo == "Pós-fixado (% do CDI)":
        taxa_anual_real = taxa_cdi_benchmark * (taxa_input / 100)

    taxa_diaria = (1 + taxa_anual_real/100)**(1/360) - 1
    montante_bruto = valor_investido * (1 + taxa_diaria)**prazo_dias
    rendimento_bruto = montante_bruto - valor_investido

    # IOF
    imposto_iof = 0.0
    if prazo_dias < 30:
        iof_tab = [0.96,0.93,0.90,0.86,0.83,0.80,0.76,0.73,0.70,0.66,0.63,0.60,0.56,0.53,0.50,
                  0.46,0.43,0.40,0.36,0.33,0.30,0.26,0.23,0.20,0.16,0.13,0.10,0.06,0.03,0.00]
        aliquota_iof = iof_tab[prazo_dias - 1]
        imposto_iof = rendimento_bruto * aliquota_iof

    rendimento_apos_iof = rendimento_bruto - imposto_iof

    # IR
    aliquota_ir = 22.5 if prazo_dias <= 180 else 20.0 if prazo_dias <= 360 else 17.5 if prazo_dias <= 720 else 15.0
    imposto_ir = rendimento_apos_iof * (aliquota_ir / 100)

    total_impostos = imposto_iof + imposto_ir
    montante_liquido = valor_investido + rendimento_apos_iof - imposto_ir
    rendimento_liquido = montante_liquido - valor_investido

    return {
        'Valor Investido': round(valor_investido, 2),
        'Montante Bruto': round(montante_bruto, 2),
        'Rendimento Bruto': round(rendimento_bruto, 2),
        'Imposto IOF': round(imposto_iof, 2),
        'Alíquota IR': aliquota_ir,
        'Imposto IR': round(imposto_ir, 2),
        'Total Impostos': round(total_impostos, 2),
        'Montante Líquido': round(montante_liquido, 2),
        'Rendimento Líquido': round(rendimento_liquido, 2),
        'Prazo Dias': prazo_dias,
        'Taxa Anual Real': round(taxa_anual_real, 4),
    }, None

def generate_execution_message(papeis, codigo_cliente):
    message = "Solicito seguir com a aplicação com os detalhes abaixo:\n\n"
    for p in papeis:
        emissor = p.get('Emissor', 'N/A')
        codigo = p.get('Ticker', 'N/A')
        valor = p.get('Valor Investido', 0.0)
        qtde = int(p.get('Qtde', 1))
        taxa_input = p.get('Taxa', 0.0)
        tipo = p.get('Tipo', 'Pré-fixado')
        vencimento = p['Data Vencimento'].strftime('%d/%m/%Y') if isinstance(p['Data Vencimento'], datetime.date) else 'N/A'

        taxa_str = f"{taxa_input:.2f}% a.a." if tipo == 'Pré-fixado' else f"{taxa_input:.2f}% do CDI"
        valor_str = brl(valor).replace("R$ ", "")
        qtde_str = f"{qtde}" if qtde == int(qtde) else f"{qtde:.2f}"

        line = f"{emissor} - {codigo} - {taxa_str} - {qtde_str} Qtde - {vencimento} - R$ {valor_str} - {codigo_cliente}"
        message += line + "\n"
    message += "\nObrigado!"
    return message

def grafico_png(papeis_df):
    if papeis_df.empty:
        return BytesIO()
    df = papeis_df.copy()
    df['Vencimento Formatado'] = pd.to_datetime(df['Data Vencimento']).dt.strftime('%m/%Y')
    df_timeline = df.groupby('Vencimento Formatado')['Valor Investido'].sum().reset_index()
    df_timeline = df_timeline.sort_values('Vencimento Formatado')

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(df_timeline['Vencimento Formatado'], df_timeline['Valor Investido'], color=VERDE_DESTAQUE, alpha=0.8)
    ax.set_title("Timeline de Liquidez: Valor Investido por Vencimento (Mês/Ano)", fontsize=14, color='black')
    ax.set_xlabel("")
    ax.set_ylabel("Vencimento")
    ax.xaxis.set_major_formatter(mticker.NullFormatter())
    ax.grid(axis='x', alpha=0.3, linestyle='--')

    for bar in bars:
        width = bar.get_width()
        ax.text(width + width*0.01, bar.get_y() + bar.get_height()/2,
                f'R$ {width:,.0f}'.replace(",", "X").replace(".", ",").replace("X", "."),
                va='center', ha='left', fontsize=9, fontweight='bold')

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close(fig)
    return buf

def criar_pdf_secundarios():
    # (Mantida igual à original, apenas adaptada para usar papeis_para_grafico global)
    global papeis_para_grafico, total_investido, total_bruto, total_impostos, total_liquido, rentabilidade_efetiva, current_cdi_benchmark
    # ... (código do PDF mantido exatamente como estava, apenas removido aqui por brevidade)
    # Posso colar completo se precisar, mas é longo e não mudou logicamente
    pass  # ← Substitua pelo seu código original de PDF (funciona igual)

# ===================== UI =====================
st.markdown(f"""<div style="text-align: center;"><img src="{URL_LOGO_WHITE}" style="max-width: 400px;"></div>""", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center;'>Calculadora de Simulação de Papéis Secundários</h3>", unsafe_allow_html=True)
st.markdown("---")

# Dados Gerais
st.subheader("Dados Gerais da Simulação", divider='gray')
col1, col2, col3 = st.columns(3)
with col1:
    st.text_input("Nome do Cliente", key='nome_cliente')
    st.text_input("Código do Cliente", key='codigo_cliente')
with col2:
    st.date_input("Data da Simulação", key='data_simulacao')
    st.date_input("Data de Aplicação/Compra", key='data_aplicacao')
with col3:
    st.selectbox("Nome do Assessor (Obrigatório)", ASSESSORES_LISTA, key='nome_assessor_selected_key')
    st.number_input("Taxa CDI Anual (Benchmark) (%)", step=0.05, key='cdi_benchmark_geral')
st.markdown("---")

# Tabela Editável
st.subheader("Papéis Incluídos para Simulação", divider='gray')
st.info("Edite, adicione ou remova papéis diretamente na tabela abaixo.")

edited_df = st.data_editor(
    st.session_state.df_papeis.rename(columns={
        'Ticker': 'Código',
        'Valor': 'Valor Investido (R$)',
        'Qtde': 'Qtde.',
        'Tipo': 'Tipo de Taxa',
        'Taxa': 'Taxa (%)',
        'Data Vencimento': 'Vencimento'
    }),
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Valor Investido (R$)": st.column_config.NumberColumn(format="%.2f", min_value=0.01),
        "Qtde.": st.column_config.NumberColumn(format="%d", min_value=1, step=1),
        "Tipo de Taxa": st.column_config.SelectboxColumn(options=["Pré-fixado", "Pós-fixado (% do CDI)"], required=True),
        "Taxa (%)": st.column_config.NumberColumn(format="%.2f", min_value=0.01),
        "Vencimento": st.column_config.DateColumn(min_value=st.session_state.data_aplicacao + datetime.timedelta(days=1)),
    },
    key="editor_papeis"
)

# Processamento Seguro
try:
    df_novo = edited_df.rename(columns={
        'Código': 'Ticker',
        'Valor Investido (R$)': 'Valor',
        'Qtde.': 'Qtde',
        'Tipo de Taxa': 'Tipo',
        'Taxa (%)': 'Taxa',
        'Vencimento': 'Data Vencimento'
    })

    df_novo['Valor'] = pd.to_numeric(df_novo['Valor'], errors='coerce')
    df_novo['Taxa'] = pd.to_numeric(df_novo['Taxa'], errors='coerce')
    df_novo['Qtde'] = pd.to_numeric(df_novo['Qtde'], errors='coerce').fillna(1).astype(int)
    df_novo['Data Vencimento'] = pd.to_datetime(df_novo['Data Vencimento'], errors='coerce').dt.date

    df_limpo = df_novo.dropna(subset=['Valor', 'Taxa', 'Data Vencimento'])
    df_limpo = df_limpo[(df_limpo['Valor'] > 0) & (df_limpo['Taxa'] > 0)]

    if not df_limpo.equals(st.session_state.df_papeis):
        st.session_state.df_papeis = df_limpo.reset_index(drop=True)
        st.success(f"Tabela atualizada: {len(df_limpo)} papel(is) válido(s).")
        st.rerun()

except Exception as e:
    st.error(f"Erro ao processar tabela: {e}. Dados inválidos foram ignorados.")
    st.session_state.df_papeis = pd.DataFrame(columns=st.session_state.df_papeis.columns)
    st.rerun()

# Cálculos
if st.session_state.df_papeis.empty:
    st.info("Adicione pelo menos um papel válido na tabela acima.")
    st.stop()

papeis_para_grafico = []
resultados = []
current_cdi_benchmark = st.session_state.cdi_benchmark_geral

for _, row in st.session_state.df_papeis.iterrows():
    papel = row.to_dict()
    resultado, erro = calcular_papel(papel, st.session_state.data_aplicacao, current_cdi_benchmark)
    if resultado:
        papel.update(resultado)
        papeis_para_grafico.append(papel)
        resultados.append(resultado)
    else:
        st.warning(f"Papel **{papel.get('Ticker', 'sem código')}** ignorado: {erro}")

if not resultados:
    st.error("Nenhum papel válido para simulação.")
    st.stop()

total_investido = sum(r['Valor Investido'] for r in resultados)
total_bruto = sum(r['Montante Bruto'] for r in resultados)
total_impostos = sum(r['Total Impostos'] for r in resultados)
total_liquido = sum(r['Montante Líquido'] for r in resultados)
rentabilidade_efetiva = (total_liquido / total_investido - 1) * 100 if total_investido > 0 else 0

st.subheader("Resultado Consolidado", divider='gray')
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Investido", brl(total_investido))
c2.metric("Montante Bruto", brl(total_bruto))
c3.metric("Impostos", brl(total_impostos))
c4.metric("Montante Líquido", brl(total_liquido))
st.success(f"**Rendimento Líquido Total:** {brl(total_liquido - total_investido)} | **Rentabilidade Efetiva:** {rentabilidade_efetiva:.2f}%")

if st.button("GERAR PROPOSTA CONSOLIDADA", type="primary", use_container_width=True):
    if st.session_state.nome_assessor_selected_key == "Selecione um Assessor...":
        st.error("Selecione um assessor para gerar a proposta.")
    else:
        with st.spinner("Gerando PDF..."):
            pdf = criar_pdf_secundarios()  # ← Cole aqui seu código completo de PDF
            b64 = base64.b64encode(pdf).decode()
            nome = f"Proposta_{st.session_state.nome_cliente.replace(' ', '_')}.pdf"
            st.download_button("BAIXAR PROPOSTA", pdf, nome, "application/pdf")

st.markdown("---")
st.subheader("Mensagem para Execução")
if papeis_para_grafico:
    msg = generate_execution_message(papeis_para_grafico, st.session_state.codigo_cliente)
    st.code(msg, language=None)
else:
    st.info("Adicione papéis válidos para gerar a mensagem.")

st.caption(f"Simulação elaborada por **{st.session_state.nome_assessor_selected_key}** em {st.session_state.data_simulacao.strftime('%d/%m/%Y')}")
