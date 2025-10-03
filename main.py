import streamlit as st
import pandas as pd
import datetime
import json
from datetime import datetime, timedelta
import hashlib
import sqlite3
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import re
import time
import io
import base64

# Novos imports para funcionalidades avançadas
from docx import Document
import PyPDF2
import fitz  # PyMuPDF - biblioteca alternativa para PDF
from duckduckgo_search import DDGS
#import google.generativeai as genai
import os

# Inicializar banco de dados com tabelas aprimoradas
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
    
    # Tabela de problemas aprimorada (agora tickets)
    c.execute('''
        CREATE TABLE IF NOT EXISTS problemas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE NOT NULL,
            titulo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            categoria TEXT NOT NULL,
            prioridade TEXT NOT NULL,
            status TEXT DEFAULT 'aberto',
            submetido_por INTEGER,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            prazo TIMESTAMP,
            atribuido_para INTEGER,
            solucao TEXT,
            resolvido_em TIMESTAMP,
            FOREIGN KEY (submetido_por) REFERENCES usuarios (id),
            FOREIGN KEY (atribuido_para) REFERENCES usuarios (id)
        )
    ''')
    
    # Tabela de atribuições
    c.execute('''
        CREATE TABLE IF NOT EXISTS atribuicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problema_id INTEGER,
            usuario_id INTEGER,
            atribuido_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'atribuido',
            FOREIGN KEY (problema_id) REFERENCES problemas (id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')
    
    # Tabela de eventos do calendário
    c.execute('''
        CREATE TABLE IF NOT EXISTS eventos_calendario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problema_id INTEGER,
            titulo TEXT NOT NULL,
            descricao TEXT,
            data_evento TIMESTAMP NOT NULL,
            criado_por INTEGER,
            FOREIGN KEY (problema_id) REFERENCES problemas (id),
            FOREIGN KEY (criado_por) REFERENCES usuarios (id)
        )
    ''')
    
    # Tabela de anexos de arquivos
    c.execute('''
        CREATE TABLE IF NOT EXISTS anexos_arquivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problema_id INTEGER,
            nome_arquivo TEXT NOT NULL,
            dados_arquivo BLOB NOT NULL,
            tipo_arquivo TEXT NOT NULL,
            enviado_por INTEGER,
            enviado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (problema_id) REFERENCES problemas (id),
            FOREIGN KEY (enviado_por) REFERENCES usuarios (id)
        )
    ''')
    
    # Tabela de resultados de busca
    c.execute('''
        CREATE TABLE IF NOT EXISTS resultados_busca (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problema_id INTEGER,
            consulta_busca TEXT NOT NULL,
            titulo_resultado TEXT,
            url_resultado TEXT,
            snippet_resultado TEXT,
            motor_busca TEXT,
            buscado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (problema_id) REFERENCES problemas (id)
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

# Submissão de problema aprimorada com ID do ticket
def submeter_problema(titulo, descricao, categoria, prioridade, submetido_por, dias_prazo=30):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    prazo = datetime.now() + timedelta(days=dias_prazo)
    ticket_id = gerar_id_ticket()
    
    c.execute('''
        INSERT INTO problemas (ticket_id, titulo, descricao, categoria, prioridade, submetido_por, prazo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (ticket_id, titulo, descricao, categoria, prioridade, submetido_por, prazo))
    
    problema_id = c.lastrowid
    conn.commit()
    conn.close()
    return problema_id, ticket_id

# Obter todos os problemas
def obter_todos_problemas():
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT p.*, u.nome as nome_submetido_por, u2.nome as nome_atribuido_para
        FROM problemas p 
        LEFT JOIN usuarios u ON p.submetido_por = u.id 
        LEFT JOIN usuarios u2 ON p.atribuido_para = u2.id
        ORDER BY p.criado_em DESC
    ''')
    problemas = c.fetchall()
    conn.close()
    
    return problemas

# Obter problemas do usuário
def obter_problemas_usuario(usuario_id):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT p.*, u.nome as nome_submetido_por, u2.nome as nome_atribuido_para
        FROM problemas p 
        LEFT JOIN usuarios u ON p.submetido_por = u.id 
        LEFT JOIN usuarios u2 ON p.atribuido_para = u2.id
        WHERE p.submetido_por = ?
        ORDER BY p.criado_em DESC
    ''', (usuario_id,))
    problemas = c.fetchall()
    conn.close()
    
    return problemas

# Atribuir usuário ao problema
def atribuir_ao_problema(problema_id, usuario_id):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    # Atualizar a atribuição principal do problema
    c.execute('UPDATE problemas SET atribuido_para = ? WHERE id = ?', (usuario_id, problema_id))
    
    # Verificar se já está atribuído na tabela de atribuições
    c.execute('SELECT * FROM atribuicoes WHERE problema_id = ? AND usuario_id = ?', 
              (problema_id, usuario_id))
    existente = c.fetchone()
    
    if not existente:
        c.execute('INSERT INTO atribuicoes (problema_id, usuario_id) VALUES (?, ?)', 
                  (problema_id, usuario_id))
    
    conn.commit()
    conn.close()
    return True

# Obter atribuições para o problema
def obter_atribuicoes_problema(problema_id):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT a.*, u.nome as nome_usuario 
        FROM atribuicoes a 
        JOIN usuarios u ON a.usuario_id = u.id 
        WHERE a.problema_id = ?
    ''', (problema_id,))
    atribuicoes = c.fetchall()
    conn.close()
    
    return atribuicoes

# Adicionar evento ao calendário
def adicionar_evento_calendario(problema_id, titulo, descricao, data_evento, criado_por):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO eventos_calendario (problema_id, titulo, descricao, data_evento, criado_por)
        VALUES (?, ?, ?, ?, ?)
    ''', (problema_id, titulo, descricao, data_evento, criado_por))
    
    conn.commit()
    conn.close()

# Obter eventos do calendário
def obter_eventos_calendario(usuario_id=None):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    if usuario_id:
        c.execute('''
            SELECT ce.*, p.titulo as titulo_problema, u.nome as nome_criado_por
            FROM eventos_calendario ce
            JOIN problemas p ON ce.problema_id = p.id
            JOIN usuarios u ON ce.criado_por = u.id
            WHERE ce.criado_por = ? OR ce.problema_id IN (
                SELECT problema_id FROM atribuicoes WHERE usuario_id = ?
            )
            ORDER BY ce.data_evento
        ''', (usuario_id, usuario_id))
    else:
        c.execute('''
            SELECT ce.*, p.titulo as titulo_problema, u.nome as nome_criado_por
            FROM eventos_calendario ce
            JOIN problemas p ON ce.problema_id = p.id
            JOIN usuarios u ON ce.criado_por = u.id
            ORDER BY ce.data_evento
        ''')
    
    eventos = c.fetchall()
    conn.close()
    return eventos

# Funções de anexo de arquivos
def salvar_anexo_arquivo(problema_id, nome_arquivo, dados_arquivo, tipo_arquivo, enviado_por):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO anexos_arquivos (problema_id, nome_arquivo, dados_arquivo, tipo_arquivo, enviado_por)
        VALUES (?, ?, ?, ?, ?)
    ''', (problema_id, nome_arquivo, dados_arquivo, tipo_arquivo, enviado_por))
    
    conn.commit()
    conn.close()

def obter_anexos_arquivos(problema_id):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT fa.*, u.nome as nome_enviado_por
        FROM anexos_arquivos fa
        JOIN usuarios u ON fa.enviado_por = u.id
        WHERE fa.problema_id = ?
        ORDER BY fa.enviado_em DESC
    ''', (problema_id,))
    
    anexos = c.fetchall()
    conn.close()
    return anexos

def obter_anexo_arquivo(arquivo_id):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM anexos_arquivos WHERE id = ?', (arquivo_id,))
    anexo = c.fetchone()
    conn.close()
    return anexo

# Funções de busca
def salvar_resultado_busca(problema_id, consulta_busca, titulo_resultado, url_resultado, snippet_resultado, motor_busca):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO resultados_busca (problema_id, consulta_busca, titulo_resultado, url_resultado, snippet_resultado, motor_busca)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (problema_id, consulta_busca, titulo_resultado, url_resultado, snippet_resultado, motor_busca))
    
    conn.commit()
    conn.close()

def obter_resultados_busca(problema_id):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT * FROM resultados_busca 
        WHERE problema_id = ? 
        ORDER BY buscado_em DESC
    ''', (problema_id,))
    
    resultados = c.fetchall()
    conn.close()
    return resultados

# Funcionalidade de busca na web - CORRIGIDA
def buscar_na_web(consulta, max_resultados=5):
    """Buscar usando DuckDuckGo - Versão Corrigida"""
    try:
        with DDGS() as ddgs:
            resultados = []
            for resultado in ddgs.text(consulta, max_results=max_resultados):
                resultados.append(resultado)
            return resultados
    except Exception as e:
        st.error(f"Erro na busca: {str(e)}")
        return []

def buscar_com_beautiful_soup(url):
    """Extrair conteúdo de uma URL usando BeautifulSoup"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Levanta exceção para erros HTTP
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extrair conteúdo relevante
        titulo = soup.title.string if soup.title else "Sem título"
        
        # Remover elementos script e style
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Obter conteúdo de texto
        texto = soup.get_text()
        linhas = (linha.strip() for linha in texto.splitlines())
        chunks = (phrase.strip() for linha in linhas for phrase in linha.split("  "))
        texto = ' '.join(chunk for chunk in chunks if chunk)
        
        return {
            'titulo': titulo,
            'conteudo': texto[:1000] + '...' if len(texto) > 1000 else texto,  # Limitar comprimento do conteúdo
            'url': url
        }
    except Exception as e:
        return {'erro': str(e)}

# Funções de processamento de documentos
def extrair_texto_de_pdf(arquivo):
    """Extrair texto de arquivo PDF"""
    try:
        # Voltar para o início do arquivo
        arquivo.seek(0)
        pdf_reader = PyPDF2.PdfReader(arquivo)
        texto = ""
        for pagina in pdf_reader.pages:
            texto_pagina = pagina.extract_text()
            if texto_pagina:
                texto += texto_pagina + "\n"
        return texto
    except Exception as e:
        st.error(f"Erro na extração de PDF: {e}")
        return ""

def extrair_texto_de_word(arquivo):
    """Extrair texto de documento Word"""
    try:
        # Voltar para o início do arquivo
        arquivo.seek(0)
        doc = Document(arquivo)
        texto = ""
        for paragrafo in doc.paragraphs:
            if paragrafo.text:
                texto += paragrafo.text + "\n"
        return texto
    except Exception as e:
        st.error(f"Erro na extração de Word: {e}")
        return ""

def processar_arquivo_enviado(arquivo):
    """Processar arquivo enviado e retornar conteúdo de texto"""
    tipo_arquivo = arquivo.name.split('.')[-1].lower()
    
    if tipo_arquivo == 'pdf':
        return extrair_texto_de_pdf(arquivo)
    elif tipo_arquivo in ['docx', 'doc']:
        return extrair_texto_de_word(arquivo)
    elif tipo_arquivo == 'txt':
        return arquivo.read().decode('utf-8')
    else:
        return "Tipo de arquivo não suportado"

# Atualizar status do problema
def atualizar_status_problema(problema_id, novo_status, solucao=None):
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    
    if novo_status == 'resolvido' and solucao:
        c.execute('''
            UPDATE problemas 
            SET status = ?, solucao = ?, resolvido_em = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (novo_status, solucao, problema_id))
    else:
        c.execute('UPDATE problemas SET status = ? WHERE id = ?', (novo_status, problema_id))
    
    conn.commit()
    conn.close()

# Obter todos os usuários para atribuição
def obter_todos_usuarios():
    conn = sqlite3.connect('sistema_suporte.db')
    c = conn.cursor()
    c.execute('SELECT id, nome, email, perfil, criado_em FROM usuarios')
    usuarios = c.fetchall()
    conn.close()
    return usuarios

# Mapeamento de prioridade para ordenação
ORDEM_PRIORIDADE = {'Crítico': 1, 'Alta': 2, 'Média': 3, 'Baixa': 4}

def main():
    st.set_page_config(page_title="Plataforma de Resolução de Problemas", page_icon="🔧", layout="wide")
    
    # Inicializar banco de dados
    init_db()
    
    # Barra lateral para navegação
    st.sidebar.title("🔧 Plataforma de Resolução de Problemas")
    st.sidebar.markdown("---")
    
    # Estado da sessão para autenticação
    if 'usuario' not in st.session_state:
        st.session_state.usuario = None
    if 'pagina' not in st.session_state:
        st.session_state.pagina = "Início"
    
    # Seção de autenticação
    if st.session_state.usuario is None:
        opcao_auth = st.sidebar.selectbox("Selecionar Opção", ["Login", "Registrar"])
        
        if opcao_auth == "Login":
            st.sidebar.subheader("Login")
            email_login = st.sidebar.text_input("Email")
            senha_login = st.sidebar.text_input("Senha", type="password")
            
            if st.sidebar.button("Login"):
                usuario = autenticar_usuario(email_login, senha_login)
                if usuario:
                    st.session_state.usuario = usuario
                    st.sidebar.success(f"Bem-vindo {usuario['nome']}!")
                    st.rerun()
                else:
                    st.sidebar.error("Credenciais inválidas")
        
        else:  # Registrar
            st.sidebar.subheader("Registrar")
            nome_reg = st.sidebar.text_input("Nome Completo")
            email_reg = st.sidebar.text_input("Email")
            senha_reg = st.sidebar.text_input("Senha", type="password")
            
            if st.sidebar.button("Registrar"):
                if registrar_usuario(email_reg, senha_reg, nome_reg):
                    st.sidebar.success("Registro bem-sucedido! Por favor, faça login.")
                else:
                    st.sidebar.error("Email já existe!")
        
        # Mostrar conteúdo principal para usuários não autenticados
        st.title("🔧 Plataforma de Resolução de Problemas")
        st.markdown("""
        ### Bem-vindo à Plataforma Colaborativa de Resolução de Problemas!
        
        **Novas Funcionalidades:**
        - 🎫 Sistema de Tickets com IDs únicos
        - 📎 Anexos de Arquivos (PDF, Word, Texto)
        - 🔍 Integração de Busca na Web (DuckDuckGo + BeautifulSoup)
        - 📊 Processamento de Documentos Aprimorado
        - 👥 Sistema de Atribuição Melhorado
        
        **Por favor, faça login ou registre-se para começar!**
        """)
        
        # Mostrar problemas recentes (somente leitura para usuários não logados)
        st.subheader("📋 Problemas Submetidos Recentemente")
        problemas = obter_todos_problemas()
        if problemas:
            dados_problemas = []
            for problema in problemas:
                dados_problemas.append({
                    'ID do Ticket': problema[1],
                    'Título': problema[2],
                    'Categoria': problema[4],
                    'Prioridade': problema[5],
                    'Status': problema[6],
                    'Submetido Por': problema[12],
                    'Prazo': problema[9]
                })
            
            df = pd.DataFrame(dados_problemas)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhum problema submetido ainda.")
            
        st.markdown("---")
        st.markdown("**Créditos:** Desenvolvido por Paulo Monteiro")
        return
    
    # Usuário está autenticado - mostrar aplicação completa
    usuario = st.session_state.usuario
    
    # Navegação para usuários autenticados
    if usuario['perfil'] == 'admin':
        paginas = ["Início", "Submeter Ticket", "Meus Tickets", "Todos os Tickets", "Calendário", "Painel Admin", "Busca na Web"]
    else:
        paginas = ["Início", "Submeter Ticket", "Meus Tickets", "Tickets Disponíveis", "Calendário", "Busca na Web"]
    
    st.session_state.pagina = st.sidebar.selectbox("Navegação", paginas, index=paginas.index(st.session_state.pagina))
    
    st.sidebar.markdown("---")
    st.sidebar.write(f"👤 Bem-vindo, {usuario['nome']} ({usuario['perfil']})")
    if st.sidebar.button("Sair"):
        st.session_state.usuario = None
        st.session_state.pagina = "Início"
        st.rerun()
    
    # Roteamento de páginas
    if st.session_state.pagina == "Início":
        mostrar_pagina_inicio(usuario)
    elif st.session_state.pagina == "Submeter Ticket":
        mostrar_submeter_ticket(usuario)
    elif st.session_state.pagina == "Meus Tickets":
        mostrar_meus_tickets(usuario)
    elif st.session_state.pagina == "Tickets Disponíveis":
        mostrar_tickets_disponiveis(usuario)
    elif st.session_state.pagina == "Todos os Tickets":
        mostrar_todos_tickets(usuario)
    elif st.session_state.pagina == "Calendário":
        mostrar_calendario(usuario)
    elif st.session_state.pagina == "Painel Admin":
        mostrar_painel_admin(usuario)
    elif st.session_state.pagina == "Busca na Web":
        mostrar_busca_web(usuario)

def mostrar_pagina_inicio(usuario):
    st.title("🏠 Dashboard")
    
    col1, col2, col3, col4 = st.columns(4)
    
    # Estatísticas
    problemas = obter_todos_problemas()
    problemas_usuario = obter_problemas_usuario(usuario['id'])
    atribuicoes = len([p for p in problemas if p[10] == usuario['id']])
    
    with col1:
        st.metric("Total de Tickets", len(problemas))
    with col2:
        st.metric("Meus Tickets Submetidos", len(problemas_usuario))
    with col3:
        st.metric("Minhas Atribuições", atribuicoes)
    with col4:
        st.metric("Tickets Abertos", len([p for p in problemas if p[6] in ['aberto', 'em andamento']]))
    
    st.markdown("---")
    
    # Atividade recente
    st.subheader("📈 Atividade Recente")
    
    # Problemas recentes
    problemas_recentes = problemas[:5]
    if problemas_recentes:
        st.write("**Tickets Submetidos Recentemente:**")
        for problema in problemas_recentes:
            with st.expander(f"{problema[1]} - {problema[2]} - Prioridade {problema[5]}"):
                st.write(f"**Categoria:** {problema[4]}")
                st.write(f"**Status:** {problema[6]}")
                st.write(f"**Submetido por:** {problema[12]}")
                st.write(f"**Atribuído a:** {problema[13] if problema[13] else 'Não atribuído'}")
                st.write(f"**Prazo:** {problema[9]}")
    else:
        st.info("Nenhum ticket submetido ainda.")

def mostrar_submeter_ticket(usuario):
    st.title("🎫 Submeter Novo Ticket")
    
    with st.form("formulario_ticket"):
        titulo = st.text_input("Título do Ticket*")
        descricao = st.text_area("Descrição do Problema*", height=150)
        
        col1, col2 = st.columns(2)
        with col1:
            categoria = st.selectbox("Categoria*", [
                "Técnico", "Pesquisa", "Negócio", 
                "Acadêmico", "Software", "Hardware",
                "Análise de Dados", "Algoritmo", "Documentação", "Outro"
            ])
        with col2:
            prioridade = st.selectbox("Prioridade*", ["Baixa", "Média", "Alta", "Crítico"])
        
        dias_prazo = st.slider("Prazo (dias a partir de hoje)", 1, 90, 30)
        
        # Upload de arquivo
        arquivos_enviados = st.file_uploader(
            "Anexar Arquivos (PDF, Word, Texto)", 
            type=['pdf', 'docx', 'doc', 'txt'],
            accept_multiple_files=True
        )
        
        submetido = st.form_submit_button("Submeter Ticket")
        
        if submetido:
            if titulo and descricao:
                problema_id, ticket_id = submeter_problema(titulo, descricao, categoria, prioridade, usuario['id'], dias_prazo)
                st.success(f"Ticket submetido com sucesso! ID do Ticket: {ticket_id}")
                
                # Salvar arquivos enviados
                if arquivos_enviados:
                    for arquivo_enviado in arquivos_enviados:
                        dados_arquivo = arquivo_enviado.read()
                        salvar_anexo_arquivo(
                            problema_id, 
                            arquivo_enviado.name, 
                            dados_arquivo, 
                            arquivo_enviado.type, 
                            usuario['id']
                        )
                    st.info(f"📎 {len(arquivos_enviados)} arquivo(s) anexado(s)")
                
                # Adicionar evento inicial do calendário para o prazo
                data_prazo = datetime.now() + timedelta(days=dias_prazo)
                adicionar_evento_calendario(
                    problema_id, 
                    f"Prazo: {titulo}", 
                    f"Prazo final para resolução: {descricao}",
                    data_prazo,
                    usuario['id']
                )
            else:
                st.error("Por favor, preencha todos os campos obrigatórios!")

def mostrar_meus_tickets(usuario):
    st.title("📋 Meus Tickets Submetidos")
    
    problemas = obter_problemas_usuario(usuario['id'])
    
    if not problemas:
        st.info("Você não submeteu nenhum ticket ainda.")
        return
    
    for problema in problemas:
        with st.expander(f"{problema[1]} - {problema[2]} [{problema[5]}] - {problema[6]}"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**ID do Ticket:** {problema[1]}")
                st.write(f"**Categoria:** {problema[4]}")
                st.write(f"**Prioridade:** {problema[5]}")
                st.write(f"**Status:** {problema[6]}")
                st.write(f"**Submetido:** {problema[8]}")
                st.write(f"**Prazo:** {problema[9]}")
                st.write(f"**Atribuído a:** {problema[13] if problema[13] else 'Não atribuído'}")
            
            with col2:
                st.write("**Descrição:**")
                st.write(problema[3])
                
                # Mostrar anexos de arquivos
                anexos = obter_anexos_arquivos(problema[0])
                if anexos:
                    st.write("**Anexos:**")
                    for anexo in anexos:
                        col_a1, col_a2 = st.columns([3, 1])
                        with col_a1:
                            st.write(f"📎 {anexo[2]}")
                        with col_a2:
                            dados_arquivo = anexo[3]
                            st.download_button(
                                label="Baixar",
                                data=dados_arquivo,
                                file_name=anexo[2],
                                mime=anexo[4],
                                key=f"dl_{anexo[0]}"
                            )
                
                # Mostrar resultados de busca
                resultados_busca = obter_resultados_busca(problema[0])
                if resultados_busca:
                    st.write("**Resultados de Busca Salvos:**")
                    for resultado in resultados_busca[:3]:  # Mostrar primeiros 3
                        st.write(f"🔍 {resultado[3]} - {resultado[5]}")
            
            # Adicionar evento do calendário para este problema
            st.subheader("Adicionar Evento ao Calendário")
            with st.form(f"formulario_evento_{problema[0]}"):
                titulo_evento = st.text_input("Título do Evento", value=f"Reunião: {problema[2]}")
                desc_evento = st.text_area("Descrição do Evento")
                data_evento = st.date_input("Data do Evento", min_value=datetime.now().date())
                hora_evento = st.time_input("Hora do Evento", datetime.now().time())
                
                if st.form_submit_button("Adicionar ao Calendário"):
                    data_hora_evento = datetime.combine(data_evento, hora_evento)
                    adicionar_evento_calendario(problema[0], titulo_evento, desc_evento, data_hora_evento, usuario['id'])
                    st.success("Evento adicionado ao calendário!")

def mostrar_tickets_disponiveis(usuario):
    st.title("🔍 Tickets Disponíveis para Resolução")
    
    problemas = obter_todos_problemas()
    
    # Filtrar problemas que não estão atribuídos ao usuário atual e ainda estão abertos
    problemas_disponiveis = [p for p in problemas if p[10] != usuario['id'] and p[6] in ['aberto', 'em andamento']]
    
    if not problemas_disponiveis:
        st.info("Nenhum ticket disponível no momento.")
        return
    
    # Ordenar por prioridade
    problemas_disponiveis.sort(key=lambda x: ORDEM_PRIORIDADE.get(x[5], 5))
    
    for problema in problemas_disponiveis:
        with st.expander(f"{problema[1]} - {problema[2]} [{problema[5]}] - {problema[6]}"):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**ID do Ticket:** {problema[1]}")
                st.write(f"**Categoria:** {problema[4]}")
                st.write(f"**Prioridade:** {problema[5]}")
                st.write(f"**Status:** {problema[6]}")
                st.write(f"**Submetido por:** {problema[12]}")
                st.write(f"**Prazo:** {problema[9]}")
                st.write("**Descrição:**")
                st.write(problema[3])
                
                # Mostrar atribuições atuais
                atribuicoes = obter_atribuicoes_problema(problema[0])
                if atribuicoes:
                    st.write("**Atualmente atribuído a:**")
                    for atribuicao in atribuicoes:
                        st.write(f"- {atribuicao[4]}")
            
            with col2:
                if st.button(f"Atribuir a Mim", key=f"atribuir_{problema[0]}"):
                    if atribuir_ao_problema(problema[0], usuario['id']):
                        st.success("Atribuído a você com sucesso!")
                        st.rerun()
                    else:
                        st.error("Falha na atribuição!")

def mostrar_todos_tickets(usuario):
    if usuario['perfil'] != 'admin':
        st.error("Acesso negado. Privilégios de administrador necessários.")
        return
    
    st.title("📊 Todos os Tickets (Visualização Admin)")
    
    problemas = obter_todos_problemas()
    
    if not problemas:
        st.info("Nenhum ticket submetido ainda.")
        return
    
    # Criar DataFrame para melhor exibição
    dados_problemas = []
    for problema in problemas:
        atribuicoes = obter_atribuicoes_problema(problema[0])
        atribuido_a = ", ".join([a[4] for a in atribuicoes]) if atribuicoes else "Nenhum"
        
        dados_problemas.append({
            'ID do Ticket': problema[1],
            'Título': problema[2],
            'Categoria': problema[4],
            'Prioridade': problema[5],
            'Status': problema[6],
            'Submetido Por': problema[12],
            'Atribuído A': atribuido_a,
            'Prazo': problema[9],
            'Criado': problema[8]
        })
    
    df = pd.DataFrame(dados_problemas)
    st.dataframe(df, use_container_width=True)
    
    # Gerenciamento de tickets
    st.subheader("Gerenciamento de Tickets")
    ids_problemas = [p[0] for p in problemas]
    problema_selecionado = st.selectbox("Selecionar Ticket para Gerenciar", ids_problemas, 
                                   format_func=lambda x: f"{next(p[1] for p in problemas if p[0] == x)} - {next(p[2] for p in problemas if p[0] == x)}")
    
    if problema_selecionado:
        problema = next(p for p in problemas if p[0] == problema_selecionado)
        col1, col2, col3 = st.columns(3)
        
        with col1:
            novo_status = st.selectbox("Atualizar Status", 
                                    ["aberto", "em andamento", "resolvido", "fechado"],
                                    index=["aberto", "em andamento", "resolvido", "fechado"].index(problema[6]))
            
            solucao = st.text_area("Notas de Resolução", value=problema[11] or "")
            
            if st.button("Atualizar Status"):
                atualizar_status_problema(problema_selecionado, novo_status, solucao)
                st.success("Status atualizado!")
                st.rerun()
        
        with col2:
            st.write("**Atribuições Atuais:**")
            atribuicoes = obter_atribuicoes_problema(problema_selecionado)
            if atribuicoes:
                for atribuicao in atribuicoes:
                    st.write(f"- {atribuicao[4]}")
            else:
                st.write("Nenhuma atribuição")
            
            # Atribuir a usuário
            usuarios = obter_todos_usuarios()
            opcoes_usuarios = {f"{u[1]} ({u[3]})": u[0] for u in usuarios}
            usuario_selecionado = st.selectbox("Atribuir a Usuário", list(opcoes_usuarios.keys()))
            
            if st.button("Atribuir Usuário"):
                usuario_id = opcoes_usuarios[usuario_selecionado]
                atribuir_ao_problema(problema_selecionado, usuario_id)
                st.success("Usuário atribuído!")
                st.rerun()
        
        with col3:
            # Anexos de arquivos
            st.write("**Anexos:**")
            anexos = obter_anexos_arquivos(problema_selecionado)
            if anexos:
                for anexo in anexos:
                    st.write(f"📎 {anexo[2]}")
            else:
                st.write("Nenhum anexo")

def mostrar_calendario(usuario):
    st.title("📅 Calendário")
    
    # Obter eventos baseado no perfil do usuário
    if usuario['perfil'] == 'admin':
        eventos = obter_eventos_calendario()
    else:
        eventos = obter_eventos_calendario(usuario['id'])
    
    if not eventos:
        st.info("Nenhum evento de calendário encontrado.")
        return
    
    # Agrupar eventos por data
    eventos_por_data = {}
    for evento in eventos:
        data_evento = datetime.strptime(evento[4], '%Y-%m-%d %H:%M:%S').date()
        if data_evento not in eventos_por_data:
            eventos_por_data[data_evento] = []
        eventos_por_data[data_evento].append(evento)
    
    # Exibir eventos cronologicamente
    for data in sorted(eventos_por_data.keys()):
        st.subheader(f"📅 {data.strftime('%A, %d de %B de %Y')}")
        
        for evento in eventos_por_data[data]:
            with st.expander(f"⏰ {evento[1]} - {evento[4][11:16]}"):
                st.write(f"**Ticket:** {evento[6]}")
                st.write(f"**Descrição:** {evento[2]}")
                st.write(f"**Criado por:** {evento[7]}")
# Função de busca alternativa - CORREÇÃO COMPLETA
def buscar_na_web(consulta, max_resultados=5):
    """Buscar usando DuckDuckGo - Versão Corrigida"""
    try:
        # Método 1: Tentar com a versão mais recente
        from duckduckgo_search import DDGS
        
        with DDGS() as ddgs:
            resultados = []
            for resultado in ddgs.text(consulta, max_results=max_resultados):
                # Garantir que temos os campos esperados
                resultado_formatado = {
                    'title': resultado.get('title', 'Sem título'),
                    'href': resultado.get('href', ''),
                    'body': resultado.get('body', 'Sem descrição')
                }
                resultados.append(resultado_formatado)
            return resultados
            
    except Exception as e:
        st.error(f"Erro na busca DuckDuckGo: {str(e)}")
        
        # Método 2: Fallback para requests + BeautifulSoup
        try:
            st.info("Tentando método alternativo de busca...")
            return buscar_alternativa(consulta, max_resultados)
        except Exception as e2:
            st.error(f"Busca alternativa também falhou: {str(e2)}")
            return []

def buscar_alternativa(consulta, max_resultados=5):
    """Método alternativo de busca usando requests"""
    try:
        import urllib.parse
        
        # Codificar a consulta para URL
        consulta_codificada = urllib.parse.quote(consulta)
        url = f"https://html.duckduckgo.com/html/?q={consulta_codificada}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        resultados = []
        links = soup.find_all('a', class_='result__a', limit=max_resultados)
        
        for link in links:
            titulo = link.get_text(strip=True)
            href = link.get('href', '')
            
            # Encontrar a descrição
            descricao_element = link.find_next('a', class_='result__snippet')
            descricao = descricao_element.get_text(strip=True) if descricao_element else "Sem descrição"
            
            resultados.append({
                'title': titulo,
                'href': href,
                'body': descricao
            })
        
        return resultados
        
    except Exception as e:
        st.error(f"Busca alternativa falhou: {str(e)}")
        return []
def mostrar_painel_admin(usuario):
    if usuario['perfil'] != 'admin':
        st.error("Acesso negado. Privilégios de administrador necessários.")
        return
    
    st.title("⚙️ Painel de Administração")
    
    aba1, aba2, aba3, aba4 = st.tabs(["Gerenciamento de Usuários", "Estatísticas do Sistema", "Gerenciamento do Banco de Dados", "Gerenciamento de Arquivos"])
    
    with aba1:
        st.subheader("Gerenciamento de Usuários")
        usuarios = obter_todos_usuarios()
        
        if usuarios:
            dados_usuarios = []
            for user in usuarios:
                dados_usuarios.append({
                    'ID': user[0],
                    'Nome': user[1],
                    'Email': user[2],
                    'Perfil': user[3],
                    'Criado': user[4]
                })
            
            df = pd.DataFrame(dados_usuarios)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhum usuário encontrado.")
    
    with aba2:
        st.subheader("Estatísticas do Sistema")
        
        problemas = obter_todos_problemas()
        usuarios = obter_todos_usuarios()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total de Tickets", len(problemas))
        with col2:
            st.metric("Total de Usuários", len(usuarios))
        with col3:
            st.metric("Em Andamento", len([p for p in problemas if p[6] == 'em andamento']))
        with col4:
            st.metric("Resolvidos", len([p for p in problemas if p[6] == 'resolvido']))
        
        # Distribuição de prioridade
        st.subheader("Distribuição de Prioridade")
        contagens_prioridade = {}
        for problema in problemas:
            prioridade = problema[5]
            contagens_prioridade[prioridade] = contagens_prioridade.get(prioridade, 0) + 1
        
        if contagens_prioridade:
            df_prioridade = pd.DataFrame(list(contagens_prioridade.items()), columns=['Prioridade', 'Contagem'])
            st.bar_chart(df_prioridade.set_index('Prioridade'))
    
    with aba3:
        st.subheader("Gerenciamento do Banco de Dados")
        
        if st.button("Exportar Dados para CSV"):
            # Exportar problemas
            problemas = obter_todos_problemas()
            if problemas:
                dados_problemas = []
                for problema in problemas:
                    dados_problemas.append({
                        'Ticket_ID': problema[1],
                        'Título': problema[2],
                        'Descrição': problema[3],
                        'Categoria': problema[4],
                        'Prioridade': problema[5],
                        'Status': problema[6],
                        'Submetido_Por': problema[12],
                        'Atribuído_Para': problema[13],
                        'Criado_Em': problema[8],
                        'Prazo': problema[9],
                        'Solução': problema[11]
                    })
                
                df_problemas = pd.DataFrame(dados_problemas)
                st.download_button(
                    label="Baixar CSV de Tickets",
                    data=df_problemas.to_csv(index=False),
                    file_name="exportacao_tickets.csv",
                    mime="text/csv"
                )
    
    with aba4:
        st.subheader("Gerenciamento de Arquivos")
        st.info("Os anexos de arquivos são gerenciados dentro dos tickets individuais.")

def mostrar_busca_web(usuario):
    st.title("🔍 Busca na Web e Pesquisa")
    
    aba1, aba2, aba3 = st.tabs(["Buscar na Web", "Resultados Salvos", "Extração de Conteúdo"])
    
    with aba1:
        st.subheader("Busca na Web")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            consulta_busca = st.text_input("Consulta de Busca", placeholder="Digite seus termos de busca...")
        with col2:
            max_resultados = st.number_input("Máx. Resultados", min_value=1, max_value=20, value=5)
        
        problema_id = st.selectbox(
            "Associar com Ticket (Opcional)",
            [""] + [f"{p[0]} - {p[1]}" for p in obter_problemas_usuario(usuario['id'])]
        )
        
        if st.button("Buscar na Web") and consulta_busca:
            with st.spinner("Buscando..."):
                resultados = buscar_na_web(consulta_busca, max_resultados)
                
                if resultados:
                    st.success(f"Encontrados {len(resultados)} resultados")
                    
                    for i, resultado in enumerate(resultados):
                        with st.expander(f"{i+1}. {resultado.get('title', 'Sem título')}"):
                            st.write(f"**URL:** {resultado.get('href', 'N/A')}")
                            st.write(f"**Trecho:** {resultado.get('body', 'N/A')}")
                            
                            col_s1, col_s2 = st.columns(2)
                            with col_s1:
                                if st.button(f"Salvar Resultado", key=f"salvar_{i}"):
                                    if problema_id:
                                        ticket_id = int(problema_id.split(' - ')[0])
                                        salvar_resultado_busca(
                                            ticket_id,
                                            consulta_busca,
                                            resultado.get('title', ''),
                                            resultado.get('href', ''),
                                            resultado.get('body', ''),
                                            "DuckDuckGo"
                                        )
                                        st.success("Resultado salvo no ticket!")
                                    else:
                                        st.error("Por favor, selecione um ticket para salvar o resultado")
                            
                            with col_s2:
                                if st.button(f"Extrair Conteúdo", key=f"extrair_{i}"):
                                    with st.spinner("Extraindo conteúdo..."):
                                        url = resultado.get('href', '')
                                        if url:
                                            conteudo = buscar_com_beautiful_soup(url)
                                            if 'erro' not in conteudo:
                                                st.write("**Conteúdo Extraído:**")
                                                st.text_area("Conteúdo", conteudo['conteudo'], height=200, key=f"conteudo_{i}")
                                            else:
                                                st.error(f"Extracão falhou: {conteudo['erro']}")
                                        else:
                                            st.error("URL não disponível para extração")
                else:
                    st.error("Nenhum resultado encontrado ou busca falhou")
    
    with aba2:
        st.subheader("Resultados de Busca Salvos")
        
        problemas_usuario = obter_problemas_usuario(usuario['id'])
        if problemas_usuario:
            ticket_selecionado = st.selectbox(
                "Selecionar Ticket para Ver Resultados Salvos",
                [f"{p[0]} - {p[1]}" for p in problemas_usuario]
            )
            
            if ticket_selecionado:
                ticket_id = int(ticket_selecionado.split(' - ')[0])
                resultados_salvos = obter_resultados_busca(ticket_id)
                
                if resultados_salvos:
                    for resultado in resultados_salvos:
                        with st.expander(f"{resultado[3]} - {resultado[6]}"):
                            st.write(f"**Consulta:** {resultado[2]}")
                            st.write(f"**URL:** {resultado[4]}")
                            st.write(f"**Trecho:** {resultado[5]}")
                            st.write(f"**Buscado em:** {resultado[7]}")
                else:
                    st.info("Nenhum resultado de busca salvo para este ticket")
        else:
            st.info("Nenhum ticket disponível para mostrar resultados de busca")
    
    with aba3:
        st.subheader("Ferramenta de Extração de Conteúdo")
        
        url = st.text_input("Digite a URL para extrair conteúdo")
        if st.button("Extrair Conteúdo") and url:
            with st.spinner("Extraindo conteúdo..."):
                conteudo = buscar_com_beautiful_soup(url)
                if 'erro' not in conteudo:
                    st.success("Conteúdo extraído com sucesso!")
                    st.write(f"**Título:** {conteudo['titulo']}")
                    st.write("**Conteúdo:**")
                    st.text_area("Conteúdo Extraído", conteudo['conteudo'], height=300)
                else:
                    st.error(f"Extracão falhou: {conteudo['erro']}")

# Adicionar rodapé de créditos
st.markdown("---")
st.markdown("**Créditos:** Plataforma de Resolução de Problemas desenvolvida por Paulo Monteiro")

if __name__ == "__main__":
    main()
