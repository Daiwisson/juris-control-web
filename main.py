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
    st.title("⚖️ Processos")
    df_proc = ler_dados("processos")
    df_cli = ler_dados("clientes")
    df_hist = ler_dados("historico")
    
    lista_clientes = df_cli['nome'].tolist() if not df_cli.empty else []
    
    tab1, tab2 = st.tabs(["Novo Processo", "Gestão"])
    
    with tab1:
        if not lista_clientes:
            st.warning("Cadastre clientes antes.")
        else:
            with st.form("new_proc"):
                cli = st.selectbox("Cliente", lista_clientes)
                num = st.text_input("Número CNJ")
                juizo = st.text_input("Vara/Juízo")
                polo = st.radio("Polo", ["Autor", "Réu"], horizontal=True)
                desp = st.radio("Despacho", ["Presencial", "Virtual"], horizontal=True)
                if st.form_submit_button("Cadastrar"):
                    novo_id = df_proc['id'].max() + 1 if not df_proc.empty and 'id' in df_proc.columns and pd.notna(df_proc['id'].max()) else 1
                    hj = datetime.now().strftime("%d/%m/%Y")
                    novo = pd.DataFrame([{
                        "id": novo_id, "numero": num, "cliente_nome": cli,
                        "juizo": juizo, "polo": polo, "despacho": desp,
                        "status": "Ativo", "data_uv": hj
                    }])
                    df_final = pd.concat([df_proc, novo], ignore_index=True)
                    salvar_dados("processos", df_final)
                    st.success("Criado!")

    with tab2:
        # Seleção
        opcoes = []
        if not df_proc.empty:
            opcoes = df_proc.apply(lambda x: f"{x['id']} - {x['numero']} ({x['cliente_nome']})", axis=1).tolist()
        
        escolha = st.selectbox("Selecione o Processo", [""] + opcoes)
        
        if escolha != "":
            pid = int(float(escolha.split(" - ")[0]))
            # Filtra o processo (Loc)
            proc_row = df_proc[df_proc['id'] == pid].iloc[0]
            
            st.info(f"Processo: {proc_row['numero']} | Cliente: {proc_row['cliente_nome']}")
            st.caption(f"Status: {proc_row['status']} | Última Verificação: {proc_row['data_uv']}")
            
            # Botões de Ação
            c1, c2, c3 = st.columns(3)
            if c1.button("✅ Confirmar Consulta Hoje"):
                idx = df_proc[df_proc['id'] == pid].index
                df_proc.at[idx[0], 'data_uv'] = datetime.now().strftime("%d/%m/%Y")
                salvar_dados("processos", df_proc)
                st.rerun()
                
            if c2.button("📦 Arquivar"):
                idx = df_proc[df_proc['id'] == pid].index
                df_proc.at[idx[0], 'status'] = "Arquivado"
                salvar_dados("processos", df_proc)
                st.rerun()

            if c3.button("♻️ Reativar"):
                idx = df_proc[df_proc['id'] == pid].index
                df_proc.at[idx[0], 'status'] = "Ativo"
                salvar_dados("processos", df_proc)
                st.rerun()

            st.divider()
            
            # Histórico
            c_h1, c_h2 = st.columns(2)
            with c_h1:
                with st.form("add_hist"):
                    desc = st.text_area("Novo Andamento")
                    dt_evt = st.date_input("Data").strftime("%d/%m/%Y")
                    if st.form_submit_button("Registrar"):
                        novo_h = pd.DataFrame([{"processo_id": pid, "data": dt_evt, "descricao": desc}])
                        salvar_dados("historico", pd.concat([df_hist, novo_h], ignore_index=True))
                        # Atualiza data UV
                        idx = df_proc[df_proc['id'] == pid].index
                        df_proc.at[idx[0], 'data_uv'] = dt_evt
                        salvar_dados("processos", df_proc)
                        st.success("OK")
                        st.rerun()
            with c_h2:
                if not df_hist.empty:
                    filtro = df_hist[df_hist['processo_id'] == pid]
                    st.dataframe(filtro[['data', 'descricao']], hide_index=True)

# === 4. AGENDA ===
elif menu == "Agenda":
    st.title("📅 Agenda")
    df_ag = ler_dados("agenda")
    df_proc = ler_dados("processos")
    
    procs = df_proc['numero'].tolist() if not df_proc.empty else []
    
    with st.form("nova_ag"):
        tit = st.text_input("Título")
        vinculo = st.selectbox("Vínculo", ["Avulso"] + procs)
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data").strftime("%d/%m/%Y")
        hr = c2.time_input("Hora").strftime("%H:%M")
        tp = c3.selectbox("Tipo", ["Prazo", "Audiência"])
        if st.form_submit_button("Agendar"):
            novo = pd.DataFrame([{"titulo": tit, "processo": vinculo, "data": dt, "hora": hr, "tipo": tp}])
            salvar_dados("agenda", pd.concat([df_ag, novo], ignore_index=True))
            st.success("Agendado!")
            
    st.dataframe(df_ag, use_container_width=True)

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
