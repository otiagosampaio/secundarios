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
COR_PRIMARIA_FORM = '#6B48FF' 
TAXA_CDI_MERCADO = 14.90 

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
    """Formata uma string de entrada monetária para o padrão de exibição brasileiro (000.000,00)."""
    if valor_str is None or valor_str == "":
        return "0,00"
        
    valor_limpo = valor_str.replace('R$', '').replace('.', '').replace(',', '.', 1)
    
    try:
        valor_float = float(valor_limpo)
        return f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return "0,00"

def desformatar_moeda(valor_formatado):
    """Converte o formato brasileiro (ponto de milhar, vírgula decimal) para float."""
    if valor_formatado is None or valor_formatado == "":
        return 0.0
        
    valor_float_str = valor_formatado.replace('R$', '').replace('.', '').replace(',', '.')
    try:
        return float(valor_float_str)
    except ValueError:
        return 0.0

brl = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
brl_pdf = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") 

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
    
# --- Inicialização para campos vazios ---
if 'emissor_sec' not in st.session_state:
    st.session_state['emissor_sec'] = ""
if 'ticker_sec' not in st.session_state:
    st.session_state['ticker_sec'] = ""
if 'tipo_cdb_sec' not in st.session_state:
    st.session_state['tipo_cdb_sec'] = "Pré-fixado" 
if 'taxa_sec' not in st.session_state:
    st.session_state['taxa_sec'] = 0.0 
if 'vencimento_sec' not in st.session_state:
    st.session_state['vencimento_sec'] = datetime.date.today() + relativedelta(months=+12) 
if 'valor_bruto_input_sec' not in st.session_state:
    st.session_state['valor_bruto_input_sec'] = "" 


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

# ⭐️ AJUSTE: Campos de texto geral vazios
with c1:
    nome_cliente = st.text_input("Nome do Cliente", "")
    data_simulacao = st.date_input("Data da Simulação", datetime.date.today(), format="DD/MM/YYYY")

with c2:
    nome_assessor = st.text_input("Nome do Assessor", "")
    data_aplicacao = st.date_input("Data de Aplicação/Compra", datetime.date.today(), format="DD/MM/YYYY")

st.number_input("Taxa CDI Anual (Benchmark) (%)", value=st.session_state['cdi_benchmark_geral'], step=0.05, key='cdi_benchmark_geral') 
    
st.markdown("---")

# ===================== ADICIONAR NOVO PAPEL (FORMULÁRIO) =====================

st.subheader("Inclusão de Novo Papel", divider='gray')

def adicionar_papel():
    # Esta função agora só adiciona o papel e limpa o estado, sem forçar o rerun
    valor_investido_float = desformatar_moeda(formatar_moeda_input(st.session_state.valor_bruto_input_sec))

    if valor_investido_float <= 0:
        st.error("O valor investido deve ser maior que zero.")
        return False # Indica que a adição falhou
    
    if st.session_state.vencimento_sec <= data_aplicacao:
        st.error("A Data de Vencimento deve ser posterior à Data de Aplicação.")
        return False # Indica que a adição falhou

    novo_papel = {
        'Emissor': st.session_state.emissor_sec,
        'Ticker': st.session_state.ticker_sec,
        'Valor': valor_investido_float,
        'Tipo': st.session_state.tipo_cdb_sec,
        'Taxa': st.session_state.taxa_sec,
        'Data Vencimento': st.session_state.vencimento_sec,
    }
    
    st.session_state.papeis.append(novo_papel)
    
    # Limpar completamente os campos do formulário
    st.session_state.emissor_sec = "" 
    st.session_state.ticker_sec = "" 
    st.session_state.tipo_cdb_sec = "Pré-fixado" 
    st.session_state.taxa_sec = 0.0 
    st.session_state.vencimento_sec = datetime.date.today() + relativedelta(months=+12) 
    st.session_state.valor_bruto_input_sec = "" 
    
    return True # Indica que a adição foi bem-sucedida

# O form é submetido, e a variável 'submitted' captura o clique.
with st.form("form_papel", clear_on_submit=False):
    col_e1, col_e2 = st.columns(2) 

    with col_e1:
        st.text_input("Emissor", key="emissor_sec") 
        st.text_input("Ticker/Código", key="ticker_sec") 
        st.date_input("Data de Vencimento", key="vencimento_sec", format="DD/MM/YYYY")
            
    with col_e2:
        tipo_cdb_sec = st.selectbox("Tipo de Taxa", ["Pré-fixado", "Pós-fixado (% do CDI)"], key="tipo_cdb_sec")
        
        if st.session_state.tipo_cdb_sec == "Pós-fixado (% do CDI)":
            st.number_input("Percentual do CDI (%)", step=1.0, key="taxa_sec", min_value=0.0)
        else:
            st.number_input("Taxa Pré-fixada anual (%)", step=0.05, key="taxa_sec", min_value=0.0)
        
        st.text_input(
            label="Valor investido neste papel", 
            placeholder="Ex: 100000,00",
            key="valor_bruto_input_sec"
        )
        
    valor_formatado_em_tempo_real = formatar_moeda_input(st.session_state.valor_bruto_input_sec)
    st.markdown(f"<p style='color: {TEXTO_PRINCIPAL_ST}; margin-top: 10px;'>Valor a ser adicionado: <b>R$ {valor_formatado_em_tempo_real}</b></p>", unsafe_allow_html=True)

    # ⭐️ AJUSTE CRÍTICO: Remoção do on_click
    submitted = st.form_submit_button("ADICIONAR PAPEL À SIMULAÇÃO", type="secondary", use_container_width=True)

# ⭐️ AJUSTE CRÍTICO: Lógica de submissão e Rerun movida para fora do callback
if submitted:
    if adicionar_papel():
        st.rerun() # O RERUN é executado no fluxo principal após a adição bem-sucedida

st.markdown("---")

# ===================== TABELA DE PAPÉIS ADICIONADOS =====================

if not st.session_state.papeis:
    st.info("Nenhum papel adicionado. Use o formulário acima para começar a simulação.")
    st.stop()
    
st.subheader("Papéis Incluídos para Simulação", divider='gray')

df_papeis = pd.DataFrame(st.session_state.papeis)
df_papeis['Data Vencimento'] = pd.to_datetime(df_papeis['Data Vencimento'])

df_papeis['Taxa/CDI'] = df_papeis.apply(
    lambda row: f"{row['Taxa']:.2f}% a.a." if row['Tipo'] == 'Pré-fixado' else f"{row['Taxa']:.2f}% do CDI", axis=1
)
df_papeis['Valor'] = df_papeis['Valor'].apply(brl)
df_papeis['Vencimento'] = df_papeis['Data Vencimento'].dt.strftime('%d/%m/%Y')

colunas_exibir = ['Emissor', 'Ticker', 'Valor', 'Tipo', 'Taxa/CDI', 'Vencimento']

st.dataframe(
    df_papeis[colunas_exibir],
    hide_index=True,
    column_config={
        "Valor": st.column_config.TextColumn("Valor Investido", width="medium"),
        "Taxa/CDI": st.column_config.TextColumn("Rentabilidade", width="medium"),
        "Vencimento": st.column_config.TextColumn("Data de Vencimento", width="small"),
    }
)

if st.button("Limpar Lista de Papéis", type="primary"):
    st.session_state.papeis = []
    st.rerun()
    
st.markdown("---")

# ===================== CÁLCULOS CONSOLIDADOS =====================

resultados_calculados = []
papeis_para_grafico = []

# Nota: O cálculo usa 'data_aplicacao' que é obtida antes do st.stop()
for papel in st.session_state.papeis:
    resultado, erro = calcular_papel(papel, data_aplicacao, st.session_state.cdi_benchmark_geral) 
    if resultado:
        papel.update(resultado) 
        resultados_calculados.append(resultado)
        papeis_para_grafico.append(papel)
    elif erro:
        st.warning(f"Atenção: Papel **{papel['Ticker']}** ignorado na simulação. **{erro}**")

if not resultados_calculados:
    st.error("Não há papéis válidos para consolidar. Verifique as datas de vencimento.")
    
total_investido = sum(r['Valor Investido'] for r in resultados_calculados)
total_bruto = sum(r['Montante Bruto'] for r in resultados_calculados)
total_impostos = sum(r['Total Impostos'] for r in resultados_calculados)
total_liquido = sum(r['Montante Líquido'] for r in resultados_calculados)
rendimento_liquido_total = total_liquido - total_investido

rentabilidade_efetiva = (rendimento_liquido_total / total_investido) * 100 if total_investido > 0 else 0.0

st.subheader("Resultado Consolidado da Simulação", divider='gray')
c1, c2, c3, c4 = st.columns(4)

c1.markdown(f"<p style='font-size: 10px; margin-bottom: -15px;'>Total Investido</p><h4 style='color: {TEXTO_PRINCIPAL_ST};'>{brl(total_investido)}</h4>", unsafe_allow_html=True)
c2.markdown(f"<p style='font-size: 10px; margin-bottom: -15px;'>Montante Bruto</p><h4 style='color: {TEXTO_PRINCIPAL_ST};'>{brl(total_bruto)}</h4>", unsafe_allow_html=True)
c3.markdown(f"<p style='font-size: 10px; margin-bottom: -15px;'>Impostos (IR + IOF)</p><h4 style='color: {TEXTO_PRINCIPAL_ST};'>{brl(total_impostos)}</h4>", unsafe_allow_html=True)
c4.markdown(f"<p style='font-size: 10px; margin-bottom: -15px;'>Montante Líquido</p><h4 style='color: {TEXTO_PRINCIPAL_ST};'>{brl(total_liquido)}</h4>", unsafe_allow_html=True)

st.markdown(f"**Rendimento Líquido Total:** <span style='color:{VERDE_DESTAQUE}; font-size: 1.1em;'>{brl(rendimento_liquido_total)}</span>", unsafe_allow_html=True)
st.markdown(f"**Rentabilidade Líquida Efetiva:** <span style='color:{VERDE_DESTAQUE}; font-size: 1.1em;'>{rentabilidade_efetiva:.2f}%</span>", unsafe_allow_html=True) 
st.markdown("---")

# ===================== GRÁFICO (Simplificado) =====================
st.subheader("Visão por Papel (Montante Bruto)", divider='gray') 

df_resumo = pd.DataFrame(papeis_para_grafico)

df_resumo['Data Vencimento'] = pd.to_datetime(df_resumo['Data Vencimento'])

df_resumo['Valor_Grafico'] = df_resumo['Montante Bruto']
df_resumo['Label_Grafico'] = df_resumo['Emissor'] + ' (' + df_resumo['Data Vencimento'].dt.strftime('%Y') + ')'

fig, ax = plt.subplots(figsize=(8, 5)) 
ax.bar(df_resumo['Label_Grafico'], df_resumo['Valor_Grafico'], color=COR_PRIMARIA_FORM, alpha=0.7)
ax.set_title("Montante Bruto por Papel (R$)", fontsize=12) 
ax.set_ylabel("Montante Bruto (R$)", fontsize=10) 
ax.tick_params(axis='x', rotation=30, labelsize=7) 
ax.tick_params(axis='y', labelsize=8) 
ax.grid(axis='y', alpha=0.3)
plt.tight_layout() 
st.pyplot(fig)

# ===================== PDF GERAÇÃO =====================
def grafico_png():
    buf = BytesIO()
    
    fig.set_facecolor('white')
    ax.set_facecolor('white')
    
    ax.set_title(ax.get_title(), color='black')
    ax.set_xlabel(ax.get_xlabel(), color='black')
    ax.set_ylabel(ax.get_ylabel(), color='black')
    ax.tick_params(axis='x', colors='black')
    ax.tick_params(axis='y', colors='black')
    
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', facecolor='white')
    buf.seek(0)

    # Restaura cores para Streamlit 
    ax.set_title(ax.get_title(), color=TEXTO_PRINCIPAL_ST)
    ax.set_xlabel(ax.get_xlabel(), color=TEXTO_PRINCIPAL_ST)
    ax.set_ylabel(ax.get_ylabel(), color=TEXTO_PRINCIPAL_ST)
    ax.tick_params(axis='x', colors=TEXTO_PRINCIPAL_ST)
    ax.tick_params(axis='y', colors=TEXTO_PRINCIPAL_ST)

    return buf

def criar_pdf_secundarios():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    story = []
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(name='TitlePDF', fontSize=18, fontName='Helvetica-Bold', alignment=1, spaceAfter=7*mm, textColor=colors.HexColor('#000000')))
    styles.add(ParagraphStyle(name='SectionTitle', fontSize=10, fontName='Helvetica-Bold', spaceAfter=5*mm, textColor=colors.HexColor('#333333'), alignment=0))
    styles.add(ParagraphStyle(name='DataLabel', fontSize=9, fontName='Helvetica', textColor=colors.HexColor('#666666'), alignment=0))
    styles.add(ParagraphStyle(name='DataValue', fontSize=11, fontName='Helvetica-Bold', textColor=colors.HexColor('#333333'), alignment=0))
    styles.add(ParagraphStyle(name='Footer', fontSize=9, alignment=1, textColor=colors.HexColor('#666666')))
    styles.add(ParagraphStyle(name='Disclaimer', fontSize=7, fontName='Helvetica-Oblique', alignment=4, textColor=colors.HexColor('#666666'), spaceBefore=3*mm, spaceAfter=0*mm))
    
    styles.add(ParagraphStyle(name='ResultTitleLarge', fontSize=13, fontName='Helvetica-Bold', alignment=1, textColor=colors.white, backColor=AZUL_TABELA_PDF, topPadding=10, bottomPadding=10))
    
    # 1. Cabeçalho
    logo = carregar_logo()
    logo.hAlign = 'CENTER'
    story.append(logo)
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph("Simulação Consolidada - Papéis Secundários", styles['TitlePDF']))
    story.append(Paragraph("Projeção de Retorno com Múltiplos Emissores", getSampleStyleSheet()['Normal']))
    story.append(HRFlowable(width="100%", thickness=0.5, lineCap='round', color=colors.lightgrey, spaceBefore=5, spaceAfter=10))

    # 2. Dados Gerais
    story.append(Paragraph("DADOS DA SIMULAÇÃO", styles['SectionTitle']))
    data_geral = [
        [Paragraph("Cliente", styles['DataLabel']), Paragraph(nome_cliente, styles['DataValue']),
         Paragraph("Data Aplic.", styles['DataLabel']), Paragraph(data_aplicacao.strftime('%d/%m/%Y'), styles['DataValue'])],
        [Paragraph("Assessor", styles['DataLabel']), Paragraph(nome_assessor, styles['DataValue']),
         Paragraph("CDI Benchmark", styles['DataLabel']), Paragraph(f"{st.session_state.cdi_benchmark_geral:.2f}% a.a.", styles['DataValue'])], 
    ]
    total_width_pdf = A4[0] - 30*mm
    t_dados = Table(data_geral, colWidths=[total_width_pdf*0.2, total_width_pdf*0.3, total_width_pdf*0.2, total_width_pdf*0.3])
    t_dados.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('LEFTPADDING', (0,0), (-1,-1), 10)]))
    story.append(t_dados)
    story.append(Spacer(1, 5*mm))

    # 3. Tabela de Papéis
    story.append(Paragraph("DETALHES DOS PAPÉIS INCLUÍDOS", styles['SectionTitle']))
    
    data_tabela_papeis = [
        ["Emissor", "Ticker", "Valor Investido", "Tipo", "Taxa", "Vencimento", "Rendimento Líquido"]
    ]
    
    for p in papeis_para_grafico: 
        taxa_str = f"{p['Taxa']:.2f}% a.a." if p['Tipo'] == 'Pré-fixado' else f"{p['Taxa']:.2f}% do CDI"
        data_tabela_papeis.append([
            p['Emissor'],
            p['Ticker'],
            brl_pdf(p['Valor Investido']),
            p['Tipo'],
            taxa_str,
            p['Data Vencimento'].strftime('%d/%m/%Y'),
            brl_pdf(p['Rendimento Líquido'])
        ])

    colWidths_papeis = [total_width_pdf*0.18, total_width_pdf*0.12, total_width_pdf*0.15, total_width_pdf*0.12, total_width_pdf*0.15, total_width_pdf*0.13, total_width_pdf*0.15]
    t_papeis = Table(data_tabela_papeis, colWidths=colWidths_papeis)
    t_papeis.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
    ]))
    story.append(t_papeis)
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, lineCap='round', color=colors.lightgrey, spaceBefore=5, spaceAfter=10))

    # 4. Resultado Consolidado (Tabela Azul)
    
    resultado_completo = [
        [Paragraph("<b>RESULTADO CONSOLIDADO</b>", styles['ResultTitleLarge']), "", "", ""],
        ["TOTAL INVESTIDO", "MONTANTE BRUTO", "TOTAL IMPOSTOS", "MONTANTE LÍQUIDO"],
        [brl_pdf(total_investido), brl_pdf(total_bruto), brl_pdf(total_impostos), brl_pdf(total_liquido)],
        [Paragraph(f"Rentabilidade Líquida Efetiva: <font size='10' color='white'><b>{rentabilidade_efetiva:.2f}%</b></font>", styles['ResultTitleLarge']), "", "", ""],
    ]
    
    colWidths_4 = [total_width_pdf/4] * 4
    t_res_final = Table(resultado_completo, colWidths=colWidths_4)
    t_res_final.setStyle(TableStyle([
        ('SPAN', (0,0), (3,0)),
        ('SPAN', (0,3), (3,3)),
        ('BACKGROUND', (0,0), (-1,3), AZUL_TABELA_PDF),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.white),
        ('FONTSIZE', (0,1), (3,1), 9),
        ('FONTNAME', (0,1), (3,1), 'Helvetica-Bold'),
        ('TOPPADDING', (0,1), (3,1), 4),
        ('BOTTOMPADDING', (0,1), (3,1), 4),
        ('FONTSIZE', (0,2), (3,2), 14),
        ('TOPPADDING', (0,2), (3,2), 8),
        ('BOTTOMPADDING', (0,2), (3,2), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0, colors.transparent),
    ]))
    story.append(t_res_final)
    story.append(Spacer(1, 10*mm))
    
    # 5. Gráfico (Página 2)
    story.append(PageBreak())
    story.append(Paragraph("PROJEÇÃO DE MONTANTE BRUTO POR PAPEL", styles['SectionTitle'])) 
    
    img = Image(grafico_png(), width=160*mm, height=80*mm) 
    img.hAlign = 'CENTER'
    story.append(img)
    
    story.append(Spacer(1, 10*mm))

    # 6. Rodapé e Disclaimer
    story.append(Paragraph(f"Simulação elaborada por <b>{nome_assessor}</b> em {data_simulacao.strftime('%d/%m/%Y')}", styles['Footer']))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("DISCLAIMER", styles['SectionTitle']))
    disclaimer_text = ("A Traders Distribuidora de Valores Mobiliários Ltda., com CNPJ sob o nº 62.280.490/0001-84 é uma instituição financeira autorizada a funcionar pelo Banco Central do Brasil... [Insira o disclaimer legal completo da Traders DTVM aqui]...") 
    story.append(Paragraph(disclaimer_text, styles['Disclaimer']))


    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ===================== BOTÃO PDF =====================
if st.button("BAIXAR PROPOSTA CONSOLIDADA", type="primary", use_container_width=True):
    with st.spinner("Gerando sua proposta premium consolidada..."):
        try:
            pdf_data = criar_pdf_secundarios()
            b64 = base64.b64encode(pdf_data).decode()
            nome_arq = f"Proposta_Secundarios_{nome_cliente.replace(' ', '_')}.pdf"
            href = f'<a href="data:application/pdf;base64,{b64}" download="{nome_arq}"><h3 style="text-align:center; color:white;">BAIXAR PROPOSTA CONSOLIDADA</h3></a>'
            st.markdown(href, unsafe_allow_html=True)
            st.balloons()
            st.success("Proposta premium gerada com sucesso!")
        except Exception as e:
            st.error(f"Ocorreu um erro ao gerar o PDF: {e}")

# ===================== RODAPÉ STREAMLIT =====================
st.markdown(
    f"<p style='text-align:center; margin-top:40px;'>Simulação elaborada por <b>{nome_assessor}</b> em {data_simulacao.strftime('%d/%m/%Y')}</p>",
    unsafe_allow_html=True
)
