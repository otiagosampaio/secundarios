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
# Mantenha as cores originais ou substitua com a identidade visual do seu novo projeto
URL_LOGO_WHITE = "https://ik.imagekit.io/aufhkvnry/logo-traders__bg-white.png" # Altere para o seu logo
TEXTO_PRINCIPAL_ST = "#222222"
VERDE_DESTAQUE = '#2E8B57'
AZUL_TABELA_PDF = colors.HexColor("#864df4")
COR_PRIMARIA_FORM = '#6B48FF' # Cor para o botão de adicionar
TAXA_CDI_MERCADO = 14.90 # Valor de CDI atual

# ===================== FUNÇÕES AUXILIARES (Adaptadas) =====================

def carregar_logo():
    # Mantendo sua função original robusta de carregamento de logo para ReportLab
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
    # Remove R$ e pontos de milhar, substitui a última vírgula por ponto decimal
    valor_limpo = valor_str.replace('R$', '').replace('.', '').replace(',', '.', 1)
    
    try:
        valor_float = float(valor_limpo)
        # Formata para string padrão americano e depois inverte para o brasileiro
        return f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return "0,00"

def desformatar_moeda(valor_formatado):
    """Converte o formato brasileiro (ponto de milhar, vírgula decimal) para float."""
    valor_float_str = valor_formatado.replace('R$', '').replace('.', '').replace(',', '.')
    try:
        return float(valor_float_str)
    except ValueError:
        return 0.0

brl = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
brl_pdf = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") # Alias para PDF

# ===================== CÁLCULO PARA UM ÚNICO PAPEL =====================

def calcular_papel(papel, data_aplicacao, taxa_cdi_benchmark):
    """Realiza os cálculos de rendimento, IR e IOF para um único papel."""
    
    # 1. Parâmetros
    valor_investido = papel['Valor']
    data_vencimento = papel['Data Vencimento']
    tipo = papel['Tipo']
    taxa_input = papel['Taxa']

    prazo_dias = (data_vencimento - data_aplicacao).days
    
    if prazo_dias <= 0:
        return None, "Data de resgate inválida"

    # 2. Determinação da Taxa Diária e Base de Dias
    dias_ano = 360 # Geralmente usado para cálculo de Renda Fixa
    taxa_anual_real = taxa_input

    if tipo == "Pós-fixado (% do CDI)":
        # A taxa input é o percentual do CDI, a taxa_anual_real é a taxa final em a.a.
        taxa_anual_real = taxa_cdi_benchmark * (taxa_input / 100)
    
    # Taxa diária calculada por juros compostos
    taxa_diaria = (1 + taxa_anual_real/100)**(1/dias_ano) - 1

    # 3. Cálculo Bruto
    montante_bruto = valor_investido * (1 + taxa_diaria)**prazo_dias
    rendimento_bruto = montante_bruto - valor_investido

    # 4. IOF (sobre o rendimento bruto)
    rendimento_apos_iof = rendimento_bruto
    imposto_iof = 0
    if prazo_dias < 30:
        # Tabela de IOF adaptada do seu código original
        iof_tab = [0.96,0.93,0.90,0.86,0.83,0.80,0.76,0.73,0.70,0.66,0.63,0.60,0.56,0.53,0.50,
                   0.46,0.43,0.40,0.36,0.33,0.30,0.26,0.23,0.20,0.16,0.13,0.10,0.06,0.03,0.00]
        aliquota_iof = iof_tab[prazo_dias-1]
        imposto_iof = rendimento_bruto * aliquota_iof
        rendimento_apos_iof = rendimento_bruto - imposto_iof

    # 5. Imposto de Renda (IR) - sobre o rendimento líquido de IOF
    aliquota_ir = 22.5 if prazo_dias <= 180 else 20.0 if prazo_dias <= 360 else 17.5 if prazo_dias <= 720 else 15.0
    imposto_ir = rendimento_apos_iof * (aliquota_ir/100)
    
    # 6. Resultado Líquido
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
st.set_page_config(page_title="Traders Secundários - Calculadora", layout="wide")

# Inicializa o session state para a lista de papéis e o valor de investimento base
if 'papeis' not in st.session_state:
    st.session_state['papeis'] = []
if 'valor_input' not in st.session_state:
    st.session_state['valor_input'] = "500.000,00" # Valor base para o formulário de inclusão

# ===================== LOGO + TÍTULO (Streamlit Display) =====================
st.markdown(
    f"""<div style="text-align: center; margin: 10px 0;">
        <img src="{URL_LOGO_WHITE}" width="300">
    </div>""",
    unsafe_allow_html=True
)
st.markdown(f"<h2 style='text-align: center; color: {TEXTO_PRINCIPAL_ST};'>Calculadora de Simulação de Papéis Secundários</h2>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center; font-size: 17px; margin-bottom: 30px;'>Adicione os papéis e simule o resultado consolidado para o cliente.</p>", unsafe_allow_html=True)
st.markdown("---")

# ===================== DADOS GERAIS DA SIMULAÇÃO =====================
st.subheader("Dados Gerais da Simulação")
c1, c2, c3 = st.columns(3)

with c1:
    nome_cliente = st.text_input("Nome do Cliente", "João Silva")
    nome_assessor = st.text_input("Nome do Assessor", "Seu Nome")

with c2:
    data_simulacao = st.date_input("Data da Simulação", datetime.date.today(), format="DD/MM/YYYY")
    data_aplicacao = st.date_input("Data de Aplicação/Compra", datetime.date.today(), format="DD/MM/YYYY")

with c3:
    taxa_cdi_benchmark = st.number_input("Taxa CDI Anual (Benchmark) (%)", value=TAXA_CDI_MERCADO, step=0.05)
    
st.markdown("---")

# ===================== ADICIONAR NOVO PAPEL (FORMULÁRIO) =====================

st.subheader("Inclusão de Novo Papel")

# Função para adicionar o papel (chamada no submit do form)
def adicionar_papel():
    valor_investido_float = desformatar_moeda(formatar_moeda_input(st.session_state.valor_bruto_input_sec))

    if valor_investido_float <= 0:
        st.error("O valor investido deve ser maior que zero.")
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
    # Limpa campos do formulário para facilitar a próxima inclusão (opcional)
    st.session_state.valor_bruto_input_sec = "0,00"
    st.session_state.taxa_sec = 0.0

with st.form("form_papel", clear_on_submit=False):
    col_e1, col_e2, col_e3 = st.columns(3)
    
    with col_e1:
        st.text_input("Emissor", value="Banco Alfa S.A.", key="emissor_sec")
        st.text_input("Ticker/Código", value="CDB1234", key="ticker_sec")
    
    with col_e2:
        tipo_cdb_sec = st.selectbox("Tipo de Taxa", ["Pré-fixado", "Pós-fixado (% do CDI)"], key="tipo_cdb_sec")
        
        # Input de Taxa
        if tipo_cdb_sec == "Pós-fixado (% do CDI)":
            st.number_input("Percentual do CDI (%)", value=125.0, step=1.0, key="taxa_sec")
        else:
            st.number_input("Taxa Pré-fixada anual (%)", value=17.00, step=0.05, key="taxa_sec")
            
    with col_e3:
        st.date_input("Data de Vencimento", data_aplicacao + relativedelta(months=+12), format="DD/MM/YYYY", key="vencimento_sec")
        
        # Valor investido (input com formatação)
        valor_investido_str = st.text_input(
            label="Valor investido neste papel", 
            value=st.session_state['valor_input'], 
            placeholder="Digite o valor",
            key="valor_bruto_input_sec"
        )
        
    st.markdown(f"<p style='color: {TEXTO_PRINCIPAL_ST}; margin-top: 10px;'>Valor a ser adicionado: <b>R$ {formatar_moeda_input(valor_investido_str)}</b></p>", unsafe_allow_html=True)

    st.form_submit_button("ADICIONAR PAPEL À SIMULAÇÃO", on_click=adicionar_papel, type="secondary", use_container_width=True)

st.markdown("---")

# ===================== TABELA DE PAPÉIS ADICIONADOS =====================

if not st.session_state.papeis:
    st.info("Nenhum papel adicionado. Use o formulário acima para começar a simulação.")
    st.stop()
    
st.subheader("Papéis Incluídos para Simulação")

# Criação de um DataFrame para exibir a lista de papéis
df_papeis = pd.DataFrame(st.session_state.papeis)

# Adaptação para exibição
df_papeis['Taxa/CDI'] = df_papeis.apply(
    lambda row: f"{row['Taxa']:.2f}% a.a." if row['Tipo'] == 'Pré-fixado' else f"{row['Taxa']:.2f}% do CDI", axis=1
)
df_papeis['Valor'] = df_papeis['Valor'].apply(brl)
df_papeis['Vencimento'] = df_papeis['Data Vencimento'].dt.strftime('%d/%m/%Y')

# Colunas a exibir
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

# Botão de limpeza
if st.button("Limpar Lista de Papéis", type="primary"):
    st.session_state.papeis = []
    st.experimental_rerun()
    
st.markdown("---")

# ===================== CÁLCULOS CONSOLIDADOS =====================

resultados_calculados = []
for papel in st.session_state.papeis:
    resultado, erro = calcular_papel(papel, data_aplicacao, taxa_cdi_benchmark)
    if resultado:
        papel.update(resultado) # Adiciona os resultados calculados ao dicionário do papel
        resultados_calculados.append(resultado)

if not resultados_calculados:
    st.error("Erro nos dados de vencimento ou aplicação. Verifique se a data de vencimento é posterior à aplicação.")
    st.stop()

# Consolidação dos Totais
total_investido = sum(r['Valor Investido'] for r in resultados_calculados)
total_bruto = sum(r['Montante Bruto'] for r in resultados_calculados)
total_impostos = sum(r['Total Impostos'] for r in resultados_calculados)
total_liquido = sum(r['Montante Líquido'] for r in resultados_calculados)
rendimento_liquido_total = total_liquido - total_investido

# Cálculo da Rentabilidade Efetiva
rentabilidade_efetiva = (rendimento_liquido_total / total_investido) * 100 if total_investido > 0 else 0.0

st.subheader("Resultado Consolidado da Simulação")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Investido", brl(total_investido))
c2.metric("Montante Bruto", brl(total_bruto))
c3.metric("Impostos (IR + IOF)", brl(total_impostos))
c4.metric("Montante Líquido", brl(total_liquido), delta=f"{brl(rendimento_liquido_total)} (Rendimento)")

st.markdown(f"**Rentabilidade Líquida Efetiva:** <span style='color:{VERDE_DESTAQUE}; font-size: 1.2em;'>{rentabilidade_efetiva:.2f}%</span>", unsafe_allow_html=True)
st.markdown("---")

# ===================== GRÁFICO (Simplificado) =====================
# Como temos múltiplos vencimentos e taxas, um gráfico de barras é mais adequado
# do que a linha do tempo do projeto original.

st.subheader("Visão por Papel (Rendimento Líquido)")

df_resumo = pd.DataFrame(st.session_state.papeis)
df_resumo['Rendimento'] = df_resumo['Rendimento Líquido']
df_resumo['Label'] = df_resumo['Ticker'] + ' (' + df_resumo['Data Vencimento'].dt.strftime('%Y') + ')'

fig, ax = plt.subplots(figsize=(10, 5))
ax.bar(df_resumo['Label'], df_resumo['Rendimento'], color=COR_PRIMARIA_FORM, alpha=0.7)
ax.set_title("Rendimento Líquido por Papel")
ax.set_ylabel("Rendimento Líquido (R$)")
ax.tick_params(axis='x', rotation=45)
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
st.pyplot(fig)

# ===================== PDF GERAÇÃO (Adaptado para Múltiplos Papéis) =====================

def grafico_png():
    # Salva o gráfico de barras para o PDF
    buf = BytesIO()
    fig.set_facecolor('white')
    ax.set_facecolor('white')
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    # Restaura cores para Streamlit (opcional)
    fig.set_facecolor(st.config.get_option('theme.backgroundColor'))
    ax.set_facecolor(st.config.get_option('theme.backgroundColor'))
    return buf

def criar_pdf_secundarios():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    story = []
    styles = getSampleStyleSheet()
    
    # Estilos (reutilizando seus estilos originais)
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
         Paragraph("CDI Benchmark", styles['DataLabel']), Paragraph(f"{taxa_cdi_benchmark:.2f}% a.a.", styles['DataValue'])],
    ]
    t_dados = Table(data_geral, colWidths=[80, 120, 80, 120])
    t_dados.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('LEFTPADDING', (0,0), (-1,-1), 10)]))
    story.append(t_dados)
    story.append(Spacer(1, 5*mm))

    # 3. Tabela de Papéis
    story.append(Paragraph("DETALHES DOS PAPÉIS INCLUÍDOS", styles['SectionTitle']))
    
    data_tabela_papeis = [
        ["Emissor", "Ticker", "Valor Investido", "Tipo", "Taxa", "Vencimento", "Rendimento Líquido"]
    ]
    
    for p in st.session_state.papeis:
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

    t_papeis = Table(data_tabela_papeis, colWidths=[65, 45, 60, 45, 60, 45, 70])
    t_papeis.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
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
        # Linha de Rentabilidade Efetiva
        [Paragraph(f"Rentabilidade Líquida Efetiva: <font size='10' color='white'><b>{rentabilidade_efetiva:.2f}%</b></font>", styles['ResultTitleLarge']), "", "", ""],
    ]
    
    total_width = A4[0] - 30*mm
    colWidths_4 = [total_width/4] * 4
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
    story.append(Paragraph("PROJEÇÃO DE RENDIMENTO LÍQUIDO POR PAPEL", styles['SectionTitle']))
    
    img = Image(grafico_png(), width=180*mm, height=90*mm)
    img.hAlign = 'CENTER'
    story.append(img)
    
    story.append(Spacer(1, 10*mm))

    # 6. Rodapé e Disclaimer
    story.append(Paragraph(f"Simulação elaborada por <b>{nome_assessor}</b> em {data_simulacao.strftime('%d/%m/%Y')}", styles['Footer']))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("DISCLAIMER", styles['SectionTitle']))
    disclaimer_text = ("... (Insira o disclaimer legal completo da Traders DTVM aqui) ...") # Use seu disclaimer original
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
