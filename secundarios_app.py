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
import matplotlib.ticker as mticker 

# ===================== INJEÇÃO DE CSS PARA CONTROLAR AS LARGURAS =====================
st.markdown("""
<style>
/* 1. Limita o conteúdo principal (inputs, tabelas, etc.) a 60% da largura da tela */
.main .block-container {
    max-width: 60% !important; 
    padding-left: 2rem;
    padding-right: 2rem;
}

/* 2. Ajusta o tamanho do logo (máximo 400px e centraliza) */
.stMarkdown > div > img {
    display: block;
    margin-left: auto;
    margin-right: auto;
    max-width: 400px; /* Limite o logo para que não fique imenso */
    height: auto;
}
</style>
""", unsafe_allow_html=True)

# ===================== CONFIGURAÇÃO INICIAL E CONSTANTES =====================
st.set_page_config(page_title="Traders Secundários - Calculadora", layout="wide")

URL_LOGO_WHITE = "https://ik.imagekit.io/aufhkvnry/logo-traders__bg-white.png" # Altere para o seu logo
TEXTO_PRINCIPAL_ST = "#222222"
VERDE_DESTAQUE = '#2E8B57'
AZUL_TABELA_PDF = colors.HexColor("#864df4")
COR_PRIMARIA_FORM = '#6B48FF' 
TAXA_CDI_MERCADO = 14.90 

# ===================== FUNÇÕES AUXILIARES =====================

def carregar_logo():
    # Esta função é usada apenas para o PDF
    url = URL_LOGO_WHITE
    response = requests.get(url)
    img_pil = PILImage.open(PIOBytesIO(response.content))
    largura, altura = img_pil.size
    proporcao = altura / largura
    largura_desejada = 400 
    altura_calculada = largura_desejada * proporcao
    return Image(PIOBytesIO(response.content), width=largura_desejada, height=altura_calculada)

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
    elif isinstance(data_vencimento, str):
        try:
            data_vencimento = datetime.datetime.strptime(data_vencimento, '%Y-%m-%d').date()
        except ValueError:
            try:
                data_vencimento = datetime.datetime.strptime(data_vencimento, '%d/%m/%Y').date()
            except ValueError:
                return None, f"Formato de Data de Vencimento inválido para {papel.get('Ticker', 'novo papel')}"
    elif data_vencimento is None:
        return None, f"Data de Vencimento nula para {papel.get('Ticker', 'novo papel')}"

    prazo_dias = (data_vencimento - data_aplicacao).days
    
    if prazo_dias <= 0:
        return None, f"Data de resgate inválida para {papel.get('Ticker', 'novo papel')}. Prazo: {prazo_dias} dias"
    
    if valor_investido <= 0 or taxa_input <= 0:
        return None, f"Valor investido ({valor_investido}) ou Taxa ({taxa_input}%) inválida para {papel.get('Ticker', 'novo papel')}"

    dias_ano = 360 
    taxa_anual_real = taxa_input

    if tipo == "Pós-fixado (% do CDI)":
        taxa_anual_real = taxa_cdi_benchmark * (taxa_input / 100)
    
    # Formulação da taxa diária:
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

# ===================== SESSION STATE =====================
if 'papeis' not in st.session_state:
    # Adicionando um valor de exemplo inicial no Session State
    st.session_state['papeis'] = [
        {'Emissor': 'BANCO X', 'Ticker': 'CDB-X1', 'Valor': 20000.00, 'Tipo': 'Pré-fixado', 'Taxa': 16.50, 'Data Vencimento': datetime.date.today() + relativedelta(months=+12)},
        {'Emissor': 'BANCO Y', 'Ticker': 'CDB-Y2', 'Valor': 30000.00, 'Tipo': 'Pós-fixado', 'Taxa': 105.00, 'Data Vencimento': datetime.date.today() + relativedelta(months=+24)},
    ]
if 'cdi_benchmark_geral' not in st.session_state:
    st.session_state['cdi_benchmark_geral'] = TAXA_CDI_MERCADO
    
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
c1, c2 = st.columns(2) 

with c1:
    nome_cliente = st.text_input("Nome do Cliente", "João Silva")
    data_simulacao = st.date_input("Data da Simulação", datetime.date.today(), format="DD/MM/YYYY")

with c2:
    nome_assessor = st.text_input("Nome do Assessor", "Seu Nome")
    data_aplicacao = st.date_input("Data de Aplicação/Compra", datetime.date.today(), format="DD/MM/YYYY")

st.number_input("Taxa CDI Anual (Benchmark) (%)", value=st.session_state['cdi_benchmark_geral'], step=0.05, key='cdi_benchmark_geral') 
    
st.markdown("---")

# ===================== TABELA DE PAPÉIS ADICIONADOS (Inclusão, Edição e Remoção pela Tabela) =====================

st.subheader("Papéis Incluídos para Simulação", divider='gray')

# Prepara o DataFrame para o editor
if st.session_state.papeis:
    df_papeis = pd.DataFrame(st.session_state.papeis)
    # Garante que Data Vencimento é um objeto date, importante para o data_editor
    df_papeis['Data Vencimento'] = pd.to_datetime(df_papeis['Data Vencimento'], errors='coerce').dt.date 
    df_papeis['Valor'] = df_papeis['Valor'].astype(float).round(2)
    df_papeis['Taxa'] = df_papeis['Taxa'].astype(float).round(2)
else:
    # Cria um DataFrame vazio com as colunas esperadas para permitir a adição de novas linhas
    df_papeis = pd.DataFrame(columns=['Emissor', 'Ticker', 'Valor', 'Tipo', 'Taxa', 'Data Vencimento'])
    df_papeis.loc[0] = ['Emissor Exemplo', 'TICKER00', 1000.00, 'Pré-fixado', 15.00, datetime.date.today() + relativedelta(months=+12)]


# Renomear colunas para exibição amigável
df_papeis_edit = df_papeis.rename(columns={
    'Emissor': 'Emissor',
    'Ticker': 'Ticker',
    'Valor': 'Valor Investido (R$)',
    'Tipo': 'Tipo de Taxa',
    'Taxa': 'Taxa (%)',
    'Data Vencimento': 'Vencimento',
})

colunas_data_editor = ['Emissor', 'Ticker', 'Valor Investido (R$)', 'Tipo de Taxa', 'Taxa (%)', 'Vencimento']

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
            options=["Pré-fixado", "Pós-fixado)"],
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
df_papeis_new = edited_df.rename(columns={
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

# Botão de Limpar Lista
if st.button("Limpar Todos os Papéis", type="primary"):
    st.session_state.papeis = []
    st.rerun()
    
st.markdown("---")

# ===================== CÁLCULOS CONSOLIDADOS =====================

if not st.session_state.papeis:
    st.info("Nenhum papel válido para simulação. Por favor, adicione um papel com valor e taxa positivos e data de vencimento futura na tabela acima.")
    st.stop()
    
resultados_calculados = []
papeis_para_grafico = []

for papel in st.session_state.papeis:
    try:
        papel['Valor'] = float(papel['Valor'])
        papel['Taxa'] = float(papel['Taxa'])
    except (ValueError, TypeError):
        continue # Ignora papéis com valores não numéricos
        
    resultado, erro = calcular_papel(papel, data_aplicacao, st.session_state.cdi_benchmark_geral) 
    if resultado:
        papel.update(resultado) 
        resultados_calculados.append(resultado)
        papeis_para_grafico.append(papel)
    elif erro:
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

# ===================== GRÁFICO DO STREAMLIT (Mantém o Montante Bruto por Papel para a Tela) =====================
st.subheader("Visão por Papel (Montante Bruto)", divider='gray') 

df_resumo = pd.DataFrame(papeis_para_grafico)

df_resumo['Data Vencimento'] = pd.to_datetime(df_resumo['Data Vencimento'], errors='coerce')
df_resumo = df_resumo.dropna(subset=['Data Vencimento'])

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

# ===================== PDF GERAÇÃO (COM NOVO GRÁFICO TIMELINE DE LIQUIDEZ) =====================
def grafico_png():
    # --- NOVO GRÁFICO: TIMELINE DE LIQUIDEZ (Valor Investido Agregado por Mês/Ano) ---
    df_pdf = pd.DataFrame(papeis_para_grafico)
    
    # Garantir que a coluna de data é datetime e formatar para o agrupamento
    df_pdf['Data Vencimento'] = pd.to_datetime(df_pdf['Data Vencimento'], errors='coerce')
    df_pdf = df_pdf.dropna(subset=['Data Vencimento'])
    
    # Criar a coluna de agrupamento (Mês/Ano)
    df_pdf['Vencimento Formatado'] = df_pdf['Data Vencimento'].dt.strftime('%m/%Y')
    
    # Agrupar e somar o valor investido
    df_timeline = df_pdf.groupby('Vencimento Formatado')['Valor Investido'].sum().reset_index()
    
    # Ordenar corretamente pelo ano e mês para exibição na timeline
    df_timeline['Data Ordenacao'] = pd.to_datetime(df_timeline['Vencimento Formatado'], format='%m/%Y')
    df_timeline = df_timeline.sort_values(by='Data Ordenacao').drop(columns=['Data Ordenacao'])
    
    # Gera o Gráfico de Barras Horizontal (Timeline de Liquidez)
    fig_pdf, ax_pdf = plt.subplots(figsize=(10, 5)) 
    
    # 1. Plotar o gráfico e capturar os elementos do barh (bar_container)
    bar_container = ax_pdf.barh(
        df_timeline['Vencimento Formatado'], 
        df_timeline['Valor Investido'], 
        color=COR_PRIMARIA_FORM, 
        alpha=0.8
    )
    
    ax_pdf.set_title("Timeline de Liquidez: Valor Investido por Vencimento (Mês/Ano)", fontsize=14, color='black') 
    
    # AJUSTE 1: Remover o rótulo do eixo X, pois o valor estará nas barras
    ax_pdf.set_xlabel("") 
    
    # AJUSTE 2: Garantir que o rótulo do eixo Y é a data (Mês/Ano)
    ax_pdf.set_ylabel("Vencimento", fontsize=12, color='black')
    
    # AJUSTE 3: Adicionar os valores (R$) como rótulos de dados (Data Labels)
    for bar in bar_container:
        width = bar.get_width() # O valor do eixo X (Valor Investido)
        # Formatar o valor para R$
        # Uso de 'brl' localmente ou uma formatação específica para o gráfico
        valor_formatado = f'R$ {width:,.0f}'.replace(",", "X").replace(".", ",").replace("X", ".")
        
        # Adicionar o rótulo de dados (Data Label)
        ax_pdf.text(
            width, # Posição X: na ponta da barra
            bar.get_y() + bar.get_height()/2, # Posição Y: centro da barra
            '  ' + valor_formatado, # Adicionar um pequeno espaço
            va='center', # Alinhamento vertical no centro
            ha='left', # Alinhamento horizontal à esquerda (fora da barra)
            fontsize=9,
            color='black',
            fontweight='bold'
        )

    # Melhorar a visualização: Ajustar o limite do eixo X para acomodar os Data Labels
    max_value = df_timeline['Valor Investido'].max()
    ax_pdf.set_xlim(right=max_value * 1.20) # Aumenta o limite do eixo X em 20%
    
    # Ocultar os ticks e labels do eixo X (já que o valor está nas barras)
    ax_pdf.xaxis.set_major_formatter(mticker.NullFormatter())
    ax_pdf.tick_params(axis='x', length=0)
    
    ax_pdf.tick_params(axis='y', labelsize=9, colors='black') 
    ax_pdf.grid(axis='x', alpha=0.3, linestyle='--')
    
    fig_pdf.set_facecolor('white')
    ax_pdf.set_facecolor('white')
    plt.tight_layout() 

    # Salvar em buffer PNG
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close(fig_pdf) # Fecha a figura para não poluir o Streamlit
    
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
    styles.add(ParagraphStyle(name='CDBText', fontSize=9, fontName='Helvetica', textColor=colors.HexColor('#333333'), spaceAfter=10*mm)) 
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
        vencimento_date = p['Data Vencimento']
        if isinstance(vencimento_date, pd.Timestamp):
            vencimento_date = vencimento_date.date()
        elif isinstance(vencimento_date, str):
             # Tratar caso de string que passou do data_editor
            try:
                vencimento_date = datetime.datetime.strptime(vencimento_date, '%Y-%m-%d').date()
            except:
                vencimento_date = datetime.date.today() # fallback
            
        taxa_str = f"{p['Taxa']:.2f}% a.a." if p['Tipo'] == 'Pré-fixado' else f"{p['Taxa']:.2f}% do CDI"
        data_tabela_papeis.append([
            p['Emissor'],
            p['Ticker'],
            brl_pdf(p['Valor Investido']),
            p['Tipo'],
            taxa_str,
            vencimento_date.strftime('%d/%m/%Y'),
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
    
    # 5. Fundamentos do CDB 
    story.append(HRFlowable(width="100%", thickness=0.5, lineCap='round', color=colors.lightgrey, spaceBefore=5, spaceAfter=10))
    story.append(Paragraph("FUNDAMENTOS DO CDB", styles['SectionTitle']))
    
    cdb_text = (
        "O <b>CDB</b> (Certificado de Depósito Bancário) é um título de <b>renda fixa</b> emitido por bancos para captar recursos. É considerado "
        "um <b>investimento de baixo risco</b> e conta com a <b>garantia do FGC</b> (Fundo Garantidor de Créditos), que cobre até <b>R$ 250.000</b> "
        "por CPF e por instituição financeira, oferecendo <b>segurança</b> ao investidor. A rentabilidade pode ser <b>Pré-fixada</b> (taxa "
        "definida no início) ou <b>Pós-fixada</b> (geralmente atrelada a um percentual do CDI). "
        "Em relação às características de resgate, a <b>Liquidez</b> do CDB pode ser diária (ideal para reserva de emergência) ou "
        "apenas no vencimento (oferecendo historicamente maior retorno). A <b>tributação</b> segue a tabela regressiva do Imposto de "
        "Renda (<b>IR</b>), onde o imposto diminui quanto maior o prazo do investimento (chegando a 15% após 720 dias). O Imposto "
        "sobre Operações Financeiras (<b>IOF</b>) é isento para resgates feitos após 30 dias."
    )
    story.append(Paragraph(cdb_text, styles['CDBText']))
    
    story.append(PageBreak())
    
    # 6. Gráfico - Timeline de Liquidez 
    story.append(Paragraph("TIMELINE DE LIQUIDEZ: VALOR INVESTIDO POR VENCIMENTO", styles['SectionTitle'])) 
    
    img = Image(grafico_png(), width=160*mm, height=100*mm) # Aumentei um pouco a altura para acomodar o gráfico horizontal
    img.hAlign = 'CENTER'
    story.append(img)
    
    story.append(Spacer(1, 10*mm))

    # 7. Rodapé e Disclaimer 
    story.append(Paragraph(f"Simulação elaborada por <b>{nome_assessor}</b> em {data_simulacao.strftime('%d/%m/%Y')}", styles['Footer']))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("DISCLAIMER", styles['SectionTitle']))
    
    disclaimer_text = ("As informações presentes neste Material Técnico são baseadas em simulações e os resultados reais poderão ser significativamente diferentes. Os valores de liquidez representam o Capital Inicial Investido (sem considerar a rentabilidade) que estará disponível na data de vencimento.") 
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
