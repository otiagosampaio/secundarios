# ===================== FERRAMENTAS DA TABELA (Clonar e Limpar) =====================
st.subheader("Ferramentas da Tabela", divider='gray')
c_clone_button, c_clear_button = st.columns([1, 4]) # Ajuste de colunas

# Funções de ação
def clone_ultima_papel():
    if st.session_state.papeis:
        # Pega o índice da última linha (índice -1)
        original_papel = st.session_state.papeis[-1]
        
        # 1. Clona o dicionário
        cloned_papel = original_papel.copy()
        
        # 2. Modifica Ticker e Emissor para denotar uma cópia e garantir unicidade
        ticker_original = str(cloned_papel.get('Ticker', 'NOVO_PAPEL'))
        
        # Cria um novo Ticker único
        copy_count = 1
        new_ticker = f"{ticker_original} - CÓPIA {copy_count}"
        while any(p.get('Ticker') == new_ticker for p in st.session_state.papeis):
            copy_count += 1
            new_ticker = f"{ticker_original} - CÓPIA {copy_count}"

        cloned_papel['Ticker'] = new_ticker
        cloned_papel['Emissor'] = str(cloned_papel.get('Emissor', 'NOVO EMISSOR')) + ' (CÓPIA)'
        
        # 3. Adiciona o clone à lista
        st.session_state.papeis.append(cloned_papel)
        
        st.success(f"A última linha da tabela foi clonada com sucesso!")
        st.rerun()
    else:
        st.warning("Não há papéis na tabela para clonar.")

def clear_papeis():
    st.session_state.papeis = []
    st.rerun()


# 1. Clone Button (Clonar a Última Linha)
with c_clone_button:
    if st.session_state.papeis:
        st.button("Clonar Última Linha", on_click=clone_ultima_papel, type="secondary", use_container_width=True, help="Duplica a última linha da tabela.")
    else:
        st.button("Clonar Última Linha", disabled=True, use_container_width=True)


# 2. Clear Button
with c_clear_button:
    if st.button("Limpar Todos os Papéis", type="primary", use_container_width=True):
        clear_papeis()
    
st.markdown("---")
