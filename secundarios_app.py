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
import locale 

# Configuração de locale para formatação de moeda em Python (não Streamlit)
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
    except locale.Error:
        pass # Ignora se não conseguir configurar

# ===================== INJEÇÃO DE CSS PARA CONTROLAR AS LARGURAS E CORES =====================
st.markdown("""
<style>
/* 1. Limita o conteúdo principal (inputs, tabelas, etc.) a 80% da largura da tela */
.main .block-container {
    max-width: 80% !important; 
    padding-left: 2rem;
    padding-right: 2rem;
}

/* 2. Ajusta o tamanho do logo (máximo 400px e centraliza) */
.stMarkdown > div > img {
    display: block;
    margin-left: auto;
    margin-right: auto;
    max-width: 400px; 
    height: auto;
}

/* Força o botão primário (tipo="primary") para o verde desejado (#2E8B57) */
div.stButton > button[data-testid="baseButton-primary"] {
    background-color: #2E8B57;
    border-color: #2E8B57;
    color: white !important;
}

div.stButton > button[data-testid="baseButton-primary"]:hover {
    background-color: #3C9F68;
    border-color: #3C9F68;
}

</style>
""", unsafe_allow_html=True)

# ===================== CONFIGURAÇÃO INICIAL E CONSTANTES =====================
st.set_page_config(page_title="Traders Secundários - Calculadora", layout="wide")

URL_LOGO_WHITE = "https://ik.imagekit.io/aufhkvnry/logo-traders__bg-white.png" # Altere para o seu logo
TEXTO_PRINCIPAL_ST = "#222222"
VERDE_DESTAQUE = '#2E8B57'
AZUL_TABELA_PDF = colors.HexColor("#864df4")
COR_PRIMARIA_FORM = VERDE_DESTAQUE 
TAXA_CDI_MERCADO = 14.90

# Lista de Assessores para o Selectbox
ASSESSORES_LISTA = [
    "Selecione um Assessor...", # Opção inicial para validação
    "Tiago Sampaio",
    "Bruno Nunes",
    "Luan Su Iye",
    "Pedro Matos"
]

# ===================== FUNÇÕES AUXILIARES =====================

def carregar_logo():
    # Esta função é usada apenas para o PDF
    url = URL_LOGO_WHITE
    response = requests.get(url)
    img_pil = PILImage.open(PIOBytesIO(response.content))
    largura, altura = img_pil.size
    proporcao = altura / largura
    
    # Aumentar largura desejada para o logo no PDF (80mm)
    largura_desejada = 80 * mm
    
    altura_calculada = largura_desejada * proporcao
    return Image(PIOBytesIO(response.content), width=largura_desejada, height=altura_calculada)

# Funções de formatação de moeda
brl = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
brl_pdf = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ===================== CÁLCULO FINANCEIRO =====================
def calcular_papel(papel, data_aplicacao, taxa_cdi_benchmark):
    valor_investido = papel['Valor']
    data_vencimento = papel['Data Vencimento']
    tipo = papel['Tipo']
    taxa_input = papel['Taxa']

    # --- 1. VALIDAÇÃO E PRAZO ---
    if isinstance(data_vencimento, pd.Timestamp):
        data_vencimento = data_vencimento.date()
    elif isinstance(data_vencimento, str):
        try:
            data_vencimento = datetime.datetime.strptime(data_vencimento, '%Y-%m-%d').date()
        except ValueError:
            try:
                data_vencimento = datetime.datetime.strptime(data_vencimento, '%d/%m/%Y').date()
            except ValueError:
                return None, f"Formato de Data de Vencimento inválido para {papel.get('Ticker', 'novo papel')}"

    # Prazo (diferença entre a data de vencimento e a data de aplicação)
    prazo_dias = (data_vencimento - data_aplicacao).days
    
    if prazo_dias <= 0 or valor_investido <= 0 or taxa_input <= 0:
        return None, f"Dados inválidos para {papel.get('Ticker', 'novo papel')}"
    
    # Constante de cálculo financeiro (360 dias)
    dias_ano = 360
    
    # --- 2. TAXA REAL ---
    taxa_anual_real = taxa_input
    if tipo == "Pós-fixado (% do CDI)":
        taxa_anual_real = taxa_cdi_benchmark * (taxa_input / 100)
    
    # Converte taxa anual (%) para fator diário
    taxa_diaria = (1 + taxa_anual_real/100)**(1/dias_ano) - 1

    
    # --- 3. CÁLCULO BRUTO ---
    montante_bruto = valor_investido * (1 + taxa_diaria)**prazo_dias
    rendimento_bruto = montante_bruto - valor_investido

    # --- 4. CÁLCULO IOF ---
    rendimento_apos_iof = rendimento_bruto
    imposto_iof = 0.0
    
    if prazo_dias < 30:
        iof_tab = [0.96,0.93,0.90,0.86,0.83,0.80,0.76,0.73,0.70,0.66,0.63,0.60,0.56,0.53,0.50,
                 0.46,0.43,0.40,0.36,0.33,0.30,0.26,0.23,0.20,0.16,0.13,0.10,0.06,0.03,0.00]
        
        idx = prazo_dias - 1
        aliquota_iof = iof_tab[idx]
        
        imposto_iof = rendimento_bruto * aliquota_iof
        rendimento_apos_iof = rendimento_bruto - imposto_iof

    # --- 5. CÁLCULO IR ---
    aliquota_ir = 22.5 if prazo_dias <= 180 else 20.0 if prazo_dias <= 360 else 17.5 if prazo_dias <= 720 else 15.0
    
    imposto_ir = rendimento_apos_iof * (aliquota_ir/100)
    
    # --- 6. RESULTADO FINAL ---
    total_impostos = imposto_iof + imposto_ir
    montante_liquido = valor_investido + rendimento_apos_iof - imposto_ir
    rendimento_liquido = montante_liquido - valor_investido
    
    resultado = {
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
    }

    return resultado, None

# ===================== FUNÇÃO GERADORA DE MENSAGEM DE EXECUÇÃO =====================
def generate_execution_message(papeis, codigo_cliente):
    """Gera a mensagem formatada para a mesa de operações."""
    
    message = "Solicito seguir com a aplicação com os detalhes abaixo:\n\n"
    
    for p in papeis:
        # 1. Recupera dados do papel
        emissor = p.get('Emissor', 'N/A')
        # Ticker foi substituído por Código na exibição, mas a chave interna continua sendo 'Ticker'
        codigo = p.get('Ticker', 'N/A') 
        valor = p.get('Valor Investido', p.get('Valor', 0.0)) 
        taxa_input = p.get('Taxa', 0.0)
        tipo = p.get('Tipo', 'Pré-fixado')
        vencimento_date = p.get('Data Vencimento')

        # 2. Formata Taxa
        if tipo == 'Pré-fixado':
            taxa_str = f"{taxa_input:.2f}% a.a."
        elif tipo == 'Pós-fixado (% do CDI)':
            taxa_str = f"{taxa_input:.2f}% do CDI"
        else:
            taxa_str = f"{taxa_input:.2f}%"

        # 3. Formata Vencimento
        vencimento_str = 'N/A'
        if isinstance(vencimento_date, datetime.date):
            vencimento_str = vencimento_date.strftime('%d/%m/%Y')
        elif isinstance(vencimento_date, pd.Timestamp):
            vencimento_str = vencimento_date.date().strftime('%d/%m/%Y')
        elif isinstance(vencimento_date, str):
            try:
                vencimento_str = datetime.datetime.strptime(vencimento_date, '%Y-%m-%d').date().strftime('%d/%m/%Y')
            except:
                pass
            
        # 4. Formata Valor
        valor_str = brl(valor).replace("R$ ", "") 

        # 5. Constrói a linha (usando 'codigo')
        line = f"{emissor} - {codigo} - {taxa_str} - {vencimento_str} - R$ {valor_str} - {codigo_cliente}"
        
        message += line + "\n"

    # 6. Adiciona o fechamento
    message += "\nObrigado!"
    
    return message


# ===================== SESSION STATE =====================
if 'papeis' not in st.session_state:
    st.session_state['papeis'] = []
if 'cdi_benchmark_geral' not in st.session_state:
    st.session_state['cdi_benchmark_geral'] = TAXA_CDI_MERCADO
if 'nome_cliente' not in st.session_state:
    st.session_state['nome_cliente'] = "João Silva"
if 'codigo_cliente' not in st.session_state:
    st.session_state['codigo_cliente'] = ""
if 'nome_assessor_selected_key' not in st.session_state:
    st.session_state['nome_assessor_selected_key'] = ASSESSORES_LISTA[0]
if 'data_simulacao' not in st.session_state:
    st.session_state['data_simulacao'] = datetime.date.today()
if 'data_aplicacao' not in st.session_state:
    st.session_state['data_aplicacao'] = datetime.date.today()
    
# ===================== LOGO + TÍTULO (Streamlit Display) =====================
st.markdown(
    f"""<div style="text-align: center; margin: 10px 0;">
        <img src="{URL_LOGO_WHITE}" style="max-width: 400px; height: auto;">
    </div>""",
    unsafe_allow_html=True
)
st.markdown(f"<h3 style='text-align: center; color: {TEXTO_PRINCIPAL_ST};'>Calculadora de Simulação de Papéis Secundários</h3>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center; font-size: 15px; margin-bottom: 20px;'>Adicione e gerencie os papéis diretamente na tabela abaixo para simular o resultado consolidado para o cliente.</p>", unsafe_allow_html=True)
st.markdown("---")

# ===================== DADOS GERAIS DA SIMULAÇÃO =====================
st.subheader("Dados Gerais da Simulação", divider='gray')

# LINHA 1: Nome do Cliente, Código do Cliente, Nome do Assessor
col_nome, col_cod, col_assessor = st.columns(3)

with col_nome:
    st.text_input("Nome do Cliente", key='nome_cliente')

with col_cod:
    st.text_input("Código do Cliente", key='codigo_cliente')

with col_assessor:
    nome_assessor = st.selectbox(
        "Nome do Assessor (Obrigatório)", 
        options=ASSESSORES_LISTA,
        key='nome_assessor_selected_key'
    )

# LINHA 2: Data da Simulação, Data de Aplicação, Taxa CDI Anual (Benchmark)
col_data_sim, col_data_app, col_cdi = st.columns(3)

with col_data_sim:
    st.date_input("Data da Simulação", key='data_simulacao', format="DD/MM/YYYY")

with col_data_app:
    st.date_input("Data de Aplicação/Compra", key='data_aplicacao', format="DD/MM/YYYY")

with col_cdi:
    st.number_input("Taxa CDI Anual (Benchmark) (%)", step=0.05, key='cdi_benchmark_geral')
    
st.markdown("---")

# ===================== TABELA DE PAPÉIS ADICIONADOS =====================
st.subheader("Papéis Incluídos para Simulação", divider='gray')

# Prepara o DataFrame para o editor
if st.session_state.papeis:
    df_papeis = pd.DataFrame(st.session_state.papeis)
    df_papeis['Data Vencimento'] = pd.to_datetime(df_papeis['Data Vencimento'], errors='coerce').dt.date
    df_papeis['Valor'] = df_papeis['Valor'].astype(float).round(2)
    df_papeis['Taxa'] = df_papeis['Taxa'].astype(float).round(2)
else:
    df_papeis = pd.DataFrame(columns=['Emissor', 'Ticker', 'Valor', 'Tipo', 'Taxa', 'Data Vencimento'])


# Renomear colunas para exibição amigável (MUDANÇA AQUI: Ticker -> Código)
df_papeis_edit = df_papeis.rename(columns={
    'Emissor': 'Emissor',
    'Ticker': 'Código',
    'Valor': 'Valor Investido (R$)',
    'Tipo': 'Tipo de Taxa',
    'Taxa': 'Taxa (%)',
    'Data Vencimento': 'Vencimento',
})

# MUDANÇA AQUI: Ticker -> Código
colunas_data_editor = ['Emissor', 'Código', 'Valor Investido (R$)', 'Tipo de Taxa', 'Taxa (%)', 'Vencimento']

st.info("Para **editar** um papel, clique duas vezes na célula. Para **remover**, selecione a linha e pressione o botão `Del` no teclado ou o ícone 🗑️ na tabela. Para **adicionar** um novo papel, use o botão **+ Adicionar linha** na parte inferior da tabela.")

edited_df = st.data_editor(
    df_papeis_edit[colunas_data_editor],
    hide_index=True,
    num_rows="dynamic", # Inclusão na tabela
    column_config={
        "Valor Investido (R$)": st.column_config.NumberColumn(
            "Valor Investido (R$)",
            format="%.2f",
            step=0.01,
            min_value=0.01,
        ),
        "Tipo de Taxa": st.column_config.SelectboxColumn(
            "Tipo de Taxa",
            options=["Pré-fixado", "Pós-fixado (% do CDI)"],
            required=True,
        ),
        "Taxa (%)": st.column_config.NumberColumn(
            "Taxa (%)",
            format="%.2f",
            step=0.01,
            min_value=0.01,
        ),
        "Vencimento": st.column_config.DateColumn(
            "Vencimento",
            format="DD/MM/YYYY",
            min_value=datetime.date.today() + relativedelta(days=+1),
        ),
    },
    key="data_editor_papeis"
)

# Processar as edições, adições e remoções do data_editor
# Manter 'Ticker' como chave interna para compatibilidade com o cálculo (MUDANÇA AQUI: Código -> Ticker)
df_papeis_new = edited_df.rename(columns={
    'Código': 'Ticker', 
    'Valor Investido (R$)': 'Valor',
    'Tipo de Taxa': 'Tipo',
    'Taxa (%)': 'Taxa',
    'Vencimento': 'Data Vencimento',
})

# Remove linhas onde os valores essenciais não são válidos
df_papeis_new = df_papeis_new[
    (df_papeis_new['Valor'].astype(float) > 0) &
    (df_papeis_new['Taxa'].astype(float) > 0) &
    (df_papeis_new['Data Vencimento'].apply(lambda x: isinstance(x, (datetime.date, pd.Timestamp)) or pd.notna(x)))
]

papeis_anteriores_len = len(st.session_state.papeis)
st.session_state.papeis = df_papeis_new.to_dict('records')

if papeis_anteriores_len != len(st.session_state.papeis):
    st.success("Tabela de papéis atualizada. Recalculando a simulação...")
    st.rerun()

# ===================== FERRAMENTAS DA TABELA (Limpar) =====================
st.subheader("Ferramentas da Tabela", divider='gray')

def clear_papeis():
    st.session_state.papeis = []
    st.rerun()

if st.button("Limpar Todos os Papéis", use_container_width=True):
    clear_papeis()
    
st.markdown("---")

# ===================== CÁLCULOS CONSOLIDADOS =====================
if not st.session_state.papeis:
    st.info("Nenhum papel válido para simulação. Por favor, adicione um papel com valor e taxa positivos e data de vencimento futura na tabela acima.")
    st.stop()
    
resultados_calculados = []
papeis_para_grafico = []

current_cdi_benchmark = st.session_state.cdi_benchmark_geral

for papel in st.session_state.papeis:
    try:
        papel_temp = papel.copy()
        papel_temp['Valor'] = float(papel_temp['Valor'])
        papel_temp['Taxa'] = float(papel_temp['Taxa'])
    except (ValueError, TypeError):
        continue
        
    resultado, erro = calcular_papel(papel_temp, st.session_state.data_aplicacao, current_cdi_benchmark)
    if resultado:
        papel_temp.update(resultado)
        papeis_para_grafico.append(papel_temp)
        resultados_calculados.append(resultado)
    elif erro:
        # A chave interna continua sendo 'Ticker'
        st.warning(f"Atenção: Papel **{papel.get('Ticker', 'novo papel')}** ignorado na simulação. **{erro}**")

if not resultados_calculados:
    st.error("Não há papéis válidos para consolidar. Verifique os dados inseridos (Valor > R$0, Taxa > 0% e Vencimento futuro).")
    st.stop()

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

# ===================== FUNÇÕES DE GERAÇÃO DE PDF E GRÁFICO =====================
def grafico_png():
    df_pdf = pd.DataFrame(papeis_para_grafico)
    df_pdf['Data Vencimento'] = pd.to_datetime(df_pdf['Data Vencimento'], errors='coerce')
    df_pdf = df_pdf.dropna(subset=['Data Vencimento'])
    df_pdf['Vencimento Formatado'] = df_pdf['Data Vencimento'].dt.strftime('%m/%Y')
    
    df_timeline = df_pdf.groupby('Vencimento Formatado')['Valor Investido'].sum().reset_index()
    df_timeline['Data Ordenacao'] = pd.to_datetime(df_timeline['Vencimento Formatado'], format='%m/%Y')
    df_timeline = df_timeline.sort_values(by='Data Ordenacao').drop(columns=['Data Ordenacao'])
    
    fig_pdf, ax_pdf = plt.subplots(figsize=(10, 5))
    
    bar_container = ax_pdf.barh(
        df_timeline['Vencimento Formatado'],
        df_timeline['Valor Investido'],
        color=COR_PRIMARIA_FORM,
        alpha=0.8
    )
    
    ax_pdf.set_title("Timeline de Liquidez: Valor Investido por Vencimento (Mês/Ano)", fontsize=14, color='black')
    ax_pdf.set_xlabel("")
    ax_pdf.set_ylabel("Vencimento", fontsize=12, color='black')
    
    for bar in bar_container:
        width = bar.get_width()
        valor_formatado = f'R$ {width:,.0f}'.replace(",", "X").replace(".", ",").replace("X", ".")
        
        ax_pdf.text(
            width, 
            bar.get_y() + bar.get_height()/2, 
            '  ' + valor_formatado, 
            va='center', 
            ha='left', 
            fontsize=9,
            color='black',
            fontweight='bold'
        )

    max_value = df_timeline['Valor Investido'].max()
    ax_pdf.set_xlim(right=max_value * 1.20)
    
    ax_pdf.xaxis.set_major_formatter(mticker.NullFormatter())
    ax_pdf.tick_params(axis='x', length=0)
    
    ax_pdf.tick_params(axis='y', labelsize=9, colors='black')
    ax_pdf.grid(axis='x', alpha=0.3, linestyle='--')
    
    fig_pdf.set_facecolor('white')
    ax_pdf.set_facecolor('white')
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close(fig_pdf)
    
    return buf

def criar_pdf_secundarios():
    if not papeis_para_grafico:
        raise ValueError("Não há papéis válidos para gerar a proposta consolidada.")
        
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    story = []
    styles = getSampleStyleSheet()
    
    # Estilos (condensados para brevidade)
    styles.add(ParagraphStyle(name='TitlePDF', fontSize=18, fontName='Helvetica-Bold', alignment=1, spaceAfter=5*mm, textColor=colors.HexColor('#000000')))
    styles.add(ParagraphStyle(name='SectionTitle', fontSize=10, fontName='Helvetica-Bold', spaceBefore=5*mm, spaceAfter=3*mm, textColor=colors.HexColor('#333333'), alignment=0))
    styles.add(ParagraphStyle(name='DataLabel', fontSize=9, fontName='Helvetica', textColor=colors.HexColor('#666666'), alignment=0))
    styles.add(ParagraphStyle(name='DataValue', fontSize=11, fontName='Helvetica-Bold', textColor=colors.HexColor('#333333'), alignment=0))
    styles.add(ParagraphStyle(name='Footer', fontSize=9, alignment=1, textColor=colors.HexColor('#666666')))
    styles.add(ParagraphStyle(name='Disclaimer', fontSize=7, fontName='Helvetica-Oblique', alignment=4, textColor=colors.HexColor('#666666'), spaceBefore=3*mm, spaceAfter=0*mm))
    styles.add(ParagraphStyle(name='CDBText', fontSize=9, fontName='Helvetica', textColor=colors.HexColor('#333333'), spaceAfter=5*mm))
    styles.add(ParagraphStyle(name='ResultTitleLarge', fontSize=13, fontName='Helvetica-Bold', alignment=1, textColor=colors.white, backColor=AZUL_TABELA_PDF, topPadding=8, bottomPadding=8))
    # MUDANÇA AQUI: Ticker -> Código no cabeçalho
    styles.add(ParagraphStyle(name='TableHeaderPDF', fontSize=7, fontName='Helvetica-Bold', alignment=1, textColor=colors.HexColor('#333333')))
    styles.add(ParagraphStyle(name='TableCellPDF', fontSize=7, fontName='Helvetica', alignment=2))


    # 1. Cabeçalho
    logo = carregar_logo()
    logo.hAlign = 'CENTER'
    story.append(Spacer(1, 3*mm))
    story.append(logo)
    story.append(Spacer(1, 3*mm))
    
    story.append(Paragraph("Simulação Consolidada - Renda Fixa FGC", styles['TitlePDF']))
    story.append(Paragraph("Projeção de Retorno com Múltiplos Emissores", getSampleStyleSheet()['Normal']))
    story.append(HRFlowable(width="100%", thickness=0.5, lineCap='round', color=colors.lightgrey, spaceBefore=3*mm, spaceAfter=5*mm))

    # 2. Dados Gerais (usando as session_state keys)
    story.append(Paragraph("DADOS DA SIMULAÇÃO", styles['SectionTitle']))
    
    data_geral = [
        [Paragraph("Cliente", styles['DataLabel']), Paragraph(st.session_state['nome_cliente'], styles['DataValue']),
         Paragraph("Data Aplic.", styles['DataLabel']), Paragraph(st.session_state['data_aplicacao'].strftime('%d/%m/%Y'), styles['DataValue'])],
        [Paragraph("Assessor", styles['DataLabel']), Paragraph(st.session_state['nome_assessor_selected_key'] if st.session_state['nome_assessor_selected_key'] else "N/A", styles['DataValue']),
         Paragraph("CDI Benchmark", styles['DataLabel']), Paragraph(f"{current_cdi_benchmark:.2f}% a.a.", styles['DataValue'])],
    ]
    total_width_pdf = A4[0] - 30*mm
    t_dados = Table(data_geral, colWidths=[total_width_pdf*0.2, total_width_pdf*0.3, total_width_pdf*0.2, total_width_pdf*0.3])
    t_dados.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('LEFTPADDING', (0,0), (-1,-1), 10)]))
    story.append(t_dados)
    story.append(Spacer(1, 5*mm))

    # 3. Tabela de Papéis (Resumo)
    story.append(Paragraph("RESUMO DOS PAPÉIS INCLUÍDOS", styles['SectionTitle']))
    
    # MUDANÇA AQUI: Ticker -> Código no cabeçalho
    data_tabela_papeis = [
        [Paragraph("Emissor", styles['TableHeaderPDF']), Paragraph("Código", styles['TableHeaderPDF']), Paragraph("Valor Investido", styles['TableHeaderPDF']), Paragraph("Tipo", styles['TableHeaderPDF']), Paragraph("Taxa", styles['TableHeaderPDF']), Paragraph("Vencimento", styles['TableHeaderPDF']), Paragraph("Rendimento Líquido", styles['TableHeaderPDF'])]
    ]
    
    for p in papeis_para_grafico:
        vencimento_date = p['Data Vencimento']
        if isinstance(vencimento_date, pd.Timestamp):
            vencimento_date = vencimento_date.date()
        elif isinstance(vencimento_date, str):
            try:
                vencimento_date = datetime.datetime.strptime(vencimento_date, '%
