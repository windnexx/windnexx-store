import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'clave_secreta_windnexx_desarrollo'

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
    password = db.Column(db.String(200), nullable=False)
    rol = db.Column(db.String(20), default='cliente')
    confirmado = db.Column(db.Boolean, default=False)
    categoria = db.Column(db.String(20), default='Cliente')
    solicitud_reset = db.Column(db.Boolean, default=False)
    ultima_actividad = db.Column(db.DateTime, nullable=True)
    codigo_referido = db.Column(db.String(20), unique=True, nullable=True)
    referido_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    rango = db.Column(db.String(20), default='Bronce')

# Modelo de Código Promocional
class CodigoPromo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    descuento_porcentaje = db.Column(db.Float, nullable=False)
    tipo_limite = db.Column(db.String(20), default='ilimitado')
    max_usos_primeras = db.Column(db.Integer, default=0) 
    usos_actuales = db.Column(db.Integer, default=0)
    es_premio_referido = db.Column(db.Boolean, default=False)
    propietario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)

# Tabla de Configuración Global de Premios de Referidos
class ConfiguracionReferido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_premio = db.Column(db.String(100), default='Descuento por Referido')
    descuento_porcentaje = db.Column(db.Float, default=6.0)

# Tabla auxiliar para control de códigos
class UsoCodigoUsuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    codigo_id = db.Column(db.Integer, db.ForeignKey('codigo_promo.id'), nullable=False)

# Modelo de Registro de Referidos
class RegistroReferido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patrocinador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    referido_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    meta_cumplida = db.Column(db.Boolean, default=False)
    fecha = db.Column(db.String(30), default=lambda: hora_lima().strftime('%d/%m/%Y %H:%M'))

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
    codigo_promo = db.Column(db.String(50), nullable=True, default='')
    descuento_aplicado = db.Column(db.Float, nullable=True, default=0.0)
    estado = db.Column(db.String(50), default='Validación de pago') 
    fecha = db.Column(db.String(30), default=lambda: hora_lima().strftime('%d/%m/%Y %H:%M'))
    solo_fecha = db.Column(db.String(20), default=lambda: hora_lima().strftime('%d/%m/%Y'))

# Modelo para Mensajes de Soporte / Chat
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
        with db.engine.connect() as connection:
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS telefono VARCHAR(20);'))
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS confirmado BOOLEAN DEFAULT FALSE;'))
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS categoria VARCHAR(20) DEFAULT \'Cliente\';'))
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS solicitud_reset BOOLEAN DEFAULT FALSE;'))
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS ultima_actividad TIMESTAMP;'))
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS codigo_referido VARCHAR(20);'))
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS referido_por_id INTEGER;'))
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS rango VARCHAR(20) DEFAULT \'Bronce\';'))
            connection.execute(text('ALTER TABLE pedido ADD COLUMN IF NOT EXISTS codigo_promo VARCHAR(50);'))
            connection.execute(text('ALTER TABLE pedido ADD COLUMN IF NOT EXISTS descuento_aplicado FLOAT DEFAULT 0.0;'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS tipo_limite VARCHAR(20) DEFAULT \'ilimitado\';'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS max_usos_primeras INTEGER DEFAULT 0;'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS usos_actuales INTEGER DEFAULT 0;'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS es_premio_referido BOOLEAN DEFAULT FALSE;'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS propietario_id INTEGER;'))
            connection.commit()
    except Exception as e:
        print("Aviso al verificar columnas en la BD:", e)
    
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
            nombre='Administrador Windnexx',
            correo='windnexx@gmail.com',
            telefono='999999999',
            password=generate_password_hash('2244Nexxxx'),
            rol='admin',
            confirmado=True,
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

@app.route('/api/estado-usuarios')
def api_estado_usuarios():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return jsonify({}), 403
    
    usuarios = Usuario.query.filter_by(confirmado=True, rol='cliente').all()
    limite_online = datetime.now(TIMEZONE_LIMA).replace(tzinfo=None) - timedelta(minutes=3)
    
    resultado = {}
    for u in usuarios:
        en_linea = bool(u.ultima_actividad and u.ultima_actividad >= limite_online)
        resultado[u.id] = en_linea
        
    return jsonify(resultado)

PRECIOS = {
    'Fragmentos': 0.082,
    'Cajas': 0.45,
    'Pases': 3.00
}

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip().lower()
        password = request.form.get('password', '')
        usuario = Usuario.query.filter_by(correo=correo).first()
        
        if usuario and check_password_hash(usuario.password, password):
            if not usuario.confirmado:
                flash('Tu cuenta aún no ha sido aprobada por el administrador.', 'warning')
                return redirect(url_for('login'))
            
            session['usuario_id'] = usuario.id
            session['nombre'] = usuario.nombre
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
            nombre=nombre, correo=correo, telefono=telefono, password=hashed_password,
            rol='cliente', confirmado=False, categoria='Cliente', rango='Bronce',
            referido_por_id=patrocinador.id if patrocinador else None,
            codigo_referido=f"WIND-TEMP-{temp_hash}"
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        nuevo_usuario.codigo_referido = f"WIND-{nuevo_usuario.id}-{os.urandom(2).hex().upper()}"
        if patrocinador:
            db.session.add(RegistroReferido(patrocinador_id=patrocinador.id, referido_id=nuevo_usuario.id))
        db.session.commit()
        
        flash('Registro exitoso. Un administrador debe aprobar tu cuenta antes de iniciar sesión.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

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
            flash('Solicitud enviada con éxito.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Datos incorrectos.', 'danger')
            return redirect(url_for('recuperar_password'))
    return render_template('recuperar.html')

@app.route('/admin')
def admin_panel():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        flash('Acceso restringido.', 'danger')
        return redirect(url_for('login'))
        
    seccion_admin = request.args.get('seccion', 'pedidos_pendientes')
    
    usuarios_pendientes = Usuario.query.filter_by(confirmado=False, solicitud_reset=False).all()
    usuarios_confirmados = Usuario.query.filter_by(confirmado=True, rol='cliente').all()
    solicitudes_reset = Usuario.query.filter_by(solicitud_reset=True).all()
    codigos_promo = CodigoPromo.query.all()
    registros_referidos = RegistroReferido.query.all()
    config_referido = ConfiguracionReferido.query.first()
    mensajes_soporte = MensajeSoporte.query.order_by(MensajeSoporte.id.desc()).all()
    
    limite_online = datetime.now(TIMEZONE_LIMA).replace(tzinfo=None) - timedelta(minutes=3)
    for u in usuarios_confirmados:
        u.en_linea = bool(u.ultima_actividad and u.ultima_actividad >= limite_online)
    
    pedidos_validacion = Pedido.query.filter_by(estado='Validación de pago').all()
    pedidos_recargando = Pedido.query.filter_by(estado='Recargando').all()
    hoy_str = hora_lima().strftime('%d/%m/%Y')
    historial_envios = Pedido.query.filter_by(estado='Completado').order_by(Pedido.id.desc()).all()
    pedidos_hoy = [p for p in historial_envios if getattr(p, 'solo_fecha', hoy_str) == hoy_str]
    
    return render_template(
        'admin.html', 
        pendientes=usuarios_pendientes, confirmados=usuarios_confirmados,
        solicitudes_reset=solicitudes_reset, codigos_promo=codigos_promo,
        registros_referidos=registros_referidos, config_referido=config_referido,
        mensajes_soporte=mensajes_soporte,
        pedidos_validacion=pedidos_validacion, pedidos_recargando=pedidos_recargando,
        historial_envios=historial_envios, pedidos_hoy=pedidos_hoy,
        seccion=seccion_admin, Usuario=Usuario
    )

@app.route('/admin/soporte/atendido/<int:id>')
def soporte_atendido(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    msj = MensajeSoporte.query.get_or_404(id)
    msj.estado = 'Atendido'
    db.session.commit()
    flash('Consulta marcada como atendida.', 'success')
    return redirect(url_for('admin_panel', seccion='soporte'))

@app.route('/admin/actualizar_config_referido', methods=['POST'])
def actualizar_config_referido():
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    try:
        config = ConfiguracionReferido.query.first() or ConfiguracionReferido()
        config.descuento_porcentaje = float(request.form.get('descuento_referido', 6.0))
        config.nombre_premio = request.form.get('nombre_premio', '').strip()
        db.session.add(config)
        db.session.commit()
        flash('Configuración actualizada.', 'success')
    except ValueError:
        flash('Valor inválido.', 'danger')
    return redirect(url_for('admin_panel', seccion='codigos_promo'))

@app.route('/admin/crear_codigo', methods=['POST'])
def crear_codigo():
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    codigo = request.form.get('codigo', '').strip().upper()
    try: descuento = float(request.form.get('descuento', 0))
    except ValueError: descuento = 0
    if codigo and descuento > 0 and not CodigoPromo.query.filter_by(codigo=codigo).first():
        db.session.add(CodigoPromo(codigo=codigo, descuento_porcentaje=descuento, tipo_limite=request.form.get('tipo_limite', 'ilimitado'), max_usos_primeras=int(request.form.get('max_usos_primeras', 0))))
        db.session.commit()
        flash('Código creado.', 'success')
    else:
        flash('Error al crear código.', 'danger')
    return redirect(url_for('admin_panel', seccion='codigos_promo'))

@app.route('/admin/eliminar_codigo/<int:id>')
def eliminar_codigo(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    db.session.delete(CodigoPromo.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for('admin_panel', seccion='codigos_promo'))

@app.route('/api/verificar-alertas')
def verificar_alertas():
    try:
        return jsonify({
            "total_pedidos": Pedido.query.count(),
            "total_usuarios": Usuario.query.count()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/confirmar/<int:id>')
def confirmar_usuario(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    u = Usuario.query.get_or_404(id)
    u.confirmado = True
    db.session.commit()
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/admin/restablecer_password/<int:id>', methods=['POST'])
def restablecer_password(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    u = Usuario.query.get_or_404(id)
    np = request.form.get('nueva_password', '').strip()
    if np:
        u.password = generate_password_hash(np)
        u.solicitud_reset = False
        db.session.commit()
        flash('Contraseña restablecida.', 'success')
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/admin/eliminar_solicitud_reset/<int:id>')
def eliminar_solicitud_reset(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    u = Usuario.query.get_or_404(id)
    u.solicitud_reset = False
    db.session.commit()
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/admin/actualizar_categoria/<int:id>', methods=['POST'])
def actualizar_categoria(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    u = Usuario.query.get_or_404(id)
    u.categoria = request.form.get('categoria')
    db.session.commit()
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/admin/pasar_recargando/<int:id>')
def pasar_recargando(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    p = Pedido.query.get_or_404(id)
    p.estado = 'Recargando'
    db.session.commit()
    return redirect(url_for('admin_panel', seccion='pedidos_recargando'))

@app.route('/admin/completar_recarga/<int:id>')
def completar_recarga(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    p = Pedido.query.get_or_404(id)
    p.estado = 'Completado'
    h = hora_lima()
    p.solo_fecha = h.strftime('%d/%m/%Y')
    p.fecha = h.strftime('%d/%m/%Y %H:%M')
    db.session.commit()
    return redirect(url_for('admin_panel', seccion='historial_envios'))

@app.route('/admin/eliminar_pedido/<int:id>')
def eliminar_pedido(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    db.session.delete(Pedido.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/vaciar_historial_hoy')
def vaciar_historial_hoy():
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    hoy = hora_lima().strftime('%d/%m/%Y')
    for p in Pedido.query.filter_by(estado='Completado', solo_fecha=hoy).all():
        p.solo_fecha = f"Archivado ({hoy})"
    db.session.commit()
    return redirect(url_for('admin_panel', seccion='historial_envios'))

@app.route('/admin/eliminar/<int:id>')
def eliminar_usuario(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin': return redirect(url_for('login'))
    u = Usuario.query.get_or_404(id)
    if u.rol == 'admin': return redirect(url_for('admin_panel', seccion='gestion_usuarios'))
    db.session.delete(u)
    db.session.commit()
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/cliente/home')
def cliente_home():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        flash('Inicia sesión.', 'warning')
        return redirect(url_for('login'))
    
    if 'carrito' not in session: session['carrito'] = []
    if 'codigo_aplicado' not in session: session['codigo_aplicado'] = None; session['descuento_porcentaje'] = 0.0
        
    seccion = request.args.get('seccion', 'catalogo')
    codigo_pat = request.args.get('codigo_patrocinador', '').strip().upper()
    usuario_actual = db.session.get(Usuario, session['usuario_id'])
    
    if codigo_pat and not usuario_actual.referido_por_id:
        pat = Usuario.query.filter_by(codigo_referido=codigo_pat).first()
        if pat and pat.id != usuario_actual.id:
            usuario_actual.referido_por_id = pat.id
            db.session.add(RegistroReferido(patrocinador_id=pat.id, referido_id=usuario_actual.id))
            db.session.commit()
            flash('¡Vinculado con éxito!', 'success')
        return redirect(url_for('cliente_home', seccion='amigo_referidos'))

    tp, tf, tc, puntos = calcular_estadisticas_usuario(usuario_actual.id)
    meta = 5000
    if puntos >= meta:
        usuario_actual.rango = 'Plata'; prog = 100
    else:
        usuario_actual.rango = 'Bronce'; prog = int((puntos / meta) * 100)
    db.session.commit()

    mis_ref = RegistroReferido.query.filter_by(patrocinador_id=usuario_actual.id).all()
    historial = Pedido.query.filter_by(usuario_id=session['usuario_id']).order_by(Pedido.id.desc()).all()
        
    tot = 0
    calc = []
    for item in session['carrito']:
        sub = item['cantidad'] * PRECIOS.get(item['producto'], 0)
        tot += sub
        calc.append({'producto': item['producto'], 'cantidad': item['cantidad'], 'precio_unitario': PRECIOS.get(item['producto'], 0), 'subtotal': round(sub, 2)})
        
    desc_monto = tot * (session.get('descuento_porcentaje', 0) / 100.0) if session.get('descuento_porcentaje', 0) > 0 else 0.0
    total_fin = max(0.0, tot - desc_monto)
        
    return render_template(
        'cliente_home.html', nombre=session.get('nombre'), usuario=usuario_actual,
        total_pases=tp, total_fragmentos=tf, total_cajas=tc,
        progreso_porcentaje=prog, puntos_fragmentos=puntos, meta_rango=meta,
        mis_referidos=mis_ref, Usuario=Usuario, CodigoPromo=CodigoPromo,
        carrito=calc, total_general=round(tot, 2), descuento_monto=round(desc_monto, 2),
        total_final=round(total_fin, 2), codigo_aplicado=session.get('codigo_aplicado'),
        seccion=seccion, historial=historial
    )

@app.route('/cliente/agregar', methods=['POST'])
def agregar_carrito():
    if 'usuario_id' not in session or session.get('rol') != 'cliente': return redirect(url_for('login'))
    prod = request.form.get('producto')
    try: cant = max(1, int(request.form.get('cantidad', 1)))
    except ValueError: cant = 1
    
    if 'carrito' not in session: session['carrito'] = []
    enc = False
    for i in session['carrito']:
        if i['producto'] == prod: i['cantidad'] += cant; enc = True; break
    if not enc: session['carrito'].append({'producto': prod, 'cantidad': cant})
    session.modified = True
    return redirect(url_for('cliente_home', seccion='catalogo'))

@app.route('/cliente/aplicar_codigo', methods=['POST'])
def aplicar_codigo():
    if 'usuario_id' not in session or session.get('rol') != 'cliente': return redirect(url_for('login'))
    cp = CodigoPromo.query.filter_by(codigo=request.form.get('codigo_promo', '').strip().upper()).first()
    if cp:
        session['codigo_aplicado'] = cp.codigo
        session['descuento_porcentaje'] = cp.descuento_porcentaje
        flash(f'¡Código {cp.codigo} aplicado!', 'success')
    else:
        flash('Código inválido.', 'danger')
    session.modified = True
    return redirect(url_for('cliente_home', seccion='catalogo'))

@app.route('/cliente/preparar_pago', methods=['POST'])
def preparar_pago():
    if 'usuario_id' not in session or session.get('rol') != 'cliente': return redirect(url_for('login'))
    jid = request.form.get('jugador_id', '').strip()
    if not jid:
        flash('Ingresa el ID.', 'danger')
        return redirect(url_for('cliente_home', seccion='catalogo'))
    session['jugador_id_temp'] = jid
    session.modified = True
    return redirect(url_for('cliente_home', seccion='pago_yape'))

@app.route('/cliente/pagar_yape', methods=['POST'])
def pagar_yape():
    if 'usuario_id' not in session or session.get('rol') != 'cliente': return redirect(url_for('login'))
    tot = sum(i['cantidad'] * PRECIOS.get(i['producto'], 0) for i in session.get('carrito', []))
    desc = tot * (session.get('descuento_porcentaje', 0.0) / 100.0)
    
    np = Pedido(
        usuario_id=session['usuario_id'], nombre_cliente=session['nombre'],
        jugador_id=session.get('jugador_id_temp'),
        detalle=", ".join([f"{i['producto']} (x{i['cantidad']})" for i in session['carrito']]),
        total=round(max(0.0, tot - desc), 2),
        telefono_digitos=request.form.get('telefono_digitos', ''),
        codigo_operacion=request.form.get('codigo_operacion', ''),
        codigo_promo=session.get('codigo_aplicado', ''), descuento_aplicado=round(desc, 2),
        estado='Validación de pago', solo_fecha=hora_lima().strftime('%d/%m/%Y'),
        fecha=hora_lima().strftime('%d/%m/%Y %H:%M')
    )
    db.session.add(np); db.session.commit()
    session['carrito'] = []; session.pop('jugador_id_temp', None); session.pop('codigo_aplicado', None); session.pop('descuento_porcentaje', None)
    session.modified = True
    flash('¡Pago registrado!', 'success')
    return redirect(url_for('cliente_home', seccion='historial'))

@app.route('/cliente/vaciar')
def vaciar_carrito():
    session['carrito'] = []; session.modified = True
    return redirect(url_for('cliente_home', seccion='catalogo'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)