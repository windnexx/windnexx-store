import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'clave_secreta_windnexx_desarrollo'

# CONFIGURACIÓN DE FLASK-MAIL CON TUS CREDENCIALES
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'windnexx@gmail.com'
app.config['MAIL_PASSWORD'] = 'radpdohmtippatbm'
app.config['MAIL_DEFAULT_SENDER'] = 'windnexx@gmail.com'

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)

db_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelo de Usuario
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    telefono = db.Column(db.String(20), nullable=True, default='')
    password = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), default='cliente')
    confirmado = db.Column(db.Boolean, default=False)
    categoria = db.Column(db.String(20), default='Cliente')

# Modelo de Pedido
class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    nombre_cliente = db.Column(db.String(100), nullable=False)
    jugador_id = db.Column(db.String(50), nullable=False)
    detalle = db.Column(db.Text, nullable=False)
    total = db.Column(db.Float, nullable=False)
    telefono_digitos = db.Column(db.String(10), nullable=False)
    codigo_operacion = db.Column(db.String(50), nullable=False)
    estado = db.Column(db.String(50), default='Validación de pago') 
    fecha = db.Column(db.String(30), default=lambda: datetime.now().strftime('%d/%m/%Y %H:%M'))
    solo_fecha = db.Column(db.String(20), default=lambda: datetime.now().strftime('%d/%m/%Y'))

with app.app_context():
    db.create_all()
    
    # Asegurar automáticamente que las columnas existan en la tabla usuario de PostgreSQL
    try:
        with db.engine.connect() as connection:
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS telefono VARCHAR(20);'))
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS confirmado BOOLEAN DEFAULT FALSE;'))
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS categoria VARCHAR(20) DEFAULT \'Cliente\';'))
            connection.commit()
    except Exception as e:
        print("Aviso al verificar columnas en la BD:", e)
    
    # 1. Administrador Principal: windnexx@gmail.com
    admin_1 = Usuario.query.filter_by(correo='windnexx@gmail.com').first()
    if not admin_1:
        nuevo_admin_1 = Usuario(
            nombre='Administrador Windnexx',
            correo='windnexx@gmail.com',
            telefono='999999999',
            password=generate_password_hash('2244Nexxxx'),
            rol='admin',
            confirmado=True,
            categoria='Supercliente'
        )
        db.session.add(nuevo_admin_1)

    # 2. Segundo Administrador: croldan12345@gmail.com
    admin_2 = Usuario.query.filter_by(correo='croldan12345@gmail.com').first()
    if not admin_2:
        nuevo_admin_2 = Usuario(
            nombre='Administrador Carlos',
            correo='croldan12345@gmail.com',
            telefono='999999999',
            password=generate_password_hash('masterkeyne9999'),
            rol='admin',
            confirmado=True,
            categoria='Supercliente'
        )
        db.session.add(nuevo_admin_2)
        
    db.session.commit()

# Precios unitarios
PRECIOS = {
    'Fragmentos': 0.082,
    'Cajas': 0.45,
    'Pases': 3.00
}

# --- RUTAS DE NAVEGACIÓN ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip().lower()
        password = request.form.get('password', '')
        
        usuario = Usuario.query.filter_by(correo=correo).first()
        
        if usuario and check_password_hash(usuario.password, password):
            if not usuario.confirmado:
                flash('Debes confirmar tu correo electrónico antes de iniciar sesión. Revisa tu bandeja de entrada o spam.', 'warning')
                return redirect(url_for('login'))
            
            session['usuario_id'] = usuario.id
            session['nombre'] = usuario.nombre
            session['rol'] = usuario.rol
            
            if usuario.rol == 'admin':
                return redirect(url_for('admin_panel'))
            else:
                return redirect(url_for('cliente_home'))
        else:
            flash('Correo o contraseña incorrectos.', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        correo = request.form.get('correo', '').strip().lower()
        telefono = request.form.get('telefono', '').strip()
        password = request.form.get('password', '')
        
        if not nombre or not correo or not password:
            flash('Todos los campos obligatorios son requeridos.', 'danger')
            return redirect(url_for('register'))

        if Usuario.query.filter_by(correo=correo).first():
            flash('El correo ya está registrado.', 'danger')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password)
        nuevo_usuario = Usuario(
            nombre=nombre,
            correo=correo,
            telefono=telefono,
            password=hashed_password,
            rol='cliente',
            confirmado=False,
            categoria='Cliente'
        )
        
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        # Generar token seguro y enviar correo de activación
        token = serializer.dumps(correo, salt='email-confirm-salt')
        enlace_confirmacion = url_for('confirmar_correo', token=token, _external=True)
        
        try:
            msg = Message('Confirma tu cuenta en WINDNEXX Store', recipients=[correo])
            msg.body = f"""Hola {nombre},\n\nGracias por registrarte en WINDNEXX Store. 
Para activar tu cuenta y comenzar a realizar pedidos, por favor haz clic en el siguiente enlace:\n\n{enlace_confirmacion}\n\nSi no creaste esta cuenta, puedes ignorar este mensaje.\n\nAtentamente,\nSoporte WINDNEXX"""
            mail.send(msg)
            flash('¡Registro exitoso! Hemos enviado un enlace de confirmación a tu correo. Revisa tu bandeja de entrada o spam.', 'success')
        except Exception as e:
            flash('Registro creado, pero hubo un error al enviar el correo automático.', 'warning')
            print("Error enviando correo:", e)
            
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/confirmar/<token>')
def confirmar_correo(token):
    try:
        correo = serializer.loads(token, salt='email-confirm-salt', max_age=3600) # Válido por 1 hora
    except Exception:
        flash('El enlace de confirmación es inválido o ha expirado.', 'danger')
        return redirect(url_for('login'))
        
    usuario = Usuario.query.filter_by(correo=correo).first()
    if usuario:
        if usuario.confirmado:
            flash('Tu cuenta ya había sido confirmada anteriormente.', 'info')
        else:
            usuario.confirmado = True
            db.session.commit()
            flash('¡Correo confirmado exitosamente! Ya puedes iniciar sesión en tu cuenta.', 'success')
    else:
        flash('Usuario no encontrado.', 'danger')
        
    return redirect(url_for('login'))

# Panel Administrador
@app.route('/admin')
def admin_panel():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        flash('Acceso restringido para administradores.', 'danger')
        return redirect(url_for('login'))
        
    seccion_admin = request.args.get('seccion', 'pedidos_pendientes')
    
    usuarios_pendientes = Usuario.query.filter_by(confirmado=False).all()
    usuarios_confirmados = Usuario.query.filter_by(confirmado=True, rol='cliente').all()
    
    pedidos_validacion = Pedido.query.filter_by(estado='Validación de pago').all()
    pedidos_recargando = Pedido.query.filter_by(estado='Recargando').all()
    
    hoy_str = datetime.now().strftime('%d/%m/%Y')
    historial_envios = Pedido.query.filter_by(estado='Completado').order_by(Pedido.id.desc()).all()
    
    pedidos_hoy = [p for p in historial_envios if getattr(p, 'solo_fecha', hoy_str) == hoy_str]
    
    historicos_agrupados = {}
    for p in historial_envios:
        fecha_item = getattr(p, 'solo_fecha', hoy_str)
        if fecha_item != hoy_str:
            if fecha_item not in historicos_agrupados:
                historicos_agrupados[fecha_item] = []
            historicos_agrupados[fecha_item].append(p)
    
    return render_template