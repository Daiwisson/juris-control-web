import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Juris Control Web", page_icon="⚖️", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
# A magia acontece aqui. O ttl=0 garante que ele não fique lendo dados velhos (cache)
conn = st.connection("gsheets", type=GSheetsConnection)

def ler_dados(aba):
    try:
        return conn.read(worksheet=aba, usecols=list(range(8)), ttl=0).dropna(how="all")
    except:
        return pd.DataFrame()

def salvar_dados(aba, df_novo):
    conn.update(worksheet=aba, data=df_novo)
    st.cache_data.clear() # Limpa memória para ver atualização na hora

# --- MENU LATERAL ---
st.sidebar.title("⚖️ Juris Control Cloud")
menu = st.sidebar.radio("Menu", ["Dashboard", "Clientes", "Processos", "Agenda", "Financeiro"])
st.sidebar.info("Conectado ao Google Sheets 🟢")

# --- 1. DASHBOARD ---
if menu == "Dashboard":
    st.title("📊 Visão Geral")
    
    # Lê as planilhas
    df_cli = ler_dados("clientes")
    df_proc = ler_dados("processos")
    df_fin = ler_dados("financeiro")
    
    # Cálculos
    qtd_cli = len(df_cli)
    qtd_ativos = len(df_proc[df_proc['status'] == 'Ativo']) if not df_proc.empty else 0
    
    val_receber = 0.0
    if not df_fin.empty:
        # Limpa o R$ e converte para numero
        receber_df = df_fin[df_fin['pago'] == False]  # Ajuste para booleano
        val_receber = receber_df['valor'].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Clientes", qtd_cli, border=True)
    c2.metric("Processos Ativos", qtd_ativos, border=True)
    c3.metric("A Receber", f"R$ {val_receber:,.2f}", border=True)

    st.divider()
    st.subheader("🚨 Alertas de Inércia (> 10 dias)")
    
    if not df_proc.empty and 'data_uv' in df_proc.columns:
        ativos = df_proc[df_proc['status'] == 'Ativo'].copy()
        alertas = []
        hoje = datetime.now().date()
        
        for idx, row in ativos.iterrows():
            try:
                # Tenta ler a data da planilha
                dt_uv = pd.to_datetime(row['data_uv'], dayfirst=True).date()
                dias = (hoje - dt_uv).days
                if dias > 10:
                    alertas.append({"Processo": row['numero'], "Dias Parado": dias})
            except:
                pass # Ignora datas em branco ou erro
        
        if alertas:
            st.error(f"{len(alertas)} processos precisando de atenção!")
            st.dataframe(pd.DataFrame(alertas), use_container_width=True)
        else:
            st.success("Diligências em dia!")

# --- 2. CLIENTES ---
elif menu == "Clientes":
    st.title("👥 Clientes")
    tab1, tab2 = st.tabs(["Novo", "Lista"])
    
    df = ler_dados("clientes")
    
    with tab1:
        with st.form("add_cli"):
            nome = st.text_input("Nome")
            cpf = st.text_input("CPF")
            mail = st.text_input("Email")
            zap = st.text_input("WhatsApp")
            end = st.text_area("Endereço")
            if st.form_submit_button("Salvar"):
                novo_id = df['id'].max() + 1 if not df.empty and 'id' in df.columns and pd.notna(df['id'].max()) else 1
                novo_dado = pd.DataFrame([{
                    "id": novo_id, "nome": nome, "cpf": cpf, 
                    "email": mail, "zap": zap, "endereco": end
                }])
                df_final = pd.concat([df, novo_dado], ignore_index=True)
                salvar_dados("clientes", df_final)
                st.success("Salvo no Google Sheets!")
                
    with tab2:
        st.dataframe(df, use_container_width=True)

# --- 3. PROCESSOS ---
elif menu == "Processos":
    st.title("⚖️ Gestão de Processos")
    
    # Carrega dados
    df_processos = conn.read(worksheet="Processos", usecols=list(range(6)), ttl=5)
    df_processos = df_processos.dropna(how="all")
    # Carrega agenda também para mostrar na linha do tempo
    df_agenda = conn.read(worksheet="Agenda", usecols=list(range(6)), ttl=5)

    # Criação das Abas
    aba_novo, aba_gestao, aba_lista = st.tabs(["➕ Novo Processo", "📂 Gestão do Caso", "📋 Lista Geral"])

    # --- ABA 1: NOVO PROCESSO ---
    with aba_novo:
        st.subheader("Cadastrar Novo Processo")
        with st.form("form_processo"):
            num_proc = st.text_input("Número do Processo (CNJ)")
            # Carrega clientes para o selectbox
            df_clientes = conn.read(worksheet="Clientes", usecols=list(range(5)), ttl=5)
            lista_clientes = df_clientes["Nome"].tolist() if not df_clientes.empty else []
            cliente_proc = st.selectbox("Cliente", lista_clientes)
            
            acao_proc = st.text_input("Ação / Assunto")
            juizo_proc = st.text_input("Vara / Juízo")
            status_proc = st.selectbox("Status", ["Ativo", "Suspenso", "Arquivado", "Em Recurso"])
            
            submit_proc = st.form_submit_button("Salvar Processo")

            if submit_proc:
                # Gera ID sequencial
                novo_id = 1
                if not df_processos.empty:
                    # Tenta converter para int para achar o maximo
                    ids_existentes = pd.to_numeric(df_processos["ID"], errors='coerce').fillna(0)
                    novo_id = int(ids_existentes.max()) + 1
                
                novo_processo = pd.DataFrame([{
                    "ID": novo_id,
                    "Número": num_proc,
                    "Cliente": cliente_proc,
                    "Ação": acao_proc,
                    "Juízo": juizo_proc,
                    "Status": status_proc
                }])
                
                df_final_proc = pd.concat([df_processos, novo_processo], ignore_index=True)
                conn.update(worksheet="Processos", data=df_final_proc)
                st.success(f"Processo {num_proc} cadastrado!")
                st.rerun()

    # --- ABA 2: GESTÃO (Detalhes + Agenda) ---
    with aba_gestao:
        st.header("Consultar e Gerir Caso")
        if not df_processos.empty:
            # Prepara lista para seleção
            df_processos['ID'] = pd.to_numeric(df_processos['ID'], errors='coerce').fillna(0).astype(int)
            lista_selecao = df_processos['ID'].astype(str) + " - " + df_processos['Número'].astype(str) + " (" + df_processos['Cliente'].astype(str) + ")"
            
            escolha = st.selectbox("Selecione o Processo", options=lista_selecao)
            
            if escolha:
                # Pega ID (com a correção do float/int que fizemos antes)
                pid = int(float(escolha.split(" - ")[0]))
                
                # Filtra os dados
                filtro = df_processos[df_processos["ID"] == pid]
                if not filtro.empty:
                    proc_atual = filtro.iloc[0]
                    
                    st.divider()
                    c1, c2, c3 = st.columns(3)
                    c1.metric("ID Interno", proc_atual['ID'])
                    c2.metric("Status", proc_atual['Status'])
                    c3.write(f"**Cliente:** {proc_atual['Cliente']}")
                    
                    st.write(f"**Assunto:** {proc_atual['Ação']}")
                    st.write(f"**Juízo:** {proc_atual['Juízo']}")
                    st.code(proc_atual['Número'], language="text") # Facilita copiar o número

                    # --- LINHA DO TEMPO DA AGENDA ---
                    st.divider()
                    st.subheader("📅 Histórico e Prazos do Processo")
                    
                    # Filtra a agenda pelo ID do processo selecionado
                    if not df_agenda.empty and "ID_Processo" in df_agenda.columns:
                        # Garante que tudo é texto para comparar
                        df_agenda["ID_Processo"] = df_agenda["ID_Processo"].astype(str).replace("nan", "").replace(".0", "")
                        pid_str = str(pid)
                        
                        eventos_do_caso = df_agenda[df_agenda["ID_Processo"] == pid_str]
                        
                        if not eventos_do_caso.empty:
                            for i, row in eventos_do_caso.iterrows():
                                st.info(f"🗓️ **{row['Data']}** ({row['Hora']}) - **{row['Evento']}**\n\n_{row['Obs']}_")
                        else:
                            st.caption("Nenhum evento vinculado a este processo.")
                    else:
                        st.warning("Coluna ID_Processo não encontrada na aba Agenda.")

    # --- ABA 3: LISTA GERAL ---
    with aba_lista:
        st.header("Panorama Geral")
        st.dataframe(
            df_processos, 
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn(format="%d")
            }
        )

# === 4. AGENDA ===
elif menu == "Agenda":
    st.title("📅 Agenda e Prazos")
    
    # Carrega dados atualizados
    df_agenda = conn.read(worksheet="Agenda", usecols=list(range(6)), ttl=5)
    df_processos = conn.read(worksheet="Processos", usecols=list(range(6)), ttl=5)
    df_agenda = df_agenda.dropna(how="all")
    
    # --- FORMULÁRIO DE NOVO EVENTO ---
    with st.expander("➕ Novo Evento / Compromisso", expanded=True):
        with st.form("form_agenda"):
            col_a, col_b = st.columns(2)
            nome_evento = col_a.text_input("Título do Evento (Ex: Audiência)")
            tipo_evento = col_b.selectbox("Tipo", ["Audiência", "Prazo", "Reunião", "Diligência", "Outro"])
            
            col_c, col_d = st.columns(2)
            data_evento = col_c.date_input("Data", datetime.today())
            hora_evento = col_d.time_input("Hora", datetime.now().time())
            
            # --- VÍNCULO COM PROCESSO ---
            # Cria lista de processos para o dropdown
            # Tratamento de erro caso a tabela de processos esteja vazia
            if not df_processos.empty:
                df_processos['ID'] = pd.to_numeric(df_processos['ID'], errors='coerce').fillna(0).astype(int)
                lista_procs = df_processos['ID'].astype(str) + " - " + df_processos['Número'].astype(str) + " (" + df_processos['Cliente'].astype(str) + ")"
                opcoes = ["Nenhum"] + list(lista_procs)
            else:
                opcoes = ["Nenhum"]
            
            processo_escolhido = st.selectbox("Vincular a um Processo (Opcional)", options=opcoes)
            # ---------------------------

            obs_evento = st.text_area("Observações / Detalhes")
            submit_agenda = st.form_submit_button("Salvar na Agenda")

            if submit_agenda:
                # Lógica para pegar só o ID numérico do processo escolhido
                id_vincular = ""
                if processo_escolhido != "Nenhum":
                    id_vincular = processo_escolhido.split(" - ")[0]

                # Cria o novo dado com a coluna ID_Processo
                novo_evento = pd.DataFrame([{
                    "Data": data_evento.strftime("%d/%m/%Y"),
                    "Hora": str(hora_evento),
                    "Evento": nome_evento,
                    "Tipo": tipo_evento,
                    "Obs": obs_evento,
                    "ID_Processo": id_vincular
                }])
                
                # Salva na planilha
                df_final_agenda = pd.concat([df_agenda, novo_evento], ignore_index=True)
                conn.update(worksheet="Agenda", data=df_final_agenda)
                st.success("Evento agendado com sucesso!")
                st.rerun()

    # --- LISTA DE EVENTOS ---
    st.divider()
    st.subheader("Próximos Compromissos")
    st.dataframe(df_agenda, use_container_width=True)
    
# === 5. FINANCEIRO ===
elif menu == "Financeiro":
    st.title("💰 Financeiro")
    df_fin = ler_dados("financeiro")
    
    with st.expander("Lançamento", expanded=False):
        with st.form("fin_add"):
            desc = st.text_input("Descrição")
            val = st.number_input("Total R$")
            parc = st.number_input("Parcelas", 1, 12, 1)
            dt_ini = st.date_input("1º Vencimento")
            if st.form_submit_button("Lançar"):
                lista_novos = []
                vp = val/parc
                base_id = df_fin['id'].max() + 1 if not df_fin.empty and 'id' in df_fin.columns and pd.notna(df_fin['id'].max()) else 1
                
                for i in range(parc):
                    venc = dt_ini + timedelta(days=30*i)
                    lista_novos.append({
                        "id": base_id + i,
                        "descricao": f"{desc} ({i+1}/{parc})",
                        "valor": vp,
                        "vencimento": venc.strftime("%d/%m/%Y"),
                        "pago": False
                    })
                salvar_dados("financeiro", pd.concat([df_fin, pd.DataFrame(lista_novos)], ignore_index=True))
                st.success("Lançado!")
    
    # Baixa
    abertos = df_fin[df_fin['pago'] == False] if not df_fin.empty else pd.DataFrame()
    if not abertos.empty:
        baixa = st.selectbox("Dar Baixa (Selecione ID)", abertos['id'].unique())
        if st.button("Confirmar Pagamento"):
            idx = df_fin[df_fin['id'] == baixa].index
            df_fin.at[idx[0], 'pago'] = True
            salvar_dados("financeiro", df_fin)
            st.rerun()
            
    st.divider()

    st.dataframe(df_fin, use_container_width=True)


