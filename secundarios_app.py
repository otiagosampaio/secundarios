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
# Removidos: import uuid e import os

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
# Removido: CSV_FILE = 'propostas.csv' 

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
                # Usa 'Código' no erro para ser consistente com o frontend, embora a chave interna seja 'Ticker'
                return None, f"Formato de Data de Vencimento inválido para {papel.get('Ticker', 'novo papel')}"

    # Prazo (diferença de dias)
    prazo_dias = (data_vencimento - data_aplicacao).days
    
    if prazo_dias <= 0 or valor_investido <= 0 or taxa_input <= 0:
        return None, f"Dados inválidos para {papel.get('Ticker', 'novo papel')}"
    
    # Constante de cálculo financeiro (360 dias)
    dias_ano = 360
    
    # --- 2. TAXA REAL ---
    taxa_anual_real = taxa_input
    # CORREÇÃO DE SINTAXE: String literal completa
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
    
    # Ticker renomeado para Código 
    data_tabela_papeis = [
        [Paragraph("Emissor", styles['TableHeaderPDF']), Paragraph("Código", styles['TableHeaderPDF']), Paragraph("Valor Investido", styles['TableHeaderPDF']), Paragraph("Tipo", styles['TableHeaderPDF']), Paragraph("Taxa", styles['TableHeaderPDF']), Paragraph("Vencimento", styles['TableHeaderPDF']), Paragraph("Rendimento Líquido", styles['TableHeaderPDF'])]
    ]
    
    for p in papeis_para_grafico:
        vencimento_date = p['Data Vencimento']
        # Conversão de data segura para PDF
        if isinstance(vencimento_date, pd.Timestamp):
            vencimento_date = vencimento_date.date()
        elif isinstance(vencimento_date, str):
          
            try:
                vencimento_date = datetime.datetime.strptime(vencimento_date, '%Y-%m-%d').date()
            except:
                vencimento_date = st.session_state.data_aplicacao
        
        tipo_taxa_display = "Pós-fixado" if p['Tipo'] == 'Pós-fixado (% do CDI)' else p['Tipo']
        taxa_str = f"{p['Taxa']:.2f}% a.a." if p['Tipo'] == 'Pré-fixado' else f"{p['Taxa']:.2f}% do CDI"
        
        data_tabela_papeis.append([
            Paragraph(p['Emissor'], styles['TableCellPDF']),
            Paragraph(p['Ticker'], styles['TableCellPDF']), # Acesso pela chave interna 'Ticker'
            Paragraph(brl_pdf(p['Valor Investido']), styles['TableCellPDF']),
            Paragraph(tipo_taxa_display, styles['TableCellPDF']), 
            Paragraph(taxa_str, styles['TableCellPDF']),
    
            Paragraph(vencimento_date.strftime('%d/%m/%Y'), styles['TableCellPDF']),
            Paragraph(brl_pdf(p['Rendimento Líquido']), styles['TableCellPDF']),
        ])

    colWidths_papeis = [total_width_pdf*0.18, total_width_pdf*0.12, total_width_pdf*0.15, total_width_pdf*0.12, total_width_pdf*0.15, total_width_pdf*0.13, total_width_pdf*0.15]
    t_papeis = Table(data_tabela_papeis, colWidths=colWidths_papeis)
    t_papeis.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
      
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
    ]))
    story.append(t_papeis)
    story.append(Spacer(1, 5*mm))

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
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0, colors.transparent),
    ]))
    story.append(t_res_final)
    story.append(Spacer(1, 5*mm))

    # 5. Fundamentos do CDB
    story.append(HRFlowable(width="100%", thickness=0.5, lineCap='round', color=colors.lightgrey, spaceBefore=3*mm, spaceAfter=5*mm))
    story.append(Paragraph("FUNDAMENTOS DO CDB", styles['SectionTitle']))
    cdb_text = (
        "O <b>CDB</b> (Certificado de Depósito Bancário) é um título de <b>renda fixa</b> emitido por bancos para captar recursos. "
        "É considerado "
        "um <b>investimento de baixo risco</b> e conta com a <b>garantia do FGC</b> (Fundo Garantidor de Créditos), que cobre até <b>R$ 250.000</b> "
        "por CPF e por instituição financeira, oferecendo <b>segurança</b> ao investidor. "
        "A rentabilidade pode ser <b>Pré-fixada</b> (taxa "
        "definida no início) ou <b>Pós-fixada</b> (geralmente atrelada a um percentual do CDI). "
        "Em relação às características de resgate, a "
        "Liquidez do CDB pode ser diária (ideal para reserva de emergência) ou apenas no vencimento (oferecendo historicamente "
        "maior retorno). A tributação segue a tabela regressiva do Imposto de Renda (IR), onde o imposto diminui quanto maior o "
        "prazo do investimento (chegando a 15% após 720 dias). O Imposto sobre Operações Financeiras (IOF) é isento para "
        "resgates feitos após 30 dias."
    )
    story.append(Paragraph(cdb_text, styles['CDBText']))
    story.append(Spacer(1, 3*mm))

    # 6. Gráfico Timeline (Page Break)
    story.append(PageBreak())
    
    # Insere o gráfico aqui
    grafico_buf = grafico_png()
    story.append(Paragraph("TIMELINE DE LIQUIDEZ: VALOR INVESTIDO POR VENCIMENTO", styles['SectionTitle']))
    story.append(Image(grafico_buf, width=150*mm, height=75*mm, hAlign='CENTER'))
    story.append(Spacer(1, 10*mm))
    
    # 7. Tabela de Detalhe e Tributação
    story.append(Paragraph("DETALHAMENTO POR PAPEL E TRIBUTAÇÃO", styles['SectionTitle']))
    
    data_tabela_detalhe = [
        [Paragraph("Código", styles['TableHeaderPDF']), Paragraph("Vencimento", styles['TableHeaderPDF']), Paragraph("Montante Bruto", styles['TableHeaderPDF']), Paragraph("Alíquota IR", styles['TableHeaderPDF']), Paragraph("Imposto IR/IOF", styles['TableHeaderPDF']), Paragraph("Montante Líquido", styles['TableHeaderPDF'])]
    ]
    # Início do loop
    for p in papeis_para_grafico:
        vencimento_date = p['Data Vencimento']
        # Conversão de data segura para PDF
        if isinstance(vencimento_date, pd.Timestamp):
            vencimento_date = vencimento_date.date()
        elif isinstance(vencimento_date, str):
            try:
                vencimento_date = datetime.datetime.strptime(vencimento_date, '%Y-%m-%d').date()
            except:
                vencimento_date = st.session_state.data_aplicacao
        
        data_tabela_detalhe.append([
            Paragraph(p['Ticker'], styles['TableCellPDF']), # Acesso pela chave interna 'Ticker'
            Paragraph(vencimento_date.strftime('%d/%m/%Y'), styles['TableCellPDF']),
            Paragraph(brl_pdf(p['Montante Bruto']), styles['TableCellPDF']),
            Paragraph(f"{p['Alíquota IR']:.1f}%", styles['TableCellPDF']),
            Paragraph(brl_pdf(p['Total Impostos']), styles['TableCellPDF']),
            Paragraph(brl_pdf(p['Montante Líquido']), styles['TableCellPDF']),
        ])
    
    colWidths_detalhe = [total_width_pdf*0.15, total_width_pdf*0.15, total_width_pdf*0.2, total_width_pdf*0.15, total_width_pdf*0.2, total_width_pdf*0.15]
    t_detalhe = Table(data_tabela_detalhe, colWidths=colWidths_detalhe)
    t_detalhe.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_detalhe)
    story.append(Spacer(1, 5*mm))

    # --- FIM BLOCO ---
    # 8. Rodapé e Disclaimer
    story.append(HRFlowable(width="100%", thickness=0.5, lineCap='round', color=colors.lightgrey, spaceBefore=3*mm, spaceAfter=5*mm)) # Divisória
    story.append(Paragraph(f"Simulação elaborada por <b>{st.session_state['nome_assessor_selected_key'] if st.session_state['nome_assessor_selected_key'] != 'Selecione um Assessor...' else 'Assessor não informado'}</b> em {st.session_state['data_simulacao'].strftime('%d/%m/%Y')}", styles['Footer']))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("DISCLAIMER", styles['SectionTitle']))
    disclaimer_text = ("As informações presentes neste Material Técnico são baseadas em simulações e os resultados reais poderão ser significativamente diferentes. "
                       "Esta simulação não representa uma oferta de venda ou recomendação de investimento. Os produtos de Renda Fixa aqui apresentados "
                       "possuem risco e rentabilidade variáveis. Consulte sempre seu assessor de investimentos para tomar decisões. "
                       "A garantia do FGC de R$ 250.000 por CPF, por emissor e por instituição está sujeita às regras e limites atuais do FGC. "
                       "A taxa CDI Benchmark é uma referência de mercado e não garante a taxa real em aplicações futuras. "
                       "A rentabilidade histórica não garante rentabilidade futura.")
    story.append(Paragraph(disclaimer_text, styles['Disclaimer']))
    
    doc.build(story)
    
    return buffer.getvalue()


# ===================== INÍCIO DA APLICAÇÃO STREAMLIT =====================

# 1. Inicialização do Session State
if 'papeis' not in st.session_state:
    st.session_state.papeis = []
if 'nome_cliente' not in st.session_state:
    st.session_state.nome_cliente = "Cliente Exemplo"
if 'codigo_cliente' not in st.session_state:
    st.session_state.codigo_cliente = "000000"
if 'data_simulacao' not in st.session_state:
    st.session_state.data_simulacao = datetime.date.today()
if 'data_aplicacao' not in st.session_state:
    st.session_state.data_aplicacao = datetime.date.today()
if 'cdi_benchmark_geral' not in st.session_state:
    st.session_state.cdi_benchmark_geral = TAXA_CDI_MERCADO
if 'nome_assessor_selected_key' not in st.session_state:
    st.session_state.nome_assessor_selected_key = ASSESSORES_LISTA[0] # Selecione um Assessor...

# Exibição do Logo (para Streamlit)
st.image(URL_LOGO_WHITE)

st.title("Simulador de Renda Fixa FGC")
st.markdown("Cálculo consolidado de impostos (IR/IOF) e rentabilidade líquida para múltiplos CDBs.")


# ===================== DADOS GERAIS DA SIMULAÇÃO =====================
with st.container(border=True):
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
    # Garante que 'Qtde' existe, ou usa 1.0 como padrão se for a primeira vez
    if 'Qtde' not in df_papeis.columns:
        df_papeis['Qtde'] = 1.0
    # COERÇÃO INICIAL MAIS SEGURA PARA EXIBIÇÃO:
    df_papeis['Data Vencimento'] = pd.to_datetime(df_papeis['Data Vencimento'], errors='coerce').dt.date
    df_papeis['Valor'] = pd.to_numeric(df_papeis['Valor'], errors='coerce').round(2)
    df_papeis['Qtde'] = pd.to_numeric(df_papeis['Qtde'], errors='coerce').fillna(1.0).round(0) # Tratamento de Qtde
    df_papeis['Taxa'] = pd.to_numeric(df_papeis['Taxa'], errors='coerce').round(2)
    # Remove linhas com NaN nos campos críticos para evitar que o data_editor quebre ao carregar
    df_papeis = df_papeis.dropna(subset=['Valor', 'Taxa', 'Data Vencimento'])
else:
    # Adiciona 'Qtde' na criação do DataFrame vazio
    df_papeis = pd.DataFrame(columns=['Emissor', 'Ticker', 'Valor', 'Qtde', 'Tipo', 'Taxa', 'Data Vencimento'])

# Renomear colunas para exibição amigável (Ticker -> Código)
df_papeis_edit = df_papeis.rename(columns={
    'Emissor': 'Emissor',
    'Ticker': 'Código',
    'Valor': 'Valor Investido (R$)',
    'Qtde': 'Qtde.', # Mapeamento da Qtde
    'Tipo': 'Tipo de Taxa',
    'Taxa': 'Taxa (%)',
    'Vencimento': 'Vencimento',
})

# ORDEM: Inclui 'Qtde.'
colunas_data_editor = ['Emissor', 'Código', 'Valor Investido (R$)', 'Qtde.', 'Tipo de Taxa', 'Taxa (%)', 'Vencimento']

st.info("Para **editar** um papel, clique duas vezes na célula. Para **remover**, selecione a linha e pressione o botão `Del` no teclado ou o ícone 🗑️ na tabela. Para **adicionar** um novo papel, use o botão `+` no rodapé da tabela.")


# INÍCIO DO BLOCO DE CONFIGURAÇÃO CORRIGIDO
column_config_papeis = {
    # CORREÇÃO: Emissor como campo de texto livre
    "Emissor": st.column_config.TextColumn( 
        "Emissor",
        help="Nome da instituição emissora do papel",
        required=True
    ),
    "Código": st.column_config.TextColumn(
        "Código",
        help="Ticker/código de identificação do papel",
        required=True
    ),
    "Valor Investido (R$)": st.column_config.NumberColumn(
        "Valor Investido (R$)",
        min_value=0.01,
        format="R$ %.2f",
        required=True
    ),
    "Qtde.": st.column_config.NumberColumn(
        "Qtde.",
        min_value=1,
        step=1,
        format="%d",
        required=True
    ),
    "Tipo de Taxa": st.column_config.SelectboxColumn(
        "Tipo de Taxa",
        options=["Pré-fixado", "Pós-fixado (% do CDI)"],
        required=True
    ),
    "Taxa (%)": st.column_config.NumberColumn(
        "Taxa (%)",
        min_value=0.01,
        format="%.2f",
        required=True
    ),
    "Vencimento": st.column_config.DateColumn(
        "Vencimento",
        min_value=datetime.date.today() - relativedelta(days=1), # Permite o dia de hoje
        format="DD/MM/YYYY",
        required=True
    ),
}
# FIM DO BLOCO DE CONFIGURAÇÃO CORRIGIDO

# FIM DA CONFIGURAÇÃO DO DATA EDITOR (retorna um DataFrame)
edited_df = st.data_editor(
    df_papeis_edit,
    num_rows="dynamic",
    column_config=column_config_papeis,
    column_order=colunas_data_editor,
    key="data_editor_papeis"
)

# =========================================================
# BLOCO SUBSTITUTO SEGURO (MANTIDO para garantir estabilidade)
# =========================================================

df_edited = edited_df
papeis_anteriores = st.session_state.papeis.copy() # Copia a versão anterior para comparação

# 1. Renomeia colunas de volta para chaves internas
df_edited = df_edited.rename(columns={
    'Código': 'Ticker',
    'Valor Investido (R$)': 'Valor',
    'Qtde.': 'Qtde',
    'Tipo de Taxa': 'Tipo',
    'Taxa (%)': 'Taxa',
    'Vencimento': 'Data Vencimento',
})

# 2. Força tipos com tratamento de erro (errors='coerce')
try:
    df_clean = df_edited.copy()
    
    # pd.to_numeric() converte listas/sequências/strings inválidas para NaN, resolvendo o ValueError
    df_clean['Valor'] = pd.to_numeric(df_clean['Valor'], errors='coerce')
    df_clean['Taxa'] = pd.to_numeric(df_clean['Taxa'], errors='coerce')
    # Coerce + fillna(1) para garantir Qtde mínima de 1 se for NaN
    df_clean['Qtde'] = pd.to_numeric(df_clean['Qtde'], errors='coerce').fillna(1)
    df_clean['Data Vencimento'] = pd.to_datetime(df_clean['Data Vencimento'], errors='coerce')
    
    # 3. Remove linhas inválidas/corrompidas (dropa os NaNs gerados na coerção)
    df_clean = df_clean.dropna(subset=['Emissor', 'Ticker', 'Valor', 'Taxa', 'Data Vencimento'])
    # Remove linhas com valores <= 0
    df_clean = df_clean[(df_clean['Valor'] > 0) & (df_clean['Taxa'] > 0)]
    
    # 4. Tipos finais garantidos
    df_clean['Valor'] = df_clean['Valor'].round(2).astype(float)
    df_clean['Taxa'] = df_clean['Taxa'].round(4).astype(float) # Round(4) para precisão da taxa
    df_clean['Qtde'] = df_clean['Qtde'].astype(int) 
    df_clean['Data Vencimento'] = df_clean['Data Vencimento'].dt.date 
    
    new_papeis = df_clean.to_dict('records')
    
    # 5. Comparação Profunda antes do rerun
    if len(new_papeis) != len(papeis_anteriores) or \
       any(a != b for a, b in zip(new_papeis, papeis_anteriores)):
        
        st.session_state.papeis = new_papeis
        st.rerun()

except Exception as e:
    # 6. Tratamento de erro crítico 
    if str(e) == "The truth value of a Series is ambiguous. Use a.empty, a.bool(), a.item(), a.any() or a.all().":
        # Se for o erro de ambiguidade do pandas (rara, mas possível), apenas tenta recarregar
        st.session_state.papeis = [] 
        st.rerun()
    else:
        st.error(f"Erro crítico ao processar a tabela. Dados corrompidos foram descartados. Detalhe: {e}")
        st.session_state.papeis = [] 
        st.rerun()
    
# =========================================================

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
        # Garantir os tipos esperados para o cálculo
        papel_temp['Valor'] = float(papel_temp['Valor'])
        papel_temp['Taxa'] = float(papel_temp['Taxa'])
        papel_temp['Qtde'] = float(papel_temp.get('Qtde', 1.0)) 
    except (ValueError, TypeError):
        continue

    resultado, erro = calcular_papel(papel_temp, st.session_state.data_aplicacao, current_cdi_benchmark)

    if resultado:
        papel_temp.update(resultado)
        papeis_para_grafico.append(papel_temp)
        resultados_calculados.append(resultado)
    elif erro:
        st.warning(f"Atenção: Papel **{papel.get('Ticker', 'novo papel')}** ignorado na simulação. **{erro}**")

if not resultados_calculados:
    st.error("Não há papéis válidos para consolidar. Verifique os dados inseridos (Valor > R$0, Taxa > 0% e Vencimento futuro).")
    st.stop()

total_investido = sum(r['Valor Investido'] for r in resultados_calculados)
total_bruto = sum(r['Montante Bruto'] for r in resultados_calculados)
total_impostos = sum(r['Total Impostos'] for r in resultados_calculados)
total_liquido = sum(r['Montante Líquido'] for r in resultados_calculados)

# Calculando a rentabilidade efetiva: (Rendimento Líquido / Total Investido) * 100
rendimento_liquido_total = total_liquido - total_investido
rentabilidade_efetiva = (rendimento_liquido_total / total_investido) * 100 if total_investido > 0 else 0.0


# ===================== EXIBIÇÃO DE RESULTADOS =====================
st.subheader("Resultados Consolidados", divider='green')

col_1, col_2, col_3, col_4, col_5 = st.columns(5)

with col_1:
    st.metric("Total Investido", brl(total_investido))
with col_2:
    st.metric("Montante Bruto", brl(total_bruto))
with col_3:
    st.metric("Total Impostos (IR/IOF)", brl(total_impostos))
with col_4:
    st.metric("Montante Líquido", brl(total_liquido))
with col_5:
    st.metric("Rentabilidade Líquida Efetiva", f"{rentabilidade_efetiva:.2f}%")


st.markdown("---") 

# ===================== GERAÇÃO E DOWNLOAD DO PDF =====================
st.subheader("Gerar Proposta Consolidada em PDF", divider='gray')

if st.session_state['nome_assessor_selected_key'] == ASSESSORES_LISTA[0] or not st.session_state['nome_cliente']:
    st.warning("Preencha o **Nome do Cliente** e selecione o **Nome do Assessor** nos 'Dados Gerais da Simulação' para gerar a proposta.")
else:
    with st.spinner("Gerando sua proposta premium consolidada..."):
        try:
            # 1. GERAR PDF
            pdf_data = criar_pdf_secundarios()
            b64 = base64.b64encode(pdf_data).decode()
            nome_arq = f"Proposta_RendaFixa_{st.session_state['nome_cliente'].replace(' ', '_')}.pdf"
            
            # Botão de download simples (sem referência a ID de simulação)
            # Usa o estilo de botão primário
            href = f'<a href="data:application/pdf;base64,{b64}" download="{nome_arq}" class="stButton" style="text-decoration:none;"><button data-testid="baseButton-primary" style="width:100%;">BAIXAR PROPOSTA CONSOLIDADA</button></a>'
            
            st.markdown(href, unsafe_allow_html=True)
            st.success("Proposta premium gerada com sucesso! Clique no botão acima para baixar.")
            
        except Exception as e:
            # Tratamento de erro
            if "papéis válidos" in str(e):
                st.error("Ocorreu um erro ao gerar o PDF. Adicione pelo menos um papel válido na tabela (Valor > R$0, Taxa > 0% e Vencimento futuro).")
            else:
                # Em caso de erro desconhecido, mostra a mensagem genérica
                st.error(f"Ocorreu um erro inesperado ao gerar o PDF. Por favor, tente novamente. Detalhe técnico: {e}")

# Removidos: Mensagem Automática de Execução e Consulta CSV.

# ===================== RODAPÉ STREAMLIT =====================
st.markdown(
    f"""<p style='text-align:center; margin-top:40px; color:#666;'>Simulação elaborada por <b>{st.session_state['nome_assessor_selected_key'] if st.session_state['nome_assessor_selected_key'] != 'Selecione um Assessor...' else 'Assessor não informado'}</b> em {st.session_state['data_simulacao'].strftime('%d/%m/%Y')}</p>""",
    unsafe_allow_html=True
)
