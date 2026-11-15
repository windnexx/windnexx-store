import os
import re
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import text

# Importaciones para Google OAuth, Enlaces Seguros y Envío de Correo
from authlib.integrations.flask_client import OAuth
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message

try:
    import pandas as pd
    EXCEL_DISPONIBLE = True
except ImportError:
    EXCEL_DISPONIBLE = False

app = Flask(__name__)

# Corrección obligatoria para Render (Proxy HTTPS)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['PREFERRED_URL_SCHEME'] = 'https'

app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_windnexx_desarrollo')

# Configuración de Flask-Mail
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME'))

mail = Mail(app)

# Configuración de Google OAuth
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

serializer = URLSafeTimedSerializer(app.secret_key)

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

TIMEZONE_LIMA = ZoneInfo("America/Lima")

def hora_lima():
    return datetime.now(TIMEZONE_LIMA)

# Modelo de Usuario
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    telefono = db.Column(db.String(20), nullable=True, default='')
    password = db.Column(db.String(200), nullable=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    correo_verificado = db.Column(db.Boolean, default=False)
    rol = db.Column(db.String(20), default='cliente')
    confirmado = db.Column(db.Boolean, default=True)
    categoria = db.Column(db.String(20), default='Cliente')
    solicitud_reset = db.Column(db.Boolean, default=False)
    ultima_actividad = db.Column(db.DateTime, nullable=True)
    codigo_referido = db.Column(db.String(20), unique=True, nullable=True)
    referido_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    rango = db.Column(db.String(20), default='Bronce')

class ConfiguracionGlobal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    anuncio_publicidad = db.Column(db.Text, default='¡Bienvenidos a WINDNEXX Store! Aprovecha los mejores descuentos.')

class CodigoPromo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    descuento_porcentaje = db.Column(db.Float, nullable=False)
    tipo_limite = db.Column(db.String(20), default='ilimitado')
    max_usos_primeras = db.Column(db.Integer, default=0) 
    usos_actuales = db.Column(db.Integer, default=0)
    es_premio_referido = db.Column(db.Boolean, default=False)
    propietario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)

class ConfiguracionReferido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_premio = db.Column(db.String(100), default='Descuento por Referido')
    descuento_porcentaje = db.Column(db.Float, default=6.0)

class UsoCodigoUsuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    codigo_id = db.Column(db.Integer, db.ForeignKey('codigo_promo.id'), nullable=False)

class RegistroReferido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patrocinador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    referido_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    meta_cumplida = db.Column(db.Boolean, default=False)
    fecha = db.Column(db.String(30), default=lambda: hora_lima().strftime('%d/%m/%Y %H:%M'))

class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    nombre_cliente = db.Column(db.String(100), nullable=False)
    jugador_id = db.Column(db.String(50), nullable=False)
    detalle = db.Column(db.Text, nullable=False)
    total = db.Column(db.Float, nullable=False)
    telefono_digitos = db.Column(db.String(10), nullable=False)
    codigo_operacion = db.Column(db.String(50), nullable=False)
    codigo_promo = db.Column(db.String(50), nullable=True, default='')
    descuento_aplicado = db.Column(db.Float, nullable=True, default=0.0)
    estado = db.Column(db.String(50), default='Validación de pago') 
    fecha = db.Column(db.String(30), default=lambda: hora_lima().strftime('%d/%m/%Y %H:%M'))
    solo_fecha = db.Column(db.String(20), default=lambda: hora_lima().strftime('%d/%m/%Y'))

class MensajeSoporte(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    imagen = db.Column(db.String(255), nullable=True)
    estado = db.Column(db.String(20), default='Pendiente')
    fecha = db.Column(db.String(30), default=lambda: hora_lima().strftime('%d/%m/%Y %H:%M'))

with app.app_context():
    db.create_all()
    try:
        db.session.execute(text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS google_id VARCHAR(100) UNIQUE;"))
        db.session.execute(text("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS correo_verificado BOOLEAN DEFAULT FALSE;"))
        db.session.execute(text("UPDATE usuario SET correo_verificado = TRUE WHERE correo_verificado IS FALSE AND google_id IS NULL AND password IS NOT NULL;"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Nota de migración: {e}")

    if not ConfiguracionGlobal.query.first():
        conf_g = ConfiguracionGlobal(anuncio_publicidad='¡Aprovecha los mejores descuentos en productos de Free Fire!')
        db.session.add(conf_g)
        db.session.commit()

    if not ConfiguracionReferido.query.first():
        conf_inicial = ConfiguracionReferido(nombre_premio='Cupón de Recompensa de Referido', descuento_porcentaje=6.0)
        db.session.add(conf_inicial)
        db.session.commit()

    for u in Usuario.query.filter_by(codigo_referido=None).all():
        u.codigo_referido = f"WIND-{u.id}-{os.urandom(2).hex().upper()}"
    db.session.commit()

    admin_1 = Usuario.query.filter_by(correo='windnexx@gmail.com').first()
    if not admin_1:
        nuevo_admin_1 = Usuario(
            nombre='Administrador Nomar',
            correo='windnexx@gmail.com',
            telefono='999999999',
            password=generate_password_hash('2244Nexxxx'),
            rol='admin',
            confirmado=True,
            correo_verificado=True,
            categoria='Supercliente',
            codigo_referido='WIND-ADMIN-1'
        )
        db.session.add(nuevo_admin_1)

    admin_2 = Usuario.query.filter_by(correo='croldan12345@gmail.com').first()
    if not admin_2:
        nuevo_admin_2 = Usuario(
            nombre='Administrador Carlos',
            correo='croldan12345@gmail.com',
            telefono='999999999',
            password=generate_password_hash('masterkeyne9999'),
            rol='admin',
            confirmado=True,
            correo_verificado=True,
            categoria='Supercliente',
            codigo_referido='WIND-ADMIN-2'
        )
        db.session.add(nuevo_admin_2)
        
    db.session.commit()

@app.before_request
def actualizar_actividad_usuario():
    if 'usuario_id' in session and request.endpoint != 'static':
        usuario = db.session.get(Usuario, session['usuario_id'])
        if usuario:
            usuario.ultima_actividad = datetime.now(TIMEZONE_LIMA).replace(tzinfo=None)
            db.session.commit()

@app.route('/api/ping')
def ping_actividad():
    return jsonify({"status": "ok"})

PRECIOS = {'Fragmentos': 0.082, 'Cajas': 0.45, 'Pases': 3.00}

def calcular_estadisticas_usuario(usuario_id):
    pedidos_completados = Pedido.query.filter_by(usuario_id=usuario_id, estado='Completado').all()
    total_pases = 0
    total_fragmentos = 0
    total_cajas = 0
    monto_total_comprado = 0.0

    for p in pedidos_completados:
        m_frag = re.search(r'Fragmentos \(x(\d+)\)', p.detalle)
        if m_frag: total_fragmentos += int(m_frag.group(1))
        m_cajas = re.search(r'Cajas \(x(\d+)\)', p.detalle)
        if m_cajas: total_cajas += int(m_cajas.group(1))
        m_pases = re.search(r'Pases \(x(\d+)\)', p.detalle)
        if m_pases: total_pases += int(m_pases.group(1))
        monto_total_comprado += (p.total + (p.descuento_aplicado or 0.0))

    fragmentos_equivalentes = int(round(monto_total_comprado / PRECIOS['Fragmentos']))
    return total_pases, total_fragmentos, total_cajas, fragmentos_equivalentes

@app.route('/')
def index():
    return redirect(url_for('login'))

# --- RUTAS DE GOOGLE OAUTH ---
@app.route('/login/google')
def login_google():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/google/callback')
def google_callback():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            user_info = google.get('https://www.googleapis.com/oauth2/v3/userinfo').json()
            
        correo = user_info.get('email').lower()
        nombre = user_info.get('name', 'Usuario Google')
        google_id = user_info.get('sub')

        usuario = Usuario.query.filter_by(correo=correo).first()
        
        if usuario:
            if not usuario.google_id:
                usuario.google_id = google_id
                usuario.correo_verificado = True
                db.session.commit()
            
            session['usuario_id'] = usuario.id
            session['nombre'] = usuario.nombre
            session['correo'] = usuario.correo
            session['rol'] = usuario.rol
            
            if usuario.rol == 'admin':
                return redirect(url_for('admin_panel'))
            else:
                return redirect(url_for('cliente_home'))
        else:
            session['google_temp'] = {'correo': correo, 'nombre': nombre, 'google_id': google_id}
            return redirect(url_for('completar_registro_google'))
            
    except Exception as e:
        print("ERROR OAUTH GOOGLE:", str(e))
        flash(f'Error al autenticar con Google: {str(e)}', 'danger')
        return redirect(url_for('login'))

@app.route('/completar-registro-google', methods=['GET', 'POST'])
def completar_registro_google():
    if 'google_temp' not in session:
        return redirect(url_for('login'))
        
    datos_google = session['google_temp']
    
    if request.method == 'POST':
        telefono = request.form.get('telefono', '').strip()
        password = request.form.get('password', '')
        codigo_invitacion = request.form.get('codigo_invitacion', '').strip().upper()
        
        if not password or not telefono:
            flash('El teléfono y la contraseña son obligatorios.', 'danger')
            return redirect(url_for('completar_registro_google'))
            
        patrocinador = None
        if codigo_invitacion:
            patrocinador = Usuario.query.filter_by(codigo_referido=codigo_invitacion).first()

        hashed_password = generate_password_hash(password)
        temp_hash = os.urandom(3).hex().upper()
        
        nuevo_usuario = Usuario(
            nombre=datos_google['nombre'],
            correo=datos_google['correo'],
            telefono=telefono,
            password=hashed_password,
            google_id=datos_google['google_id'],
            correo_verificado=True,
            confirmado=True,
            rol='cliente',
            categoria='Cliente',
            rango='Bronce',
            referido_por_id=patrocinador.id if patrocinador else None,
            codigo_referido=f"WIND-TEMP-{temp_hash}"
        )
        
        db.session.add(nuevo_usuario)
        db.session.commit()
        nuevo_usuario.codigo_referido = f"WIND-{nuevo_usuario.id}-{os.urandom(2).hex().upper()}"
        
        if patrocinador:
            nuevo_registro = RegistroReferido(patrocinador_id=patrocinador.id, referido_id=nuevo_usuario.id)
            db.session.add(nuevo_registro)
            
        db.session.commit()
        
        session.pop('google_temp', None)
        session['usuario_id'] = nuevo_usuario.id
        session['nombre'] = nuevo_usuario.nombre
        session['correo'] = nuevo_usuario.correo
        session['rol'] = nuevo_usuario.rol
        
        flash('¡Cuenta creada y verificada con éxito mediante Google!', 'success')
        return redirect(url_for('cliente_home'))
        
    return render_template('completar_registro_google.html', correo=datos_google['correo'], nombre=datos_google['nombre'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip().lower()
        password = request.form.get('password', '')
        
        usuario = Usuario.query.filter_by(correo=correo).first()
        
        if usuario and usuario.password and check_password_hash(usuario.password, password):
            if not usuario.correo_verificado:
                flash('Debes verificar tu correo electrónico haciendo clic en el enlace que te enviamos antes de iniciar sesión.', 'warning')
                return redirect(url_for('login'))
            
            session['usuario_id'] = usuario.id
            session['nombre'] = usuario.nombre
            session['correo'] = usuario.correo
            session['rol'] = usuario.rol
            
            usuario.ultima_actividad = datetime.now(TIMEZONE_LIMA).replace(tzinfo=None)
            db.session.commit()
            
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
        codigo_invitacion = request.form.get('codigo_invitacion', '').strip().upper()
        
        if not nombre or not correo or not password:
            flash('Todos los campos obligatorios son requeridos.', 'danger')
            return redirect(url_for('register'))

        if Usuario.query.filter_by(correo=correo).first():
            flash('El correo ya está registrado.', 'danger')
            return redirect(url_for('register'))
            
        patrocinador = None
        if codigo_invitacion:
            patrocinador = Usuario.query.filter_by(codigo_referido=codigo_invitacion).first()

        hashed_password = generate_password_hash(password)
        temp_hash = os.urandom(3).hex().upper()
        
        nuevo_usuario = Usuario(
            nombre=nombre,
            correo=correo,
            telefono=telefono,
            password=hashed_password,
            rol='cliente',
            correo_verificado=False, # Bloqueado hasta que verifique
            confirmado=True,
            categoria='Cliente',
            rango='Bronce',
            referido_por_id=patrocinador.id if patrocinador else None,
            codigo_referido=f"WIND-TEMP-{temp_hash}"
        )
        
        db.session.add(nuevo_usuario)
        db.session.commit()
        nuevo_usuario.codigo_referido = f"WIND-{nuevo_usuario.id}-{os.urandom(2).hex().upper()}"
        
        if patrocinador:
            nuevo_registro = RegistroReferido(patrocinador_id=patrocinador.id, referido_id=nuevo_usuario.id)
            db.session.add(nuevo_registro)
            
        db.session.commit()
        
        # Enviar correo real de verificación con reporte de error detallado en consola
        try:
            token = serializer.dumps(correo, salt='email-verification-salt')
            enlace_verificacion = url_for('verificar_correo', token=token, _external=True)
            
            msg = Message('Verifica tu cuenta en WINDNEXX Store', recipients=[correo])
            msg.body = f"Hola {nombre},\n\nGracias por registrarte en WINDNEXX Store. Haz clic en el siguiente enlace para verificar tu correo y activar tu cuenta:\n\n{enlace_verificacion}\n\nSi no creaste esta cuenta, ignora este mensaje."
            mail.send(msg)
            flash('Registro exitoso. Hemos enviado un enlace de verificación a tu correo electrónico.', 'success')
        except Exception as e:
            print("ERROR SMTP AL ENVIAR CORREO:", str(e))
            flash(f'Registro exitoso, pero ocurrió un error al enviar el correo: {str(e)}', 'warning')
            
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/verificar-correo/<token>')
def verificar_correo(token):
    try:
        correo = serializer.loads(token, salt='email-verification-salt', max_age=86400)
    except Exception:
        flash('El enlace de verificación es inválido o ha expirado.', 'danger')
        return redirect(url_for('login'))
        
    usuario = Usuario.query.filter_by(correo=correo).first()
    if usuario:
        usuario.correo_verificado = True
        db.session.commit()
        flash('¡Correo verificado y cuenta activada con éxito! Ya puedes iniciar sesión.', 'success')
    else:
        flash('Usuario no encontrado.', 'danger')
        
    return redirect(url_for('login'))

@app.route('/soporte/enviar', methods=['POST'])
def enviar_soporte():
    nombre = request.form.get('nombre', '').strip()
    correo = request.form.get('correo', '').strip()
    telefono = request.form.get('telefono', '').strip()
    mensaje = request.form.get('mensaje', '').strip()
    
    filename = None
    if 'imagen' in request.files:
        file = request.files['imagen']
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
    if nombre and correo and mensaje:
        nuevo_msj = MensajeSoporte(nombre=nombre, correo=correo, telefono=telefono, mensaje=mensaje, imagen=filename)
        db.session.add(nuevo_msj)
        db.session.commit()
        flash('¡Mensaje enviado con éxito a Atención al Cliente! Te responderemos pronto.', 'success')
    else:
        flash('Por favor completa los campos obligatorios para enviar el mensaje.', 'danger')
        
    if 'usuario_id' in session and session.get('rol') == 'cliente':
        return redirect(url_for('cliente_home', seccion='atencion_cliente'))
    return redirect(url_for('login'))

@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar_password():
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip().lower()
        telefono = request.form.get('telefono', '').strip()
        
        usuario = Usuario.query.filter_by(correo=correo, telefono=telefono).first()
        if usuario:
            usuario.solicitud_reset = True
            db.session.commit()
            flash('Solicitud enviada con éxito. El administrador revisará tus datos para restablecer tu contraseña.', 'success')
            return redirect(url_for('login'))
        else:
            flash('El correo y el número de teléfono no coinciden con ningún registro.', 'danger')
            return redirect(url_for('recuperar_password'))
            
    return render_template('recuperar.html')

@app.route('/admin')
def admin_panel():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        flash('Acceso restringido para administradores.', 'danger')
        return redirect(url_for('login'))
    return render_template('admin.html', seccion=request.args.get('seccion', 'pedidos_pendientes'))

@app.route('/cliente/home')
def cliente_home():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        flash('Por favor inicia sesión con una cuenta de cliente.', 'warning')
        return redirect(url_for('login'))
    return render_template('cliente_home.html', nombre=session.get('nombre'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)