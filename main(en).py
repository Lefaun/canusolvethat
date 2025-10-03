import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import sqlite3
import requests
from bs4 import BeautifulSoup
from docx import Document
import PyPDF2
from duckduckgo_search import DDGS

# Inicializar banco de dados
def init_db():
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    # Tabela de usuários
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            nome TEXT NOT NULL,
            perfil TEXT DEFAULT 'usuario',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabela de tickets
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE NOT NULL,
            titulo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            categoria TEXT NOT NULL,
            prioridade TEXT NOT NULL,
            status TEXT DEFAULT 'aberto',
            criado_por INTEGER,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            prazo TIMESTAMP,
            atribuido_para INTEGER,
            solucao TEXT,
            resolvido_em TIMESTAMP,
            FOREIGN KEY (criado_por) REFERENCES usuarios (id),
            FOREIGN KEY (atribuido_para) REFERENCES usuarios (id)
        )
    ''')
    
    # Tabela de anexos
    c.execute('''
        CREATE TABLE IF NOT EXISTS anexos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            nome_arquivo TEXT NOT NULL,
            dados_arquivo BLOB NOT NULL,
            tipo_arquivo TEXT NOT NULL,
            enviado_por INTEGER,
            enviado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Gerar ID único do ticket
def gerar_id_ticket():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    import random
    random_str = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
    return f"TKT-{timestamp}-{random_str}"

# Criptografar senha
def criptografar_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

# Autenticar usuário
def autenticar_usuario(email, senha):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    senha_criptografada = criptografar_senha(senha)
    
    c.execute('SELECT * FROM usuarios WHERE email = ? AND senha = ?', 
              (email, senha_criptografada))
    usuario = c.fetchone()
    conn.close()
    
    if usuario:
        return {
            'id': usuario[0],
            'email': usuario[1],
            'nome': usuario[3],
            'perfil': usuario[4]
        }
    return None

# Registrar novo usuário
def registrar_usuario(email, senha, nome, perfil='usuario'):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    senha_criptografada = criptografar_senha(senha)
    
    try:
        c.execute('INSERT INTO usuarios (email, senha, nome, perfil) VALUES (?, ?, ?, ?)',
                  (email, senha_criptografada, nome, perfil))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

# Criar novo ticket
def criar_ticket(titulo, descricao, categoria, prioridade, criado_por, dias_prazo=30):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    prazo = datetime.now() + timedelta(days=dias_prazo)
    ticket_id = gerar_id_ticket()
    
    c.execute('''
        INSERT INTO tickets (ticket_id, titulo, descricao, categoria, prioridade, criado_por, prazo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (ticket_id, titulo, descricao, categoria, prioridade, criado_por, prazo))
    
    ticket_db_id = c.lastrowid
    conn.commit()
    conn.close()
    return ticket_db_id, ticket_id

# Obter todos os tickets
def obter_todos_tickets():
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT t.*, u.nome as nome_criador, u2.nome as nome_atribuido
        FROM tickets t 
        LEFT JOIN usuarios u ON t.criado_por = u.id 
        LEFT JOIN usuarios u2 ON t.atribuido_para = u2.id
        ORDER BY t.criado_em DESC
    ''')
    tickets = c.fetchall()
    conn.close()
    
    return tickets

# Obter tickets do usuário
def obter_tickets_usuario(usuario_id):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT t.*, u.nome as nome_criador, u2.nome as nome_atribuido
        FROM tickets t 
        LEFT JOIN usuarios u ON t.criado_por = u.id 
        LEFT JOIN usuarios u2 ON t.atribuido_para = u2.id
        WHERE t.criado_por = ?
        ORDER BY t.criado_em DESC
    ''', (usuario_id,))
    tickets = c.fetchall()
    conn.close()
    
    return tickets

# Atribuir ticket a usuário
def atribuir_ticket(ticket_id, usuario_id):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('UPDATE tickets SET atribuido_para = ? WHERE id = ?', (usuario_id, ticket_id))
    conn.commit()
    conn.close()
    return True

# Salvar anexo
def salvar_anexo(ticket_id, nome_arquivo, dados_arquivo, tipo_arquivo, enviado_por):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO anexos (ticket_id, nome_arquivo, dados_arquivo, tipo_arquivo, enviado_por)
        VALUES (?, ?, ?, ?, ?)
    ''', (ticket_id, nome_arquivo, dados_arquivo, tipo_arquivo, enviado_por))
    
    conn.commit()
    conn.close()

# Obter anexos do ticket
def obter_anexos(ticket_id):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT a.*, u.nome as nome_usuario
        FROM anexos a
        JOIN usuarios u ON a.enviado_por = u.id
        WHERE a.ticket_id = ?
        ORDER BY a.enviado_em DESC
    ''', (ticket_id,))
    
    anexos = c.fetchall()
    conn.close()
    return anexos

# Buscar na web
def buscar_web(consulta, max_resultados=5):
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(consulta, max_results=max_resultados))
            return resultados
    except Exception as e:
        st.error(f"Erro na busca: {e}")
        return []

# Extrair texto de PDF
def extrair_texto_pdf(arquivo):
    try:
        pdf_reader = PyPDF2.PdfReader(arquivo)
        texto = ""
        for pagina in pdf_reader.pages:
            texto += pagina.extract_text()
        return texto
    except Exception as e:
        st.error(f"Erro na extração PDF: {e}")
        return ""

# Extrair texto de Word
def extrair_texto_word(arquivo):
    try:
        doc = Document(arquivo)
        texto = ""
        for paragrafo in doc.paragraphs:
            texto += paragrafo.text + "\n"
        return texto
    except Exception as e:
        st.error(f"Erro na extração Word: {e}")
        return ""

# Atualizar status do ticket
def atualizar_status_ticket(ticket_id, novo_status, solucao=None):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    if novo_status == 'resolvido' and solucao:
        c.execute('''
            UPDATE tickets 
            SET status = ?, solucao = ?, resolvido_em = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (novo_status, solucao, ticket_id))
    else:
        c.execute('UPDATE tickets SET status = ? WHERE id = ?', (novo_status, ticket_id))
    
    conn.commit()
    conn.close()

# Obter todos os usuários
def obter_todos_usuarios():
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    c.execute('SELECT id, nome, email, perfil, criado_em FROM usuarios')
    usuarios = c.fetchall()
    conn.close()
    return usuarios

# Ordem de prioridade
ORDEM_PRIORIDADE = {'Crítico': 1, 'Alta': 2, 'Média': 3, 'Baixa': 4}

def main():
    st.set_page_config(page_title="Sistema de Suporte", page_icon="🔧", layout="wide")
    
    # Inicializar banco
    init_db()
    
    # Barra lateral
    st.sidebar.title("🔧 Sistema de Suporte")
    st.sidebar.markdown("---")
    
    # Estado da sessão
    if 'usuario' not in st.session_state:
        st.session_state.usuario = None
    if 'pagina' not in st.session_state:
        st.session_state.pagina = "Início"
    
    # Autenticação
    if st.session_state.usuario is None:
        opcao_auth = st.sidebar.selectbox("Selecionar Opção", ["Login", "Registrar"])
        
        if opcao_auth == "Login":
            st.sidebar.subheader("Login")
            email_login = st.sidebar.text_input("Email")
            senha_login = st.sidebar.text_input("Senha", type="password")
            
            if st.sidebar.button("Entrar"):
                usuario = autenticar_usuario(email_login, senha_login)
                if usuario:
                    st.session_state.usuario = usuario
                    st.sidebar.success(f"Bem-vindo {usuario['nome']}!")
                    st.rerun()
                else:
                    st.sidebar.error("Credenciais inválidas")
        
        else:
            st.sidebar.subheader("Registrar")
            nome_reg = st.sidebar.text_input("Nome Completo")
            email_reg = st.sidebar.text_input("Email")
            senha_reg = st.sidebar.text_input("Senha", type="password")
            
            if st.sidebar.button("Registrar"):
                if registrar_usuario(email_reg, senha_reg, nome_reg):
                    st.sidebar.success("Registro realizado! Faça login.")
                else:
                    st.sidebar.error("Email já existe!")
        
        # Conteúdo para não autenticados
        st.title("🔧 Sistema de Suporte")
        st.markdown("""
        ### Bem-vindo ao Sistema de Suporte Colaborativo!
        
        **Funcionalidades:**
        - 🎫 Criar tickets com IDs únicos
        - 📎 Anexar arquivos (PDF, Word)
        - 🔍 Buscar na web
        - 👥 Atribuir tickets
        - 📊 Acompanhar progresso
        
        **Faça login ou registre-se para começar!**
        """)
        
        st.subheader("📋 Tickets Recentes")
        tickets = obter_todos_tickets()
        if tickets:
            dados_tickets = []
            for ticket in tickets:
                dados_tickets.append({
                    'Ticket ID': ticket[1],
                    'Título': ticket[2],
                    'Categoria': ticket[4],
                    'Prioridade': ticket[5],
                    'Status': ticket[6]
                })
            
            df = pd.DataFrame(dados_tickets)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhum ticket criado ainda.")
            
        st.markdown("---")
        st.markdown("**Desenvolvido por Paulo Monteiro**")
        return
    
    # Usuário autenticado
    usuario = st.session_state.usuario
    
    # Navegação
    if usuario['perfil'] == 'admin':
        paginas = ["Início", "Novo Ticket", "Meus Tickets", "Todos Tickets", "Admin"]
    else:
        paginas = ["Início", "Novo Ticket", "Meus Tickets", "Tickets Disponíveis"]
    
    st.session_state.pagina = st.sidebar.selectbox("Navegação", paginas)
    
    st.sidebar.markdown("---")
    st.sidebar.write(f"👤 Olá, {usuario['nome']} ({usuario['perfil']})")
    if st.sidebar.button("Sair"):
        st.session_state.usuario = None
        st.session_state.pagina = "Início"
        st.rerun()
    
    # Rotas
    if st.session_state.pagina == "Início":
        mostrar_pagina_inicio(usuario)
    elif st.session_state.pagina == "Novo Ticket":
        mostrar_novo_ticket(usuario)
    elif st.session_state.pagina == "Meus Tickets":
        mostrar_meus_tickets(usuario)
    elif st.session_state.pagina == "Tickets Disponíveis":
        mostrar_tickets_disponiveis(usuario)
    elif st.session_state.pagina == "Todos Tickets":
        mostrar_todos_tickets(usuario)
    elif st.session_state.pagina == "Admin":
        mostrar_admin(usuario)

def mostrar_pagina_inicio(usuario):
    st.title("🏠 Dashboard")
    
    col1, col2, col3 = st.columns(3)
    
    tickets = obter_todos_tickets()
    meus_tickets = obter_tickets_usuario(usuario['id'])
    
    with col1:
        st.metric("Total de Tickets", len(tickets))
    with col2:
        st.metric("Meus Tickets", len(meus_tickets))
    with col3:
        st.metric("Tickets Abertos", len([t for t in tickets if t[6] in ['aberto', 'em andamento']]))
    
    st.markdown("---")
    
    st.subheader("📈 Atividade Recente")
    
    tickets_recentes = tickets[:5]
    if tickets_recentes:
        st.write("**Tickets Recentes:**")
        for ticket in tickets_recentes:
            with st.expander(f"{ticket[1]} - {ticket[2]}"):
                st.write(f"**Categoria:** {ticket[4]}")
                st.write(f"**Prioridade:** {ticket[5]}")
                st.write(f"**Status:** {ticket[6]}")
                st.write(f"**Criado por:** {ticket[12]}")
                st.write(f"**Prazo:** {ticket[9]}")
    else:
        st.info("Nenhum ticket criado ainda.")

def mostrar_novo_ticket(usuario):
    st.title("🎫 Novo Ticket")
    
    with st.form("form_ticket"):
        titulo = st.text_input("Título do Ticket*")
        descricao = st.text_area("Descrição do Problema*", height=150)
        
        col1, col2 = st.columns(2)
        with col1:
            categoria = st.selectbox("Categoria*", [
                "Técnico", "Pesquisa", "Negócio", 
                "Acadêmico", "Software", "Hardware", "Outro"
            ])
        with col2:
            prioridade = st.selectbox("Prioridade*", ["Baixa", "Média", "Alta", "Crítico"])
        
        dias_prazo = st.slider("Prazo (dias a partir de hoje)", 1, 90, 30)
        
        arquivos = st.file_uploader(
            "Anexar Arquivos (PDF, Word)", 
            type=['pdf', 'docx', 'doc'],
            accept_multiple_files=True
        )
        
        enviado = st.form_submit_button("Criar Ticket")
        
        if enviado:
            if titulo and descricao:
                ticket_id, ticket_numero = criar_ticket(titulo, descricao, categoria, prioridade, usuario['id'], dias_prazo)
                st.success(f"Ticket criado com sucesso! Número: {ticket_numero}")
                
                if arquivos:
                    for arquivo in arquivos:
                        dados_arquivo = arquivo.read()
                        salvar_anexo(
                            ticket_id, 
                            arquivo.name, 
                            dados_arquivo, 
                            arquivo.type, 
                            usuario['id']
                        )
                    st.info(f"📎 {len(arquivos)} arquivo(s) anexado(s)")
            else:
                st.error("Preencha todos os campos obrigatórios!")

def mostrar_meus_tickets(usuario):
    st.title("📋 Meus Tickets")
    
    tickets = obter_tickets_usuario(usuario['id'])
    
    if not tickets:
        st.info("Você não criou nenhum ticket ainda.")
        return
    
    for ticket in tickets:
        with st.expander(f"{ticket[1]} - {ticket[2]} [{ticket[5]}]"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Número:** {ticket[1]}")
                st.write(f"**Categoria:** {ticket[4]}")
                st.write(f"**Prioridade:** {ticket[5]}")
                st.write(f"**Status:** {ticket[6]}")
                st.write(f"**Criado em:** {ticket[8]}")
                st.write(f"**Prazo:** {ticket[9]}")
                st.write(f"**Atribuído para:** {ticket[13] if ticket[13] else 'Não atribuído'}")
            
            with col2:
                st.write("**Descrição:**")
                st.write(ticket[3])
                
                anexos = obter_anexos(ticket[0])
                if anexos:
                    st.write("**Anexos:**")
                    for anexo in anexos:
                        col_a1, col_a2 = st.columns([3, 1])
                        with col_a1:
                            st.write(f"📎 {anexo[2]}")
                        with col_a2:
                            st.download_button(
                                label="Baixar",
                                data=anexo[3],
                                file_name=anexo[2],
                                mime=anexo[4],
                                key=f"dl_{anexo[0]}"
                            )

def mostrar_tickets_disponiveis(usuario):
    st.title("🔍 Tickets Disponíveis")
    
    tickets = obter_todos_tickets()
    tickets_disponiveis = [t for t in tickets if t[10] != usuario['id'] and t[6] in ['aberto', 'em andamento']]
    
    if not tickets_disponiveis:
        st.info("Nenhum ticket disponível no momento.")
        return
    
    tickets_disponiveis.sort(key=lambda x: ORDEM_PRIORIDADE.get(x[5], 5))
    
    for ticket in tickets_disponiveis:
        with st.expander(f"{ticket[1]} - {ticket[2]} [{ticket[5]}]"):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**Número:** {ticket[1]}")
                st.write(f"**Categoria:** {ticket[4]}")
                st.write(f"**Prioridade:** {ticket[5]}")
                st.write(f"**Status:** {ticket[6]}")
                st.write(f"**Criado por:** {ticket[12]}")
                st.write(f"**Prazo:** {ticket[9]}")
                st.write("**Descrição:**")
                st.write(ticket[3])
            
            with col2:
                if st.button("Assumir Ticket", key=f"assumir_{ticket[0]}"):
                    if atribuir_ticket(ticket[0], usuario['id']):
                        st.success("Ticket atribuído a você!")
                        st.rerun()

def mostrar_todos_tickets(usuario):
    if usuario['perfil'] != 'admin':
        st.error("Acesso negado. Apenas administradores.")
        return
    
    st.title("📊 Todos os Tickets")
    
    tickets = obter_todos_tickets()
    
    if not tickets:
        st.info("Nenhum ticket criado ainda.")
        return
    
    dados_tickets = []
    for ticket in tickets:
        dados_tickets.append({
            'Número': ticket[1],
            'Título': ticket[2],
            'Categoria': ticket[4],
            'Prioridade': ticket[5],
            'Status': ticket[6],
            'Criado Por': ticket[12],
            'Atribuído Para': ticket[13] if ticket[13] else 'Não atribuído',
            'Prazo': ticket[9]
        })
    
    df = pd.DataFrame(dados_tickets)
    st.dataframe(df, use_container_width=True)

def mostrar_admin(usuario):
    if usuario['perfil'] != 'admin':
        st.error("Acesso negado. Apenas administradores.")
        return
    
    st.title("⚙️ Painel Admin")
    
    aba1, aba2 = st.tabs(["Gerenciar Usuários", "Estatísticas"])
    
    with aba1:
        st.subheader("Usuários do Sistema")
        usuarios = obter_todos_usuarios()
        
        if usuarios:
            dados_usuarios = []
            for user in usuarios:
                dados_usuarios.append({
                    'ID': user[0],
                    'Nome': user[1],
                    'Email': user[2],
                    'Perfil': user[3]
                })
            
            df = pd.DataFrame(dados_usuarios)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhum usuário encontrado.")
    
    with aba2:
        st.subheader("Estatísticas do Sistema")
        
        tickets = obter_todos_tickets()
        usuarios = obter_todos_usuarios()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total de Tickets", len(tickets))
        with col2:
            st.metric("Total de Usuários", len(usuarios))
        with col3:
            st.metric("Tickets Resolvidos", len([t for t in tickets if t[6] == 'resolvido']))

# Rodapé
st.markdown("---")
st.markdown("**Desenvolvido por Paulo Monteiro**")

if __name__ == "__main__":
    main()
