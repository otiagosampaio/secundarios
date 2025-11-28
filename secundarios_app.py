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
import re
import pandas as pd
import numpy as np

# ===================== CONFIGURAÇÃO DE CORES (TEMA CLARO PADRÃO) =====================
URL_LOGO_WHITE = "https://ik.imagekit.io/aufhkvnry/logo-traders__bg-white.png" # Altere para o seu logo
TEXTO_PRINCIPAL_ST = "#222222"
VERDE_DESTAQUE = '#2E8B57'
AZUL_TABELA_PDF = colors.HexColor("#864df4")
COR_PRIMARIA_FORM = '#6B48FF' # Cor para o botão de adicionar
TAXA_CDI_MERCADO = 14.90 # Valor de CDI atual

# ===================== FUNÇÕES AUXILIARES =====================

def carregar_logo():
    url = URL_LOGO_WHITE
    response = requests.get(url)
    img_pil = PILImage.open(PIOBytesIO(response.content))
    largura, altura = img_pil.size
    proporcao = altura / largura
    largura_desejada = 200
    altura_calculada = largura_desejada * proporcao
    return Image(PIOBytesIO(response.content), width=largura_desejada, height=altura_calculada)

def formatar_moeda_input(valor_str):
    valor_limpo = valor_str.replace('R$', '').replace('.', '').replace(',', '.', 1)
    
    try:
        valor_float = float(valor_limpo)
        return f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return "0,00"

def desformatar_moeda(valor_formatado):
    valor_float_str = valor_formatado.replace('R$', '').replace('.', '').replace(',', '.')
    try:
        return float(valor_float_str)
    except ValueError:
        return 0.0

brl = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
brl_pdf = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") # Alias para PDF

# ===================== CÁLCULO PARA UM ÚNICO PAPEL =====================

def calcular_papel(papel, data_aplicacao, taxa_cdi_benchmark):
    valor_investido = papel['Valor']
    data_vencimento = papel['Data Vencimento']
    tipo = papel['Tipo']
    taxa_input = papel['Taxa']

    if isinstance(data_vencimento, pd.Timestamp):
        data_vencimento = data_vencimento.date()

    prazo_dias = (data_vencimento - data_aplicacao).days
    
    if prazo_dias <= 0:
        return None, f"Data de resgate inválida para {papel['Ticker']}"

    dias_ano = 360 
    taxa_anual_real = taxa_input

    if tipo == "Pós-fixado (% do CDI)":
        taxa_anual_real = taxa_cdi_benchmark * (taxa_input / 100)
    
    taxa_diaria = (1 + taxa_anual_real/100)**(1/dias_ano) - 1

    montante_bruto = valor_investido * (1 + taxa_diaria)**prazo_dias
    rendimento_bruto = montante_bruto - valor_investido

    rendimento_apos_iof = rendimento_bruto
    imposto_iof = 0
    if prazo_dias < 30:
        iof_tab = [0.96,0.93,0.90,0.86,0.83,0.80,0.76,0.73,0.70,0.66,0.63,0.60,0.56,0.53,0.50,
                   0.46,0.43,0.40,0.36,0.33,0.30,0.26,0.23,0.20,0.16,0.13,0.10,0.06,0.03,0.00]
        idx = min(prazo_dias, 30) - 1
        aliquota_iof = iof_tab[idx]
        imposto_iof = rendimento_bruto * aliquota_iof
        rendimento_apos_iof = rendimento_bruto - imposto_iof

    aliquota_ir = 22.5 if prazo_dias <= 180 else 20.0 if prazo_dias <= 360 else 17.5 if prazo_dias <= 720 else 15.0
    imposto_ir = rendimento_apos_iof * (aliquota_ir/100)
    
    montante_liquido = valor_investido + rendimento_apos_iof - imposto_ir
    rendimento_liquido = montante_liquido - valor_investido
    
    total_impostos = imposto_iof + imposto_ir

    resultado = {
        'Valor Investido': valor_investido,
        'Montante Bruto': montante_bruto,
        'Rendimento Bruto': rendimento_bruto,
        'Imposto IOF': imposto_iof,
        'Alíquota IR': aliquota_ir,
        'Imposto IR': imposto_ir,
        'Total Impostos': total_impostos,
        'Montante Líquido': montante_liquido,
        'Rendimento Líquido': rendimento_liquido,
        'Prazo Dias': prazo_dias,
        'Taxa Anual Real': taxa_anual_real,
    }

    return resultado, None

# ===================== CONFIGURAÇÃO INICIAL E SESSION STATE =====================
st.set_page_config(page_title="Traders Secundários - Calculadora", layout="centered")

# --- Inicialização Padrão ---
if 'papeis' not in st.session_state:
    st.session_state['papeis'] = []
if 'cdi_benchmark_geral' not in st.session_state:
    st.session_state['cdi_benchmark_geral'] = TAXA_CDI_MERCADO
    
# --- Inicialização dos campos do FORMULÁRIO ---
if 'emissor_sec' not in st.session_state:
    st.session_state['emissor_sec'] = "Banco Alfa S.A."
if 'ticker_sec' not in st.session_state:
    st.session_state['ticker_sec'] = "CDB1234"
if 'tipo_cdb_sec' not in st.session_state:
    st.session_state['tipo_cdb_sec'] = "Pré-fixado"
if 'taxa_sec' not in st.session_state:
    st.session_state['taxa_sec'] = 17.00
if 'vencimento_sec' not in st.session_state:
    st.session_state['vencimento_sec'] = datetime.date.today() + relativedelta(months=+12)
if 'valor_bruto_input_sec' not in st.session_state:
    st.session_state['valor_bruto_input_sec'] = "500.000,00" # Valor base para o formulário de inclusão


# ===================== LOGO + TÍTULO (Streamlit Display) =====================
st.markdown(
    f"""<div style="text-align: center; margin: 10px 0;">
        <img src="{URL_LOGO_WHITE}" width="200"> 
    </div>""",
    unsafe_allow_html=True
)
st.markdown(f"<h3 style='text-align: center; color: {TEXTO_PRINCIPAL_ST};'>Calculadora de Simulação de Papéis Secundários</h3>", unsafe_allow_html=True) 
st.markdown(f"<p style='text-align: center; font-size: 15px; margin-bottom: 20px;'>Adicione os papéis e simule o resultado consolidado para o cliente.</p>", unsafe_allow_html=True) 
st.markdown("---")

# ===================== DADOS GERAIS DA SIMULAÇÃO =====================
st.subheader("Dados Gerais da Simulação", divider='gray') 
c1, c2 = st.columns(2) 

with c1:
    nome_cliente = st.text_input("Nome do Cliente", "João Silva")
    data_simulacao = st.date_input("Data da Simulação", datetime.date.today(), format="DD/MM/YYYY")

with c2:
    nome_assessor = st.text_input("Nome do Assessor", "Seu Nome")
    data_aplicacao = st.date_input("Data de Aplicação/Compra", datetime.date.today(), format="DD/MM/YYYY")

st.number_input("Taxa CDI Anual (Benchmark) (%)", value=st.session_state['cdi_benchmark_geral'], step=0.05, key='cdi_benchmark_geral') 
    
st.markdown("---")

# ===================== ADICIONAR NOVO PAPEL (FORMULÁRIO) =====================

st.subheader("Inclusão de Novo Papel", divider='gray')

def adicionar_papel():
    valor_investido_float = desformatar_moeda(formatar_moeda_input(st.session_state.valor_bruto_input_sec))

    if valor_investido_float <= 0:
        st.error("O valor investido deve ser maior que zero.")
        return
    
    if st.session_state.vencimento_sec <= data_aplicacao:
        st.error("A Data de Vencimento deve ser posterior à Data de Aplicação.")
        return

    novo_papel = {
        'Emissor': st.session_state.emissor_sec,
        'Ticker': st.session_state.ticker_sec,
        'Valor': valor_investido_float,
        'Tipo': st.session_state.tipo_cdb_sec,
        'Taxa': st.session_state.taxa_sec,
        'Data Vencimento': st.session_state.vencimento_sec,
    }
    
    st.session_state.papeis.append(novo_papel)
    
    # ⭐️ AJUSTE DE LIMPEZA: Limpar os campos do formulário redefinindo as chaves
    st.session_state.emissor_sec = "Banco Alfa S.A."
    st.session_state.ticker_sec = "CDB1234"
    st.session_state.tipo_cdb_sec = "Pré-fixado"
    st.session_state.taxa_sec = 17.00
    st.session_state.vencimento_sec = datetime.date.today() + relativedelta(months=+12)
    st.session_state.valor_bruto_input_sec = "0,00" # Limpa o campo de valor

with st.form("form_papel", clear_on_submit=False):
    col_e1, col_e2 = st.columns(2) 

    with col_e1:
        # Usa o session state para que o campo possa ser limpo
        st.text_input("Emissor", key="emissor_sec") 
        st.text_input("Ticker/Código", key="ticker_sec") 
        st.date_input("Data de Vencimento", key="vencimento_sec", format="DD/MM/YYYY")
            
    with col_e2:
        tipo_cdb_sec = st.selectbox("Tipo de Taxa", ["Pré-fixado", "Pós-fixado (% do CDI)"], key="tipo_cdb_sec")
        
        if tipo_cdb_sec == "Pós-fixado (% do CDI)":
            st.number_input("Percentual do CDI (%)", step=1.0, key="taxa_sec")
        else:
            st.number_input("Taxa Pré-fixada anual (%)", step=0.05, key="taxa_sec")
        
        # ⭐️ AJUSTE DE VALOR: O input é controlado diretamente pela session state (valor_bruto_input_sec)
        st.text_input(
            label="Valor investido neste papel", 
            placeholder="Digite o valor",
            key="valor_bruto_input_sec"
        )
        
    # ⭐️ AJUSTE DE VALOR: O valor é lido diretamente do session state do input (real-time feedback)
    valor_formatado_em_tempo_real = formatar_moeda_input(st.session_state.valor_bruto_input_sec)
    st.markdown(f"<p style='color: {TEXTO_PRINCIPAL_ST}; margin-top: 10px;'>Valor a ser adicionado: <b>R$ {valor_formatado_em_tempo_real}</b></p>", unsafe_allow_html=True)

    st.form_submit_button("ADICIONAR PAPEL À SIMULAÇÃO", on_click=adicionar_papel, type="secondary", use_container_width=True)

st.markdown("---")

# ===================== TABELA DE PAPÉIS ADICIONADOS (Restante do Código Omitido) =====================

# ... (O restante do código, incluindo a tabela, cálculos consolidados, gráfico e PDF, permanece o mesmo) ...

# ----------------------------------------------------
# Código resumido abaixo para focar apenas nas alterações, o código completo deve ser usado na aplicação.
# ----------------------------------------------------

# (Coloque o código completo da resposta anterior aqui, mas com as funções de adicionar_papel e a seção do form atualizadas)
