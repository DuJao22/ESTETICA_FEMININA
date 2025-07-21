from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import send_from_directory, jsonify
import sqlite3
import bcrypt
from datetime import datetime, timedelta
import os
import uuid
from PIL import Image
from functools import wraps

app = Flask(__name__)
app.secret_key = 'chave_secreta_salao_beleza_2024'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configuração de upload
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def resize_image(image_path, max_size=(400, 400)):
    """Redimensiona imagem mantendo proporção"""
    with Image.open(image_path) as img:
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        img.save(image_path, optimize=True, quality=85)

# Configuração do banco de dados
def inicializar_banco():
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Tabela de usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            login TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            tipo_usuario TEXT NOT NULL,
            especialidade TEXT,
            foto_perfil TEXT DEFAULT 'default-avatar.png',
            comissao_percentual REAL DEFAULT 30.0,
            ativo INTEGER DEFAULT 1,
            descricao TEXT,
            horario_inicio TIME DEFAULT '08:00',
            horario_fim TIME DEFAULT '18:00'
        )
    ''')
    
    # Tabela de clientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            telefone TEXT,
            foto_perfil TEXT DEFAULT 'default-avatar.png',
            ultima_visita DATE,
            total_visitas INTEGER DEFAULT 0,
            total_gasto REAL DEFAULT 0.0,
            data_cadastro DATE DEFAULT CURRENT_DATE,
            ativo INTEGER DEFAULT 1
        )
    ''')
    
    # Tabela de agendamentos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            funcionario_id INTEGER,
            data DATE NOT NULL,
            horario TIME NOT NULL,
            servico TEXT NOT NULL,
            valor REAL NOT NULL,
            status TEXT DEFAULT 'agendado',
            observacoes TEXT,
            sinal_pago INTEGER DEFAULT 0,
            valor_sinal REAL DEFAULT 0.0,
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes (id),
            FOREIGN KEY (funcionario_id) REFERENCES usuarios (id)
        )
    ''')
    
    # Tabela de comissões
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comissoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            funcionario_id INTEGER,
            agendamento_id INTEGER,
            valor REAL NOT NULL,
            data_criacao DATE DEFAULT CURRENT_DATE,
            pago INTEGER DEFAULT 0,
            FOREIGN KEY (funcionario_id) REFERENCES usuarios (id),
            FOREIGN KEY (agendamento_id) REFERENCES agendamentos (id)
        )
    ''')
    
    # Tabela de configurações
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY,
            nome_sistema TEXT DEFAULT 'Salão de Beleza',
            foto_sistema TEXT DEFAULT 'default-logo.png',
            endereco TEXT,
            telefone TEXT,
            email TEXT,
            instagram TEXT,
            whatsapp TEXT
        )
    ''')
    
    # Tabela de notificações
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notificacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            titulo TEXT NOT NULL,
            mensagem TEXT NOT NULL,
            agendamento_id INTEGER,
            lida INTEGER DEFAULT 0,
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agendamento_id) REFERENCES agendamentos (id)
        )
    ''')
    
    # Tabela de promoções
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            mensagem TEXT NOT NULL,
            status TEXT DEFAULT 'enviada',
            data_criacao DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (cliente_id) REFERENCES clientes (id)
        )
    ''')
    
    # Criar usuário administrador padrão
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE tipo_usuario = 'administrador'")
    if cursor.fetchone()[0] == 0:
        senha_hash = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt())
        cursor.execute('''
            INSERT INTO usuarios (nome, login, senha, tipo_usuario, especialidade)
            VALUES (?, ?, ?, ?, ?)
        ''', ('Administrador', 'admin', senha_hash, 'administrador', 'Gestão Geral'))
    
    # Inserir configuração inicial
    cursor.execute("SELECT COUNT(*) FROM configuracoes")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO configuracoes (nome_sistema, endereco, telefone, email) 
            VALUES (?, ?, ?, ?)
        ''', ('Salão de Beleza Elite', 'Rua das Flores, 123', '(11) 99999-9999', 'contato@salao.com'))
    
    conn.commit()
    conn.close()

# Rota para servir arquivos de upload
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# Decorador para verificar login
def login_requerido(f):
    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return funcao_decorada

# Decorador para verificar se é administrador
def admin_requerido(f):
    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        if 'usuario_id' not in session or session.get('tipo_usuario') != 'administrador':
            flash('Acesso negado. Apenas administradores podem acessar esta página.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return funcao_decorada

# Função para obter configurações
def obter_configuracoes():
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT nome_sistema, foto_sistema, endereco, telefone, email, instagram, whatsapp 
        FROM configuracoes LIMIT 1
    ''')
    config = cursor.fetchone()
    conn.close()
    return config or ('Salão de Beleza Elite', 'default-logo.png', '', '', '', '', '')

# ÁREA PÚBLICA - CLIENTES

@app.route('/cliente')
def area_cliente():
    """Página inicial para clientes"""
    config = obter_configuracoes()
    
    # Buscar funcionários ativos para exibir
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT nome, especialidade, foto_perfil, descricao
        FROM usuarios 
        WHERE tipo_usuario = 'funcionario' AND ativo = 1
        ORDER BY nome
    ''')
    funcionarios = cursor.fetchall()
    conn.close()
    
    return render_template('cliente/home.html', config=config, funcionarios=funcionarios)

@app.route('/cliente/cadastro', methods=['GET', 'POST'])
def cadastro_cliente():
    """Cadastro de novo cliente"""
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']
        telefone = request.form['telefone']
        
        # Hash da senha
        senha_hash = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt())
        
        conn = sqlite3.connect('salao_beleza.db')
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO clientes (nome, email, senha, telefone)
                VALUES (?, ?, ?, ?)
            ''', (nome, email, senha_hash, telefone))
            
            cliente_id = cursor.lastrowid
            conn.commit()
            
            # Login automático
            session['cliente_id'] = cliente_id
            session['cliente_nome'] = nome
            session['cliente_email'] = email
            
            flash('Cadastro realizado com sucesso! Bem-vindo!', 'success')
            return redirect(url_for('painel_cliente'))
            
        except sqlite3.IntegrityError:
            flash('Este e-mail já está cadastrado. Faça login.', 'error')
        finally:
            conn.close()
    
    config = obter_configuracoes()
    return render_template('cliente/cadastro.html', config=config)

@app.route('/cliente/login', methods=['GET', 'POST'])
def login_cliente():
    """Login de cliente"""
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        
        conn = sqlite3.connect('salao_beleza.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, nome, email, senha 
            FROM clientes WHERE email = ? AND ativo = 1
        ''', (email,))
        cliente = cursor.fetchone()
        conn.close()
        
        if cliente and bcrypt.checkpw(senha.encode('utf-8'), cliente[3]):
            session['cliente_id'] = cliente[0]
            session['cliente_nome'] = cliente[1]
            session['cliente_email'] = cliente[2]
            flash(f'Bem-vindo, {cliente[1]}!', 'success')
            return redirect(url_for('painel_cliente'))
        else:
            flash('E-mail ou senha incorretos!', 'error')
    
    config = obter_configuracoes()
    return render_template('cliente/login.html', config=config)

@app.route('/cliente/logout')
def logout_cliente():
    """Logout de cliente"""
    session.pop('cliente_id', None)
    session.pop('cliente_nome', None)
    session.pop('cliente_email', None)
    flash('Logout realizado com sucesso!', 'success')
    return redirect(url_for('area_cliente'))

# Decorador para verificar login de cliente
def cliente_login_requerido(f):
    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        if 'cliente_id' not in session:
            return redirect(url_for('login_cliente'))
        return f(*args, **kwargs)
    return funcao_decorada

@app.route('/cliente/painel')
@cliente_login_requerido
def painel_cliente():
    """Painel do cliente"""
    cliente_id = session['cliente_id']
    
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Dados do cliente
    cursor.execute('''
        SELECT nome, email, telefone, foto_perfil, total_visitas, total_gasto
        FROM clientes WHERE id = ?
    ''', (cliente_id,))
    cliente = cursor.fetchone()
    
    # Agendamentos do cliente
    cursor.execute('''
        SELECT a.id, a.data, a.horario, u.nome, a.servico, a.valor, a.status, 
               a.sinal_pago, a.valor_sinal
        FROM agendamentos a
        JOIN usuarios u ON a.funcionario_id = u.id
        WHERE a.cliente_id = ?
        ORDER BY a.data DESC, a.horario DESC
        LIMIT 10
    ''', (cliente_id,))
    agendamentos = cursor.fetchall()
    
    conn.close()
    config = obter_configuracoes()
    
    return render_template('cliente/painel.html', 
                         config=config, 
                         cliente=cliente, 
                         agendamentos=agendamentos)

@app.route('/cliente/agendar', methods=['GET', 'POST'])
@cliente_login_requerido
def agendar_servico():
    """Agendamento de serviço pelo cliente"""
    if request.method == 'POST':
        funcionario_id = request.form['funcionario_id']
        data = request.form['data']
        horario = request.form['horario']
        servico = request.form['servico']
        valor = float(request.form['valor'])
        
        # Calcular sinal (35%)
        valor_sinal = valor * 0.35
        
        conn = sqlite3.connect('salao_beleza.db')
        cursor = conn.cursor()
        
        # Verificar se horário está disponível
        cursor.execute('''
            SELECT COUNT(*) FROM agendamentos 
            WHERE funcionario_id = ? AND data = ? AND horario = ? AND status != 'cancelado'
        ''', (funcionario_id, data, horario))
        
        if cursor.fetchone()[0] > 0:
            flash('Este horário já está ocupado. Escolha outro.', 'error')
        else:
            # Criar agendamento
            cursor.execute('''
                INSERT INTO agendamentos (cliente_id, funcionario_id, data, horario, servico, valor, valor_sinal)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (session['cliente_id'], funcionario_id, data, horario, servico, valor, valor_sinal))
            
            agendamento_id = cursor.lastrowid
            
            # Criar notificação para admin
            cursor.execute('''
                INSERT INTO notificacoes (tipo, titulo, mensagem, agendamento_id)
                VALUES (?, ?, ?, ?)
            ''', ('novo_agendamento', 'Novo Agendamento', 
                  f'Cliente {session["cliente_nome"]} fez um agendamento. Aguardando pagamento do sinal.', 
                  agendamento_id))
            
            conn.commit()
            flash(f'Agendamento realizado! Pague o sinal de R$ {valor_sinal:.2f} para confirmar.', 'success')
            return redirect(url_for('painel_cliente'))
        
        conn.close()
    
    # Buscar funcionários e horários disponíveis
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, nome, especialidade, foto_perfil, descricao, horario_inicio, horario_fim
        FROM usuarios 
        WHERE tipo_usuario = 'funcionario' AND ativo = 1
        ORDER BY nome
    ''')
    funcionarios = cursor.fetchall()
    conn.close()
    
    config = obter_configuracoes()
    return render_template('cliente/agendar.html', config=config, funcionarios=funcionarios)

@app.route('/cliente/perfil', methods=['GET', 'POST'])
@cliente_login_requerido
def perfil_cliente():
    """Perfil do cliente"""
    cliente_id = session['cliente_id']
    
    if request.method == 'POST':
        nome = request.form['nome']
        telefone = request.form['telefone']
        nova_senha = request.form.get('nova_senha')
        
        conn = sqlite3.connect('salao_beleza.db')
        cursor = conn.cursor()
        
        # Upload de foto
        foto_perfil = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename and allowed_file(file.filename):
                filename = f"cliente_{cliente_id}_{uuid.uuid4().hex[:8]}.{file.filename.rsplit('.', 1)[1].lower()}"
                filepath = os.path.join(UPLOAD_FOLDER, 'clientes', filename)
                file.save(filepath)
                resize_image(filepath)
                foto_perfil = f"clientes/{filename}"
        
        # Atualizar dados
        if nova_senha and foto_perfil:
            senha_hash = bcrypt.hashpw(nova_senha.encode('utf-8'), bcrypt.gensalt())
            cursor.execute('''
                UPDATE clientes SET nome = ?, telefone = ?, foto_perfil = ?, senha = ?
                WHERE id = ?
            ''', (nome, telefone, foto_perfil, senha_hash, cliente_id))
        elif nova_senha:
            senha_hash = bcrypt.hashpw(nova_senha.encode('utf-8'), bcrypt.gensalt())
            cursor.execute('''
                UPDATE clientes SET nome = ?, telefone = ?, senha = ?
                WHERE id = ?
            ''', (nome, telefone, senha_hash, cliente_id))
        elif foto_perfil:
            cursor.execute('''
                UPDATE clientes SET nome = ?, telefone = ?, foto_perfil = ?
                WHERE id = ?
            ''', (nome, telefone, foto_perfil, cliente_id))
        else:
            cursor.execute('''
                UPDATE clientes SET nome = ?, telefone = ?
                WHERE id = ?
            ''', (nome, telefone, cliente_id))
        
        conn.commit()
        conn.close()
        
        session['cliente_nome'] = nome
        if nova_senha:
            flash('Perfil e senha atualizados com sucesso!', 'success')
        else:
            flash('Perfil atualizado com sucesso!', 'success')
        return redirect(url_for('perfil_cliente'))
    
    # Buscar dados do cliente
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT nome, email, telefone, foto_perfil, total_visitas, total_gasto, data_cadastro
        FROM clientes WHERE id = ?
    ''', (cliente_id,))
    cliente = cursor.fetchone()
    conn.close()
    
    config = obter_configuracoes()
    return render_template('cliente/perfil.html', config=config, cliente=cliente)

@app.route('/cliente/confirmar_pagamento/<int:agendamento_id>')
@cliente_login_requerido
def confirmar_pagamento_cliente(agendamento_id):
    """Cliente confirma que fez o pagamento do sinal"""
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Verificar se o agendamento pertence ao cliente
    cursor.execute('''
        SELECT id, valor_sinal FROM agendamentos 
        WHERE id = ? AND cliente_id = ? AND sinal_pago = 0
    ''', (agendamento_id, session['cliente_id']))
    
    agendamento = cursor.fetchone()
    if agendamento:
        # Marcar como pagamento enviado (aguardando confirmação do admin)
        cursor.execute('''
            UPDATE agendamentos SET status = 'aguardando_confirmacao'
            WHERE id = ?
        ''', (agendamento_id,))
        
        # Criar notificação para admin
        cursor.execute('''
            INSERT INTO notificacoes (tipo, titulo, mensagem, agendamento_id)
            VALUES (?, ?, ?, ?)
        ''', ('pagamento_enviado', 'Pagamento Enviado', 
              f'Cliente {session["cliente_nome"]} confirmou o pagamento do sinal.', 
              agendamento_id))
        
        conn.commit()
        flash('Pagamento confirmado! Aguarde a validação do estabelecimento.', 'success')
    else:
        flash('Agendamento não encontrado ou já confirmado.', 'error')
    
    conn.close()
    return redirect(url_for('painel_cliente'))

# ÁREA ADMINISTRATIVA - MODIFICAÇÕES


@app.route('/')
def index():
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('area_cliente'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_usuario = request.form['login']
        senha = request.form['senha']
        
        conn = sqlite3.connect('salao_beleza.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, nome, senha, tipo_usuario, especialidade 
            FROM usuarios WHERE login = ? AND ativo = 1
        ''', (login_usuario,))
        usuario = cursor.fetchone()
        conn.close()
        
        if usuario and bcrypt.checkpw(senha.encode('utf-8'), usuario[2]):
            session['usuario_id'] = usuario[0]
            session['nome_usuario'] = usuario[1]
            session['tipo_usuario'] = usuario[3]
            session['especialidade'] = usuario[4]
            flash(f'Bem-vindo, {usuario[1]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Login ou senha incorretos!', 'error')
    
    config = obter_configuracoes()
    return render_template('login.html', config=config)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logout realizado com sucesso!', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_requerido
def dashboard():
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Buscar notificações não lidas
    cursor.execute('''
        SELECT id, tipo, titulo, mensagem, agendamento_id, data_criacao
        FROM notificacoes 
        WHERE lida = 0 
        ORDER BY data_criacao DESC
        LIMIT 10
    ''')
    notificacoes = cursor.fetchall()
    
    # Estatísticas gerais
    hoje = datetime.now().date()
    inicio_mes = hoje.replace(day=1)
    
    if session['tipo_usuario'] == 'administrador':
        # Dashboard administrativo
        cursor.execute("SELECT COUNT(*) FROM agendamentos WHERE data = ?", (hoje,))
        agendamentos_hoje = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE tipo_usuario = 'funcionario' AND ativo = 1")
        total_funcionarios = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COALESCE(SUM(valor), 0) FROM agendamentos 
            WHERE data >= ? AND status = 'concluido'
        ''', (inicio_mes,))
        faturamento_mes = cursor.fetchone()[0]
        
        # Agendamentos por funcionário
        cursor.execute('''
            SELECT u.nome, COUNT(a.id) as total
            FROM usuarios u
            LEFT JOIN agendamentos a ON u.id = a.funcionario_id AND a.data = ?
            WHERE u.tipo_usuario = 'funcionario' AND u.ativo = 1
            GROUP BY u.id, u.nome
            ORDER BY total DESC
        ''', (hoje,))
        agendamentos_funcionario = cursor.fetchall()
        
    else:
        # Dashboard do funcionário
        funcionario_id = session['usuario_id']
        
        cursor.execute('''
            SELECT COUNT(*) FROM agendamentos 
            WHERE funcionario_id = ? AND data = ?
        ''', (funcionario_id, hoje))
        agendamentos_hoje = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COALESCE(SUM(valor), 0) FROM agendamentos 
            WHERE funcionario_id = ? AND data >= ? AND status = 'concluido'
        ''', (funcionario_id, inicio_mes))
        faturamento_mes = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COALESCE(SUM(valor), 0) FROM comissoes 
            WHERE funcionario_id = ? AND data_criacao >= ? AND pago = 0
        ''', (funcionario_id, inicio_mes))
        comissoes_pendentes = cursor.fetchone()[0]
        
        agendamentos_funcionario = []
        total_clientes = 0
        total_funcionarios = 0
    
    # Próximos agendamentos
    cursor.execute('''
        SELECT a.data, a.horario, c.nome, a.servico, u.nome
        FROM agendamentos a
        JOIN clientes c ON a.cliente_id = c.id
        JOIN usuarios u ON a.funcionario_id = u.id
        WHERE a.data >= ? AND a.status = 'agendado'
        ORDER BY a.data, a.horario
        LIMIT 5
    ''', (hoje,))
    proximos_agendamentos = cursor.fetchall()
    
    conn.close()
    config = obter_configuracoes()
    
    return render_template('dashboard.html', 
                         config=config,
                         agendamentos_hoje=agendamentos_hoje,
                         total_clientes=total_clientes,
                         total_funcionarios=total_funcionarios,
                         faturamento_mes=faturamento_mes,
                         agendamentos_funcionario=agendamentos_funcionario,
                         proximos_agendamentos=proximos_agendamentos,
                        comissoes_pendentes=locals().get('comissoes_pendentes', 0),
                        notificacoes=notificacoes)

@app.route('/marcar_notificacao_lida/<int:notificacao_id>')
@login_requerido
def marcar_notificacao_lida(notificacao_id):
    """Marcar notificação como lida"""
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE notificacoes SET lida = 1 WHERE id = ?", (notificacao_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/confirmar_pagamento_admin/<int:agendamento_id>')
@admin_requerido
def confirmar_pagamento_admin(agendamento_id):
    """Admin confirma o recebimento do pagamento"""
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Atualizar agendamento
    cursor.execute('''
        UPDATE agendamentos SET sinal_pago = 1, status = 'confirmado'
        WHERE id = ?
    ''', (agendamento_id,))
    
    # Marcar notificações relacionadas como lidas
    cursor.execute('''
        UPDATE notificacoes SET lida = 1 
        WHERE agendamento_id = ?
    ''', (agendamento_id,))
    
    conn.commit()
    conn.close()
    
    flash('Pagamento confirmado! Agendamento validado.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/agendamentos')
@login_requerido
def agendamentos():
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    if session['tipo_usuario'] == 'administrador':
        cursor.execute('''
            SELECT a.id, a.data, a.horario, c.nome, u.nome, a.servico, a.valor, a.status, a.sinal_pago, a.valor_sinal
            FROM agendamentos a
            JOIN clientes c ON a.cliente_id = c.id
            JOIN usuarios u ON a.funcionario_id = u.id
            ORDER BY a.data DESC, a.horario DESC
        ''')
    else:
        cursor.execute('''
            SELECT a.id, a.data, a.horario, c.nome, u.nome, a.servico, a.valor, a.status, a.sinal_pago, a.valor_sinal
            FROM agendamentos a
            JOIN clientes c ON a.cliente_id = c.id
            JOIN usuarios u ON a.funcionario_id = u.id
            WHERE a.funcionario_id = ?
            ORDER BY a.data DESC, a.horario DESC
        ''', (session['usuario_id'],))
    
    lista_agendamentos = cursor.fetchall()
    
    # Buscar clientes e funcionários para o formulário
    cursor.execute("SELECT id, nome FROM clientes ORDER BY nome")
    clientes = cursor.fetchall()
    
    if session['tipo_usuario'] == 'administrador':
        cursor.execute("SELECT id, nome FROM usuarios WHERE tipo_usuario = 'funcionario' AND ativo = 1 ORDER BY nome")
        funcionarios = cursor.fetchall()
    else:
        funcionarios = [(session['usuario_id'], session['nome_usuario'])]
    
    conn.close()
    config = obter_configuracoes()
    
    return render_template('agendamentos.html', 
                         config=config,
                         agendamentos=lista_agendamentos,
                         clientes=clientes,
                         funcionarios=funcionarios)

@app.route('/novo_agendamento', methods=['POST'])
@login_requerido
def novo_agendamento():
    cliente_id = request.form['cliente_id']
    funcionario_id = request.form['funcionario_id']
    data = request.form['data']
    horario = request.form['horario']
    servico = request.form['servico']
    valor = float(request.form['valor'])
    
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Inserir agendamento
    cursor.execute('''
        INSERT INTO agendamentos (cliente_id, funcionario_id, data, horario, servico, valor)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (cliente_id, funcionario_id, data, horario, servico, valor))
    
    agendamento_id = cursor.lastrowid
    
    # Criar comissão
    cursor.execute("SELECT comissao_percentual FROM usuarios WHERE id = ?", (funcionario_id,))
    percentual = cursor.fetchone()[0] or 30.0
    valor_comissao = valor * (percentual / 100)
    
    cursor.execute('''
        INSERT INTO comissoes (funcionario_id, agendamento_id, valor)
        VALUES (?, ?, ?)
    ''', (funcionario_id, agendamento_id, valor_comissao))
    
    conn.commit()
    conn.close()
    
    flash('Agendamento criado com sucesso!', 'success')
    return redirect(url_for('agendamentos'))

@app.route('/finalizar_agendamento/<int:agendamento_id>')
@login_requerido
def finalizar_agendamento(agendamento_id):
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Atualizar status do agendamento
    cursor.execute("UPDATE agendamentos SET status = 'concluido' WHERE id = ?", (agendamento_id,))
    
    # Atualizar dados do cliente
    cursor.execute('''
        SELECT cliente_id, valor FROM agendamentos WHERE id = ?
    ''', (agendamento_id,))
    cliente_id, valor = cursor.fetchone()
    
    cursor.execute('''
        UPDATE clientes SET 
            ultima_visita = CURRENT_DATE,
            total_visitas = total_visitas + 1,
            total_gasto = total_gasto + ?
        WHERE id = ?
    ''', (valor, cliente_id))
    
    conn.commit()
    conn.close()
    
    flash('Agendamento finalizado com sucesso!', 'success')
    return redirect(url_for('agendamentos'))

@app.route('/clientes')
@login_requerido
def clientes():
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, nome, telefone, email, ultima_visita, total_visitas, total_gasto
        FROM clientes
        ORDER BY nome
    ''')
    lista_clientes = cursor.fetchall()
    
    conn.close()
    config = obter_configuracoes()
    
    return render_template('clientes.html', config=config, clientes=lista_clientes)

@app.route('/novo_cliente', methods=['POST'])
@login_requerido
def novo_cliente():
    nome = request.form['nome']
    telefone = request.form['telefone']
    email = request.form['email']
    
    # Gerar senha temporária para clientes criados pelo admin
    senha_temporaria = 'cliente123'
    senha_hash = bcrypt.hashpw(senha_temporaria.encode('utf-8'), bcrypt.gensalt())
    
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO clientes (nome, telefone, email, senha)
            VALUES (?, ?, ?, ?)
        ''', (nome, telefone, email, senha_hash))
        
        conn.commit()
        flash(f'Cliente cadastrado com sucesso! Senha temporária: {senha_temporaria}', 'success')
    except sqlite3.IntegrityError:
        flash('Este e-mail já está cadastrado.', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('clientes'))

@app.route('/funcionarios')
@admin_requerido
def funcionarios():
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, nome, login, especialidade, comissao_percentual, ativo
        FROM usuarios
        WHERE tipo_usuario = 'funcionario'
        ORDER BY nome
    ''')
    lista_funcionarios = cursor.fetchall()
    
    conn.close()
    config = obter_configuracoes()
    
    return render_template('funcionarios.html', config=config, funcionarios=lista_funcionarios)

@app.route('/novo_funcionario', methods=['POST'])
@admin_requerido
def novo_funcionario():
    nome = request.form['nome']
    login = request.form['login']
    senha = request.form['senha']
    especialidade = request.form['especialidade']
    descricao = request.form.get('descricao', '')
    comissao = float(request.form['comissao'])
    
    # Upload de foto
    foto_perfil = 'default-avatar.png'
    if 'foto' in request.files:
        file = request.files['foto']
        if file and file.filename and allowed_file(file.filename):
            filename = f"funcionario_{uuid.uuid4().hex[:8]}.{file.filename.rsplit('.', 1)[1].lower()}"
            filepath = os.path.join(UPLOAD_FOLDER, 'funcionarios', filename)
            file.save(filepath)
            resize_image(filepath)
            foto_perfil = f"funcionarios/{filename}"
    
    senha_hash = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt())
    
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO usuarios (nome, login, senha, tipo_usuario, especialidade, comissao_percentual, foto_perfil, descricao)
            VALUES (?, ?, ?, 'funcionario', ?, ?, ?, ?)
        ''', (nome, login, senha_hash, especialidade, comissao, foto_perfil, descricao))
        
        conn.commit()
        flash('Funcionário cadastrado com sucesso!', 'success')
    except sqlite3.IntegrityError:
        flash('Login já existe. Escolha outro login.', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('funcionarios'))

@app.route('/relatorios')
@login_requerido
def relatorios():
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Filtros
    data_inicio = request.args.get('data_inicio', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    data_fim = request.args.get('data_fim', datetime.now().strftime('%Y-%m-%d'))
    
    if session['tipo_usuario'] == 'administrador':
        # Faturamento por funcionário
        cursor.execute('''
            SELECT u.nome, u.especialidade, COUNT(a.id) as atendimentos, COALESCE(SUM(a.valor), 0) as faturamento
            FROM usuarios u
            LEFT JOIN agendamentos a ON u.id = a.funcionario_id 
                AND a.data BETWEEN ? AND ? AND a.status = 'concluido'
            WHERE u.tipo_usuario = 'funcionario' AND u.ativo = 1
            GROUP BY u.id, u.nome, u.especialidade
            ORDER BY faturamento DESC
        ''', (data_inicio, data_fim))
        faturamento_funcionarios = cursor.fetchall()
        
        # Comissões pendentes
        cursor.execute('''
            SELECT u.nome, COALESCE(SUM(c.valor), 0) as comissoes_pendentes
            FROM usuarios u
            LEFT JOIN comissoes c ON u.id = c.funcionario_id AND c.pago = 0
            WHERE u.tipo_usuario = 'funcionario' AND u.ativo = 1
            GROUP BY u.id, u.nome
            ORDER BY comissoes_pendentes DESC
        ''')
        comissoes_pendentes = cursor.fetchall()
    else:
        funcionario_id = session['usuario_id']
        
        cursor.execute('''
            SELECT COUNT(id) as atendimentos, COALESCE(SUM(valor), 0) as faturamento
            FROM agendamentos
            WHERE funcionario_id = ? AND data BETWEEN ? AND ? AND status = 'concluido'
        ''', (funcionario_id, data_inicio, data_fim))
        resultado = cursor.fetchone()
        faturamento_funcionarios = [(session['nome_usuario'], session['especialidade'], resultado[0], resultado[1])]
        
        cursor.execute('''
            SELECT COALESCE(SUM(valor), 0) as comissoes_pendentes
            FROM comissoes
            WHERE funcionario_id = ? AND pago = 0
        ''', (funcionario_id,))
        total_comissoes = cursor.fetchone()[0]
        comissoes_pendentes = [(session['nome_usuario'], total_comissoes)]
    
    conn.close()
    config = obter_configuracoes()
    
    return render_template('relatorios.html', 
                         config=config,
                         faturamento_funcionarios=faturamento_funcionarios,
                         comissoes_pendentes=comissoes_pendentes,
                         data_inicio=data_inicio,
                         data_fim=data_fim)

@app.route('/promocoes')
@admin_requerido
def promocoes():
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Clientes fiéis (mais de 5 visitas)
    cursor.execute('''
        SELECT id, nome, telefone, total_visitas, total_gasto
        FROM clientes
        WHERE total_visitas >= 5
        ORDER BY total_visitas DESC
    ''')
    clientes_fieis = cursor.fetchall()
    
    # Promoções enviadas
    cursor.execute('''
        SELECT p.id, c.nome, p.mensagem, p.data_criacao, p.status
        FROM promocoes p
        JOIN clientes c ON p.cliente_id = c.id
        ORDER BY p.data_criacao DESC
        LIMIT 20
    ''')
    promocoes_enviadas = cursor.fetchall()
    
    conn.close()
    config = obter_configuracoes()
    
    return render_template('promocoes.html', 
                         config=config,
                         clientes_fieis=clientes_fieis,
                         promocoes_enviadas=promocoes_enviadas)

@app.route('/enviar_promocao', methods=['POST'])
@admin_requerido
def enviar_promocao():
    cliente_id = request.form['cliente_id']
    mensagem = request.form['mensagem']
    
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO promocoes (cliente_id, mensagem)
        VALUES (?, ?)
    ''', (cliente_id, mensagem))
    
    conn.commit()
    conn.close()
    
    flash('Promoção enviada com sucesso!', 'success')
    return redirect(url_for('promocoes'))

@app.route('/configuracoes', methods=['GET', 'POST'])
@admin_requerido
def configuracoes():
    if request.method == 'POST':
        nome_sistema = request.form['nome_sistema']
        endereco = request.form.get('endereco', '')
        telefone = request.form.get('telefone', '')
        email = request.form.get('email', '')
        instagram = request.form.get('instagram', '')
        whatsapp = request.form.get('whatsapp', '')
        
        # Upload de logo
        foto_sistema = None
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename and allowed_file(file.filename):
                filename = f"logo_{uuid.uuid4().hex[:8]}.{file.filename.rsplit('.', 1)[1].lower()}"
                filepath = os.path.join(UPLOAD_FOLDER, 'empresa', filename)
                file.save(filepath)
                resize_image(filepath)
                foto_sistema = f"empresa/{filename}"
        
        conn = sqlite3.connect('salao_beleza.db')
        cursor = conn.cursor()
        
        if foto_sistema:
            cursor.execute('''
                UPDATE configuracoes SET nome_sistema = ?, foto_sistema = ?, endereco = ?, 
                       telefone = ?, email = ?, instagram = ?, whatsapp = ?
                WHERE id = 1
            ''', (nome_sistema, foto_sistema, endereco, telefone, email, instagram, whatsapp))
        else:
            cursor.execute('''
                UPDATE configuracoes SET nome_sistema = ?, endereco = ?, 
                       telefone = ?, email = ?, instagram = ?, whatsapp = ?
                WHERE id = 1
            ''', (nome_sistema, endereco, telefone, email, instagram, whatsapp))
        
        conn.commit()
        conn.close()
        
        flash('Configurações salvas com sucesso!', 'success')
        return redirect(url_for('configuracoes'))
    
    config = obter_configuracoes()
    return render_template('configuracoes.html', config=config)

@app.route('/api/horarios_disponiveis')
def horarios_disponiveis():
    """API para buscar horários disponíveis"""
    funcionario_id = request.args.get('funcionario_id')
    data = request.args.get('data')
    
    if not funcionario_id or not data:
        return jsonify([])
    
    conn = sqlite3.connect('salao_beleza.db')
    cursor = conn.cursor()
    
    # Buscar horários ocupados
    cursor.execute('''
        SELECT horario FROM agendamentos 
        WHERE funcionario_id = ? AND data = ? AND status != 'cancelado'
    ''', (funcionario_id, data))
    
    horarios_ocupados = [row[0] for row in cursor.fetchall()]
    
    # Buscar horário de trabalho do funcionário
    cursor.execute('''
        SELECT horario_inicio, horario_fim FROM usuarios 
        WHERE id = ?
    ''', (funcionario_id,))
    
    horario_trabalho = cursor.fetchone()
    conn.close()
    
    if not horario_trabalho:
        return jsonify([])
    
    # Gerar horários disponíveis (de hora em hora)
    inicio = datetime.strptime(horario_trabalho[0], '%H:%M').time()
    fim = datetime.strptime(horario_trabalho[1], '%H:%M').time()
    
    horarios_disponiveis = []
    hora_atual = datetime.combine(datetime.today(), inicio)
    hora_fim = datetime.combine(datetime.today(), fim)
    
    while hora_atual < hora_fim:
        horario_str = hora_atual.strftime('%H:%M')
        if horario_str not in horarios_ocupados:
            horarios_disponiveis.append(horario_str)
        hora_atual += timedelta(hours=1)
    
    return jsonify(horarios_disponiveis)

@app.route('/creditos')
def creditos():
    config = obter_configuracoes()
    return render_template('creditos.html', config=config)

@app.route('/contato', methods=['POST'])
def contato():
    nome = request.form['nome']
    email = request.form['email']
    mensagem = request.form['mensagem']
    
    # Aqui você pode implementar o envio de email
    flash(f'Obrigado {nome}! Sua mensagem foi enviada com sucesso. Retornaremos em breve!', 'success')
    return redirect(url_for('creditos'))

if __name__ == '__main__':
    inicializar_banco()
    app.run(debug=True)