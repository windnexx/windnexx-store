import os
import io
import re
import zipfile
from xml.sax.saxutils import escape as xml_escape
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import text, inspect

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
    saldo_fragmentos = db.Column(db.Integer, default=0)

# Modelo de Configuración de Precios y Estado de Productos
class ConfiguracionProductos(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    precio_fragmentos = db.Column(db.Float, default=0.082)
    precio_cajas = db.Column(db.Float, default=0.45)
    precio_pases = db.Column(db.Float, default=3.00)
    fragmentos_habilitado = db.Column(db.Boolean, default=True)
    cajas_habilitado = db.Column(db.Boolean, default=True)
    pases_habilitado = db.Column(db.Boolean, default=True)
    diamantes_habilitado = db.Column(db.Boolean, default=True)

# Modelo de Paquetes Específicos de Diamantes
class PaqueteDiamante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cantidad = db.Column(db.Integer, unique=True, nullable=False)
    precio = db.Column(db.Float, nullable=False)

# Modelo de Código Promocional
class CodigoPromo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    descuento_porcentaje = db.Column(db.Float, nullable=False)
    tipo_premio = db.Column(db.String(30), default='descuento')
    cantidad_premio = db.Column(db.Float, default=0.0)
    tipo_limite = db.Column(db.String(20), default='ilimitado')
    max_usos_primeras = db.Column(db.Integer, default=0) 
    usos_actuales = db.Column(db.Integer, default=0)
    es_premio_referido = db.Column(db.Boolean, default=False)
    propietario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)

# Tabla de Configuración Global de Premios de Referidos
class ConfiguracionReferido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_premio = db.Column(db.String(100), default='Bono por Amigo Referido')
    descuento_porcentaje = db.Column(db.Float, default=20.0)
    fragmentos_por_referido = db.Column(db.Integer, default=20)

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

# Modelo para Mensajes de Soporte / Atención al Cliente
class MensajeSoporte(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    imagen = db.Column(db.String(255), nullable=True)
    estado = db.Column(db.String(20), default='Pendiente')
    fecha = db.Column(db.String(30), default=lambda: hora_lima().strftime('%d/%m/%Y %H:%M'))

# Modelo para Mensaje de Publicidad / Anuncio en Cliente Home
class AnuncioPublicidad(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mensaje = db.Column(db.Text, nullable=False, default='')
    activo = db.Column(db.Boolean, default=False)
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
            connection.execute(text('ALTER TABLE usuario ADD COLUMN IF NOT EXISTS saldo_fragmentos INTEGER DEFAULT 0;'))
            connection.execute(text('ALTER TABLE configuracion_referido ADD COLUMN IF NOT EXISTS fragmentos_por_referido INTEGER DEFAULT 20;'))
            connection.execute(text('ALTER TABLE pedido ADD COLUMN IF NOT EXISTS codigo_promo VARCHAR(50);'))
            connection.execute(text('ALTER TABLE pedido ADD COLUMN IF NOT EXISTS descuento_aplicado FLOAT DEFAULT 0.0;'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS tipo_premio VARCHAR(30) DEFAULT \'descuento\';'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS cantidad_premio FLOAT DEFAULT 0.0;'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS tipo_limite VARCHAR(20) DEFAULT \'ilimitado\';'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS max_usos_primeras INTEGER DEFAULT 0;'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS usos_actuales INTEGER DEFAULT 0;'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS es_premio_referido BOOLEAN DEFAULT FALSE;'))
            connection.execute(text('ALTER TABLE codigo_promo ADD COLUMN IF NOT EXISTS propietario_id INTEGER;'))
            connection.execute(text('ALTER TABLE configuracion_productos ADD COLUMN IF NOT EXISTS precio_fragmentos FLOAT DEFAULT 0.082;'))
            connection.execute(text('ALTER TABLE configuracion_productos ADD COLUMN IF NOT EXISTS precio_cajas FLOAT DEFAULT 0.45;'))
            connection.execute(text('ALTER TABLE configuracion_productos ADD COLUMN IF NOT EXISTS precio_pases FLOAT DEFAULT 3.00;'))
            connection.execute(text('ALTER TABLE configuracion_productos ADD COLUMN IF NOT EXISTS fragmentos_habilitado BOOLEAN DEFAULT TRUE;'))
            connection.execute(text('ALTER TABLE configuracion_productos ADD COLUMN IF NOT EXISTS cajas_habilitado BOOLEAN DEFAULT TRUE;'))
            connection.execute(text('ALTER TABLE configuracion_productos ADD COLUMN IF NOT EXISTS pases_habilitado BOOLEAN DEFAULT TRUE;'))
            connection.execute(text('ALTER TABLE configuracion_productos ADD COLUMN IF NOT EXISTS diamantes_habilitado BOOLEAN DEFAULT TRUE;'))
            connection.execute(text('ALTER TABLE paquete_diamante ADD COLUMN IF NOT EXISTS cantidad INTEGER;'))
            connection.execute(text('ALTER TABLE paquete_diamante ADD COLUMN IF NOT EXISTS precio FLOAT DEFAULT 0.0;'))
            connection.commit()
    except Exception as e:
        print("Aviso al verificar columnas en la BD:", e)

    try:
        inspector = inspect(db.engine)
        if 'paquete_diamante' in inspector.get_table_names():
            columnas_paq = [col['name'] for col in inspector.get_columns('paquete_diamante')]
            with db.engine.connect() as connection:
                for col_name in columnas_paq:
                    if col_name not in ('id', 'cantidad', 'precio'):
                        connection.execute(text(f'ALTER TABLE paquete_diamante ALTER COLUMN "{col_name}" DROP NOT NULL;'))
                connection.commit()
    except Exception as e:
        print("Aviso al liberar columnas antiguas de paquete_diamante:", e)
    
    if not ConfiguracionProductos.query.first():
        conf_prod = ConfiguracionProductos(
            precio_fragmentos=0.082,
            precio_cajas=0.45,
            precio_pases=3.00,
            fragmentos_habilitado=True,
            cajas_habilitado=True,
            pases_habilitado=True,
            diamantes_habilitado=True
        )
        db.session.add(conf_prod)
        db.session.commit()

    if PaqueteDiamante.query.count() == 0:
        paquetes_default = [
            PaqueteDiamante(cantidad=100, precio=3.50),
            PaqueteDiamante(cantidad=310, precio=10.50),
            PaqueteDiamante(cantidad=520, precio=17.50),
            PaqueteDiamante(cantidad=1060, precio=35.00),
            PaqueteDiamante(cantidad=2180, precio=70.00),
            PaqueteDiamante(cantidad=5600, precio=175.00),
        ]
        db.session.add_all(paquetes_default)
        db.session.commit()

    if not ConfiguracionReferido.query.first():
        conf_inicial = ConfiguracionReferido(
            nombre_premio='Bono por Amigo Referido',
            descuento_porcentaje=20.0,
            fragmentos_por_referido=20
        )
        db.session.add(conf_inicial)
        db.session.commit()

    for u in Usuario.query.filter_by(codigo_referido=None).all():
        u.codigo_referido = f"WIND-{u.id}-{os.urandom(2).hex().upper()}"
    db.session.commit()

    admin_1 = Usuario.query.filter_by(correo='windnexx@gmail.com').first()
    if not admin_1:
        nuevo_admin_1 = Usuario(
            nombre='Nomar',
            correo='windnexx@gmail.com',
            telefono='999999999',
            password=generate_password_hash('2244Nexxxx'),
            rol='admin',
            confirmado=True,
            categoria='Supercliente',
            codigo_referido='WIND-ADMIN-1'
        )
        db.session.add(nuevo_admin_1)
    else:
        admin_1.nombre = 'Nomar'

    admin_2 = Usuario.query.filter_by(correo='croldan12345@gmail.com').first()
    if not admin_2:
        nuevo_admin_2 = Usuario(
            nombre='Carlos',
            correo='croldan12345@gmail.com',
            telefono='999999999',
            password=generate_password_hash('masterkeyne9999'),
            rol='admin',
            confirmado=True,
            categoria='Supercliente',
            codigo_referido='WIND-ADMIN-2'
        )
        db.session.add(nuevo_admin_2)
    else:
        admin_2.nombre = 'Carlos'
        
    db.session.commit()

def obtener_config_productos():
    conf = ConfiguracionProductos.query.first()
    if not conf:
        conf = ConfiguracionProductos(
            precio_fragmentos=0.082,
            precio_cajas=0.45,
            precio_pases=3.00,
            fragmentos_habilitado=True,
            cajas_habilitado=True,
            pases_habilitado=True,
            diamantes_habilitado=True
        )
        db.session.add(conf)
        db.session.commit()
    return conf

def obtener_precios_dict():
    conf = obtener_config_productos()
    return {
        'Fragmentos': float(conf.precio_fragmentos or 0.082),
        'Cajas': float(conf.precio_cajas or 0.45),
        'Pases': float(conf.precio_pases or 3.00)
    }

def obtener_paquete_diamante_mas_cercano(cantidad_ingresada):
    paquetes = PaqueteDiamante.query.order_by(PaqueteDiamante.cantidad.asc()).all()
    if not paquetes:
        return None
    for p in paquetes:
        if p.cantidad == cantidad_ingresada:
            return p
    mejor_paquete = min(
        paquetes,
        key=lambda p: (abs(p.cantidad - cantidad_ingresada), -p.cantidad)
    )
    return mejor_paquete

def calcular_subtotal_item(producto, cantidad):
    if producto == 'Diamantes':
        paq = PaqueteDiamante.query.filter_by(cantidad=cantidad).first()
        if paq:
            return float(paq.precio), round(float(paq.precio) / float(paq.cantidad), 4)
        paq_cercano = obtener_paquete_diamante_mas_cercano(cantidad)
        if paq_cercano:
            return float(paq_cercano.precio), round(float(paq_cercano.precio) / float(paq_cercano.cantidad), 4)
        return 0.0, 0.0
    precios = obtener_precios_dict()
    precio_unit = precios.get(producto, 0.0)
    return round(cantidad * precio_unit, 2), precio_unit

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
        ultima_formateada = u.ultima_actividad.strftime('%d/%m/%Y %H:%M') if u.ultima_actividad else 'Nunca'
        timestamp_val = u.ultima_actividad.timestamp() if u.ultima_actividad else 0
        resultado[u.id] = {
            "en_linea": en_linea,
            "ultima_actividad": ultima_formateada,
            "timestamp": timestamp_val
        }
        
    return jsonify(resultado)

@app.route('/api/cliente/verificar-estado')
def api_cliente_verificar_estado():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        return jsonify({}), 403
    
    ultimo_pedido = Pedido.query.filter_by(usuario_id=session['usuario_id']).order_by(Pedido.id.desc()).first()
    if ultimo_pedido:
        return jsonify({"estado_actual": ultimo_pedido.estado})
    return jsonify({"estado_actual": None})

def calcular_estadisticas_usuario(usuario_id):
    pedidos_completados = Pedido.query.filter_by(usuario_id=usuario_id, estado='Completado').all()
    precios = obtener_precios_dict()
    total_pases = 0
    total_fragmentos = 0
    total_cajas = 0
    monto_total_comprado = 0.0

    for p in pedidos_completados:
        if p.total <= 0 and p.telefono_digitos == 'REF':
            continue

        m_frag = re.search(r'Fragmentos \(x(\d+)\)', p.detalle)
        if m_frag:
            total_fragmentos += int(m_frag.group(1))

        m_cajas = re.search(r'Cajas \(x(\d+)\)', p.detalle)
        if m_cajas:
            total_cajas += int(m_cajas.group(1))

        m_pases = re.search(r'Pases \(x(\d+)\)', p.detalle)
        if m_pases:
            total_pases += int(m_pases.group(1))

        monto_total_comprado += (p.total + (p.descuento_aplicado or 0.0))

    precio_frag = precios.get('Fragmentos', 0.082) or 0.082
    fragmentos_equivalentes = int(round(monto_total_comprado / precio_frag))
    return total_pases, total_fragmentos, total_cajas, fragmentos_equivalentes

def otorgar_bono_referido_si_aplica(cliente_id):
    cliente = db.session.get(Usuario, cliente_id)
    if not cliente or not cliente.referido_por_id:
        return

    tiene_compra_tienda = Pedido.query.filter(
        Pedido.usuario_id == cliente.id,
        Pedido.estado == 'Completado',
        Pedido.telefono_digitos != 'REF'
    ).first()

    if not tiene_compra_tienda:
        return

    reg_ref = RegistroReferido.query.filter_by(
        patrocinador_id=cliente.referido_por_id,
        referido_id=cliente.id
    ).first()

    if reg_ref and not reg_ref.meta_cumplida:
        reg_ref.meta_cumplida = True
        patrocinador = db.session.get(Usuario, cliente.referido_por_id)
        if patrocinador:
            config_ref = ConfiguracionReferido.query.first()
            premio_frag = config_ref.fragmentos_por_referido if (config_ref and config_ref.fragmentos_por_referido) else 20
            patrocinador.saldo_fragmentos = (patrocinador.saldo_fragmentos or 0) + premio_frag
        db.session.commit()

def generar_xlsx_memoria(filas_datos):
    columnas_letras = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
    xml_filas = []

    for r_idx, fila in enumerate(filas_datos, start=1):
        celdas = []
        for c_idx, valor in enumerate(fila):
            ref = f"{columnas_letras[c_idx]}{r_idx}"
            if isinstance(valor, (int, float)):
                celdas.append(f'<c r="{ref}"><v>{valor}</v></c>')
            else:
                texto_seguro = xml_escape(str(valor if valor is not None else ''))
                celdas.append(f'<c r="{ref}" t="inlineStr"><is><t>{texto_seguro}</t></is></c>')
        xml_filas.append(f'<row r="{r_idx}">{"".join(celdas)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cols>'
        '<col min="1" max="1" width="12" customWidth="1"/>'
        '<col min="2" max="2" width="20" customWidth="1"/>'
        '<col min="3" max="3" width="26" customWidth="1"/>'
        '<col min="4" max="4" width="20" customWidth="1"/>'
        '<col min="5" max="5" width="38" customWidth="1"/>'
        '<col min="6" max="6" width="18" customWidth="1"/>'
        '<col min="7" max="7" width="16" customWidth="1"/>'
        '</cols>'
        f'<sheetData>{"".join(xml_filas)}</sheetData>'
        '</worksheet>'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )

    rels_root = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Historial Ventas" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', rels_root)
        zf.writestr('xl/workbook.xml', workbook_xml)
        zf.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        zf.writestr('xl/worksheets/sheet1.xml', sheet_xml)
    buffer.seek(0)
    return buffer

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
            session['correo'] = usuario.correo
            
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
        
        if not telefono or not telefono.isdigit() or len(telefono) != 9:
            flash('El número de teléfono es obligatorio y debe contener exactamente 9 dígitos numéricos.', 'danger')
            return redirect(url_for('register'))

        if not nombre or not correo or not password:
            flash('Todos los campos obligatorios son requeridos.', 'danger')
            return redirect(url_for('register'))

        if Usuario.query.filter_by(correo=correo).first():
            flash('El correo ya está registrado.', 'danger')
            return redirect(url_for('register'))
            
        patrocinador = None
        if codigo_invitacion:
            patrocinador = Usuario.query.filter_by(codigo_referido=codigo_invitacion).first()
            if not patrocinador:
                flash('El código de referido ingresado no es válido.', 'warning')

        hashed_password = generate_password_hash(password)
        
        temp_hash = os.urandom(3).hex().upper()
        nuevo_usuario = Usuario(
            nombre=nombre,
            correo=correo,
            telefono=telefono,
            password=hashed_password,
            rol='cliente',
            confirmado=False,
            categoria='Cliente',
            rango='Bronce',
            saldo_fragmentos=0,
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
        
    seccion_admin = request.args.get('seccion', 'pedidos_pendientes')
    
    usuarios_pendientes = Usuario.query.filter_by(confirmado=False, solicitud_reset=False).all()
    usuarios_confirmados = Usuario.query.filter_by(confirmado=True, rol='cliente').all()
    
    limite_online = datetime.now(TIMEZONE_LIMA).replace(tzinfo=None) - timedelta(minutes=3)
    for u in usuarios_confirmados:
        u.en_linea = bool(u.ultima_actividad and u.ultima_actividad >= limite_online)
    
    usuarios_confirmados.sort(key=lambda x: (x.ultima_actividad if x.ultima_actividad else datetime.min), reverse=True)

    solicitudes_reset = Usuario.query.filter_by(solicitud_reset=True).all()
    codigos_promo = CodigoPromo.query.all()
    registros_referidos = RegistroReferido.query.order_by(RegistroReferido.id.desc()).all()
    config_referido = ConfiguracionReferido.query.first()
    config_productos = obtener_config_productos()
    paquetes_diamantes = PaqueteDiamante.query.order_by(PaqueteDiamante.cantidad.asc()).all()
    mensajes_soporte = MensajeSoporte.query.order_by(MensajeSoporte.id.desc()).all()
    publicidad = AnuncioPublicidad.query.first()
    
    pedidos_validacion = Pedido.query.filter_by(estado='Validación de pago').all()
    pedidos_recargando = Pedido.query.filter_by(estado='Recargando').all()
    
    hoy_str = hora_lima().strftime('%d/%m/%Y')
    historial_envios = Pedido.query.filter_by(estado='Completado').order_by(Pedido.id.desc()).all()
    
    pedidos_hoy = [p for p in historial_envios if getattr(p, 'solo_fecha', hoy_str) == hoy_str]
    
    historicos_agrupados = {}
    for p in historial_envios:
        fecha_item = getattr(p, 'solo_fecha', hoy_str)
        if fecha_item != hoy_str:
            if fecha_item not in historicos_agrupados:
                historicos_agrupados[fecha_item] = []
            historicos_agrupados[fecha_item].append(p)
    
    return render_template(
        'admin.html', 
        pendientes=usuarios_pendientes, 
        confirmados=usuarios_confirmados,
        solicitudes_reset=solicitudes_reset,
        codigos_promo=codigos_promo,
        registros_referidos=registros_referidos,
        config_referido=config_referido,
        config_productos=config_productos,
        paquetes_diamantes=paquetes_diamantes,
        mensajes_soporte=mensajes_soporte,
        publicidad=publicidad,
        admin_correo=session.get('correo', ''),
        pedidos_validacion=pedidos_validacion,
        pedidos_recargando=pedidos_recargando,
        historial_envios=historial_envios,
        pedidos_hoy=pedidos_hoy,
        historicos_agrupados=historicos_agrupados,
        seccion=seccion_admin,
        Usuario=Usuario
    )

@app.route('/admin/guardar_precios_productos', methods=['POST'])
def guardar_precios_productos():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conf = obtener_config_productos()
    try:
        p_frag = float(request.form.get('precio_fragmentos', conf.precio_fragmentos))
        p_cajas = float(request.form.get('precio_cajas', conf.precio_cajas))
        p_pases = float(request.form.get('precio_pases', conf.precio_pases))
        frag_hab = request.form.get('fragmentos_habilitado') == 'on'
        cajas_hab = request.form.get('cajas_habilitado') == 'on'
        pases_hab = request.form.get('pases_habilitado') == 'on'
        diam_hab = request.form.get('diamantes_habilitado') == 'on'

        if p_frag > 0:
            conf.precio_fragmentos = p_frag
        if p_cajas > 0:
            conf.precio_cajas = p_cajas
        if p_pases > 0:
            conf.precio_pases = p_pases
        conf.fragmentos_habilitado = frag_hab
        conf.cajas_habilitado = cajas_hab
        conf.pases_habilitado = pases_hab
        conf.diamantes_habilitado = diam_hab

        db.session.commit()
        flash('Precios y estado de stock actualizados correctamente.', 'success')
    except ValueError:
        flash('Por favor ingresa montos numéricos válidos.', 'danger')

    return redirect(url_for('admin_panel', seccion='productos_precios'))

@app.route('/admin/agregar_paquete_diamante', methods=['POST'])
def agregar_paquete_diamante():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    try:
        cantidad = int(request.form.get('cantidad_diamantes', 0))
        precio = float(request.form.get('precio_diamantes', 0))
        if cantidad <= 0 or precio <= 0:
            flash('La cantidad y el precio deben ser mayores a cero.', 'danger')
            return redirect(url_for('admin_panel', seccion='productos_precios'))

        existente = PaqueteDiamante.query.filter_by(cantidad=cantidad).first()
        if existente:
            existente.precio = round(precio, 2)
            flash(f'Precio del paquete de {cantidad} diamantes actualizado a S/ {precio:.2f}.', 'success')
        else:
            nuevo_paq = PaqueteDiamante(cantidad=cantidad, precio=round(precio, 2))
            db.session.add(nuevo_paq)
            flash(f'Paquete de {cantidad} diamantes (S/ {precio:.2f}) agregado.', 'success')

        db.session.commit()
    except ValueError:
        flash('Valores inválidos para el paquete de diamantes.', 'danger')

    return redirect(url_for('admin_panel', seccion='productos_precios'))

@app.route('/admin/eliminar_paquete_diamante/<int:id>')
def eliminar_paquete_diamante(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    paq = PaqueteDiamante.query.get_or_404(id)
    db.session.delete(paq)
    db.session.commit()
    flash(f'Paquete de {paq.cantidad} diamantes eliminado.', 'info')
    return redirect(url_for('admin_panel', seccion='productos_precios'))

@app.route('/admin/guardar_publicidad', methods=['POST'])
def guardar_publicidad():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    accion = request.form.get('accion', 'guardar')
    mensaje_pub = request.form.get('mensaje_publicidad', '').strip()

    anuncio = AnuncioPublicidad.query.first()
    if not anuncio:
        anuncio = AnuncioPublicidad()
        db.session.add(anuncio)

    if accion == 'quitar' or not mensaje_pub:
        anuncio.mensaje = ''
        anuncio.activo = False
        anuncio.fecha = hora_lima().strftime('%d/%m/%Y %H:%M')
        db.session.commit()
        flash('El anuncio de publicidad ha sido quitado.', 'info')
    else:
        anuncio.mensaje = mensaje_pub
        anuncio.activo = True
        anuncio.fecha = hora_lima().strftime('%d/%m/%Y %H:%M')
        db.session.commit()
        flash('¡Mensaje de publicidad guardado y publicado para los clientes!', 'success')

    return redirect(url_for('admin_panel', seccion='soporte'))

@app.route('/admin/descargar_excel')
def descargar_historial_excel():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    fecha_solicitada = request.args.get('fecha', '')
    pedidos_fecha = Pedido.query.filter_by(estado='Completado', solo_fecha=fecha_solicitada).order_by(Pedido.id.asc()).all()

    filas = [
        ["ID Pedido", "Fecha y Hora", "Cliente", "ID Destino", "Detalle de Productos", "Cupón", "Total (S/)"]
    ]
    total_dia = 0.0
    for p in pedidos_fecha:
        filas.append([
            p.id,
            p.fecha,
            p.nombre_cliente,
            p.jugador_id,
            p.detalle,
            p.codigo_promo if p.codigo_promo else "-",
            round(float(p.total), 2)
        ])
        total_dia += float(p.total)

    filas.append(["", "", "", "", "", "TOTAL DEL DÍA:", round(total_dia, 2)])

    archivo_xlsx = generar_xlsx_memoria(filas)
    nombre_descarga = f"Ventas_WindNexx_{fecha_solicitada.replace('/', '-')}.xlsx"

    return send_file(
        archivo_xlsx,
        as_attachment=True,
        download_name=nombre_descarga,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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

@app.route('/admin/soporte/eliminar/<int:id>')
def eliminar_soporte(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    msj = MensajeSoporte.query.get_or_404(id)
    if msj.imagen:
        ruta_img = os.path.join(app.config['UPLOAD_FOLDER'], msj.imagen)
        if os.path.exists(ruta_img):
            try:
                os.remove(ruta_img)
            except OSError:
                pass
    db.session.delete(msj)
    db.session.commit()
    flash('Mensaje de soporte eliminado.', 'info')
    return redirect(url_for('admin_panel', seccion='soporte'))

@app.route('/admin/actualizar_config_referido', methods=['POST'])
def actualizar_config_referido():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    
    try:
        nuevos_fragmentos = int(request.form.get('fragmentos_referido', 20))
        if nuevos_fragmentos < 1:
            nuevos_fragmentos = 20
        nombre_premio = request.form.get('nombre_premio', 'Bono por Amigo Referido').strip()
        
        config = ConfiguracionReferido.query.first()
        if not config:
            config = ConfiguracionReferido()
            db.session.add(config)
            
        config.fragmentos_por_referido = nuevos_fragmentos
        config.descuento_porcentaje = float(nuevos_fragmentos)
        config.nombre_premio = nombre_premio
        db.session.commit()
        flash(f'Premio de referidos actualizado a {nuevos_fragmentos} fragmentos por amigo.', 'success')
    except ValueError:
        flash('Cantidad de fragmentos inválida.', 'danger')
        
    return redirect(url_for('admin_panel', seccion='codigos_promo'))

@app.route('/admin/crear_codigo', methods=['POST'])
def crear_codigo():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    
    codigo = request.form.get('codigo', '').strip().upper()
    tipo_premio = request.form.get('tipo_premio', 'descuento').strip()
    try:
        valor_raw = request.form.get('cantidad_premio') or request.form.get('descuento') or 0
        cantidad_premio = float(valor_raw)
    except ValueError:
        cantidad_premio = 0
        
    tipo_limite = request.form.get('tipo_limite', 'ilimitado')
    try:
        max_usos_primeras = int(request.form.get('max_usos_primeras', 0))
    except ValueError:
        max_usos_primeras = 0
    
    if codigo and cantidad_premio > 0:
        if not CodigoPromo.query.filter_by(codigo=codigo).first():
            descuento_val = cantidad_premio if tipo_premio == 'descuento' else 0.0
            nuevo_cp = CodigoPromo(
                codigo=codigo, 
                descuento_porcentaje=descuento_val,
                tipo_premio=tipo_premio,
                cantidad_premio=cantidad_premio,
                tipo_limite=tipo_limite,
                max_usos_primeras=max_usos_primeras,
                usos_actuales=0,
                es_premio_referido=False
            )
            db.session.add(nuevo_cp)
            db.session.commit()
            flash(f'Código promocional {codigo} creado con éxito.', 'success')
        else:
            flash('El código ya existe.', 'danger')
    else:
        flash('Datos inválidos para el código promocional.', 'danger')
    return redirect(url_for('admin_panel', seccion='codigos_promo'))

@app.route('/admin/eliminar_codigo/<int:id>')
def eliminar_codigo(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
        
    cp = CodigoPromo.query.get_or_404(id)
    try:
        UsoCodigoUsuario.query.filter_by(codigo_id=cp.id).delete()
        db.session.delete(cp)
        db.session.commit()
        flash('Código promocional eliminado correctamente.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'No se pudo eliminar el código promocional: {str(e)}', 'danger')
        
    return redirect(url_for('admin_panel', seccion='codigos_promo'))

@app.route('/api/verificar-alertas')
def verificar_alertas():
    try:
        total_pedidos = Pedido.query.count()
        total_usuarios = Usuario.query.count()
        ultimo_pedido = Pedido.query.order_by(Pedido.id.desc()).first()
        ultimo_usuario = Usuario.query.order_by(Usuario.id.desc()).first()
        
        return jsonify({
            "total_pedidos": total_pedidos,
            "total_usuarios": total_usuarios,
            "ultimo_pedido_id": ultimo_pedido.id if ultimo_pedido else 0,
            "ultimo_usuario_id": ultimo_usuario.id if ultimo_usuario else 0
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/confirmar/<int:id>')
def confirmar_usuario(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
        
    usuario = Usuario.query.get_or_404(id)
    usuario.confirmado = True
    db.session.commit()
    flash(f'El usuario {usuario.nombre} ha sido confirmado exitosamente.', 'success')
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/admin/restablecer_password/<int:id>', methods=['POST'])
def restablecer_password(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
        
    usuario = Usuario.query.get_or_404(id)
    nueva_pass = request.form.get('nueva_password', '').strip()
    
    if nueva_pass:
        usuario.password = generate_password_hash(nueva_pass)
        usuario.solicitud_reset = False
        db.session.commit()
        flash(f'Contraseña restablecida correctamente para {usuario.correo}.', 'success')
    else:
        flash('Debes ingresar una contraseña válida.', 'danger')
        
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/admin/eliminar_solicitud_reset/<int:id>')
def eliminar_solicitud_reset(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    usuario = Usuario.query.get_or_404(id)
    usuario.solicitud_reset = False
    db.session.commit()
    flash('Solicitud de restablecimiento eliminada.', 'info')
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/admin/actualizar_categoria/<int:id>', methods=['POST'])
def actualizar_categoria(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
        
    usuario = Usuario.query.get_or_404(id)
    nueva_categoria = request.form.get('categoria')
    
    if nueva_categoria in ['Supercliente', 'Cliente', 'Otros']:
        usuario.categoria = nueva_categoria
        db.session.commit()
        flash(f'Categoría de {usuario.nombre} actualizada a {nueva_categoria}.', 'success')
        
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/admin/pasar_recargando/<int:id>')
def pasar_recargando(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
        
    pedido = Pedido.query.get_or_404(id)
    pedido.estado = 'Recargando'
    db.session.commit()
    flash(f'Pago validado para el pedido #{pedido.id}. Estado cambiado a "Recargando".', 'success')
    return redirect(url_for('admin_panel', seccion='pedidos_recargando'))

@app.route('/admin/completar_recarga/<int:id>')
def completar_recarga(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
        
    pedido = Pedido.query.get_or_404(id)
    pedido.estado = 'Completado'
    h_lima = hora_lima()
    pedido.solo_fecha = h_lima.strftime('%d/%m/%Y')
    pedido.fecha = h_lima.strftime('%d/%m/%Y %H:%M')
    db.session.commit()

    otorgar_bono_referido_si_aplica(pedido.usuario_id)

    flash(f'Recarga completada para el pedido #{pedido.id}. Movido al historial.', 'success')
    return redirect(url_for('admin_panel', seccion='historial_envios'))

@app.route('/admin/eliminar_pedido/<int:id>')
def eliminar_pedido(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
        
    pedido = Pedido.query.get_or_404(id)
    db.session.delete(pedido)
    db.session.commit()
    flash(f'El pedido #{pedido.id} ha sido eliminado.', 'info')
    return redirect(url_for('admin_panel'))

@app.route('/admin/vaciar_historial_hoy')
def vaciar_historial_hoy():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
        
    hoy_str = hora_lima().strftime('%d/%m/%Y')
    pedidos_hoy = Pedido.query.filter_by(estado='Completado', solo_fecha=hoy_str).all()
    
    for p in pedidos_hoy:
        p.solo_fecha = hoy_str
        
    db.session.commit()
    flash('El historial de hoy ha sido vaciado y guardado en los paneles de archivo.', 'success')
    return redirect(url_for('admin_panel', seccion='historial_envios'))

@app.route('/admin/eliminar/<int:id>')
def eliminar_usuario(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
        
    usuario = Usuario.query.get_or_404(id)
    if usuario.rol == 'admin':
        flash('No puedes eliminar cuentas de administrador.', 'danger')
        return redirect(url_for('admin_panel', seccion='gestion_usuarios'))
        
    try:
        Pedido.query.filter_by(usuario_id=usuario.id).delete()
        RegistroReferido.query.filter((RegistroReferido.patrocinador_id == usuario.id) | (RegistroReferido.referido_id == usuario.id)).delete()
        UsoCodigoUsuario.query.filter_by(usuario_id=usuario.id).delete()
        CodigoPromo.query.filter_by(propietario_id=usuario.id).delete()
        Usuario.query.filter_by(referido_por_id=usuario.id).update({Usuario.referido_por_id: None})

        db.session.delete(usuario)
        db.session.commit()
        
        flash(f'El usuario {usuario.nombre} y todos sus datos asociados han sido eliminados.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el usuario: {str(e)}', 'danger')

    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

@app.route('/cliente/retirar_referidos', methods=['POST'])
def retirar_saldo_referidos():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        return redirect(url_for('login'))

    usuario_actual = db.session.get(Usuario, session['usuario_id'])
    jugador_id = request.form.get('jugador_id', '').strip()
    saldo_disponible = usuario_actual.saldo_fragmentos or 0

    if not jugador_id:
        flash('Debes ingresar tu ID de jugador para retirar tus fragmentos.', 'danger')
        return redirect(url_for('cliente_home', seccion='amigo_referidos'))

    if saldo_disponible <= 0:
        flash('Aún no tienes saldo de fragmentos disponible para retirar.', 'warning')
        return redirect(url_for('cliente_home', seccion='amigo_referidos'))

    codigo_unico_canje = f"CANJE-REF-{usuario_actual.id}-{os.urandom(2).hex().upper()}"
    h_lima = hora_lima()

    nuevo_pedido_canje = Pedido(
        usuario_id=usuario_actual.id,
        nombre_cliente=usuario_actual.nombre,
        jugador_id=jugador_id,
        detalle=f"Canje Referidos ({saldo_disponible} Fragmentos)",
        total=0.0,
        telefono_digitos='REF',
        codigo_operacion=codigo_unico_canje,
        codigo_promo=codigo_unico_canje,
        descuento_aplicado=0.0,
        estado='Recargando',
        solo_fecha=h_lima.strftime('%d/%m/%Y'),
        fecha=h_lima.strftime('%d/%m/%Y %H:%M')
    )

    usuario_actual.saldo_fragmentos = 0
    db.session.add(nuevo_pedido_canje)
    db.session.commit()

    flash(f'¡Retiro exitoso! Se generó tu código {codigo_unico_canje} y tus {saldo_disponible} fragmentos pasaron directo a recarga ⚡', 'success')
    return redirect(url_for('cliente_home', seccion='amigo_referidos'))

@app.route('/cliente/home')
def cliente_home():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        flash('Por favor inicia sesión con una cuenta de cliente.', 'warning')
        return redirect(url_for('login'))
    
    if 'carrito' not in session:
        session['carrito'] = []
    if 'codigo_aplicado' not in session:
        session['codigo_aplicado'] = None
        session['descuento_porcentaje'] = 0.0
        session['tipo_premio'] = 'descuento'
        session['cantidad_premio'] = 0.0
        
    seccion = request.args.get('seccion', 'catalogo')
    
    codigo_pat = request.args.get('codigo_patrocinador', '').strip().upper()
    usuario_actual = db.session.get(Usuario, session['usuario_id'])
    
    ya_compro = Pedido.query.filter(
        Pedido.usuario_id == usuario_actual.id,
        Pedido.telefono_digitos != 'REF'
    ).first() is not None
    
    if codigo_pat:
        if ya_compro:
            flash('Ya realizaste tu primera compra. Esta opción es exclusiva para cuentas nuevas sin compras.', 'danger')
        elif not usuario_actual.referido_por_id:
            patrocinador = Usuario.query.filter_by(codigo_referido=codigo_pat).first()
            if patrocinador and patrocinador.id != usuario_actual.id:
                usuario_actual.referido_por_id = patrocinador.id
                nuevo_reg = RegistroReferido(patrocinador_id=patrocinador.id, referido_id=usuario_actual.id)
                db.session.add(nuevo_reg)
                db.session.commit()
                
                otorgar_bono_referido_si_aplica(usuario_actual.id)
                    
                flash('¡Te has vinculado exitosamente con el código de tu amigo!', 'success')
            else:
                flash('El código de patrocinador ingresado no es válido.', 'danger')
        return redirect(url_for('cliente_home', seccion='amigo_referidos'))

    total_pases, total_fragmentos, total_cajas, puntos_fragmentos = calcular_estadisticas_usuario(usuario_actual.id)
    
    meta_rango = 5000
    if puntos_fragmentos >= meta_rango:
        usuario_actual.rango = 'Plata'
        progreso_porcentaje = 100
    else:
        usuario_actual.rango = 'Bronce'
        progreso_porcentaje = int((puntos_fragmentos / meta_rango) * 100)
    db.session.commit()

    mis_referidos = RegistroReferido.query.filter_by(patrocinador_id=usuario_actual.id).order_by(RegistroReferido.id.desc()).all()
    
    for ref in mis_referidos:
        if not ref.meta_cumplida:
            otorgar_bono_referido_si_aplica(ref.referido_id)

    config_referido = ConfiguracionReferido.query.first()
    premio_por_referido = config_referido.fragmentos_por_referido if (config_referido and config_referido.fragmentos_por_referido) else 20

    config_productos = obtener_config_productos()
    paquetes_diamantes = PaqueteDiamante.query.order_by(PaqueteDiamante.cantidad.asc()).all()

    historial_canjes_ref = Pedido.query.filter_by(
        usuario_id=usuario_actual.id,
        telefono_digitos='REF'
    ).order_by(Pedido.id.desc()).all()

    historial_compras = Pedido.query.filter_by(usuario_id=session['usuario_id']).order_by(Pedido.id.desc()).all()
    publicidad = AnuncioPublicidad.query.filter_by(activo=True).first()
        
    total_general = 0
    carrito_calculado = []
    for item in session['carrito']:
        prod = item['producto']
        cant = item['cantidad']
        subtotal, precio_unitario = calcular_subtotal_item(prod, cant)
        total_general += subtotal
        carrito_calculado.append({
            'producto': prod,
            'cantidad': cant,
            'precio_unitario': precio_unitario,
            'subtotal': round(subtotal, 2)
        })
        
    descuento_monto = 0.0
    if session.get('descuento_porcentaje', 0) > 0:
        descuento_monto = total_general * (session['descuento_porcentaje'] / 100.0)
        
    total_final = max(0.0, total_general - descuento_monto)
        
    return render_template(
        'cliente_home.html', 
        nombre=session.get('nombre'), 
        usuario=usuario_actual,
        ya_compro=ya_compro,
        total_pases=total_pases,
        total_fragmentos=total_fragmentos,
        total_cajas=total_cajas,
        progreso_porcentaje=progreso_porcentaje,
        puntos_fragmentos=puntos_fragmentos,
        meta_rango=meta_rango,
        mis_referidos=mis_referidos,
        premio_por_referido=premio_por_referido,
        config_productos=config_productos,
        paquetes_diamantes=paquetes_diamantes,
        historial_canjes_ref=historial_canjes_ref,
        publicidad=publicidad,
        Usuario=Usuario,
        CodigoPromo=CodigoPromo,
        carrito=carrito_calculado, 
        total_general=round(total_general, 2),
        descuento_monto=round(descuento_monto, 2),
        total_final=round(total_final, 2),
        codigo_aplicado=session.get('codigo_aplicado'),
        tipo_premio=session.get('tipo_premio', 'descuento'),
        cantidad_premio=session.get('cantidad_premio', 0),
        seccion=seccion,
        historial=historial_compras
    )

@app.route('/cliente/agregar', methods=['POST'])
def agregar_carrito():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        return redirect(url_for('login'))
        
    producto = request.form.get('producto')
    config_productos = obtener_config_productos()

    disponibilidad = {
        'Fragmentos': bool(config_productos.fragmentos_habilitado),
        'Cajas': bool(config_productos.cajas_habilitado),
        'Pases': bool(config_productos.pases_habilitado),
        'Diamantes': bool(config_productos.diamantes_habilitado)
    }

    if producto in disponibilidad and not disponibilidad[producto]:
        flash(f'El producto {producto} se encuentra sin stock en este momento.', 'warning')
        return redirect(url_for('cliente_home', seccion='catalogo'))

    if producto == 'Diamantes':
        try:
            cantidad_ingresada = int(request.form.get('cantidad', 0))
        except ValueError:
            cantidad_ingresada = 0

        paq_cercano = obtener_paquete_diamante_mas_cercano(cantidad_ingresada)
        if not paq_cercano:
            flash('No hay paquetes de Diamantes configurados actualmente.', 'warning')
            return redirect(url_for('cliente_home', seccion='catalogo'))

        cantidad = paq_cercano.cantidad
        if cantidad != cantidad_ingresada:
            flash(f'La cantidad se ajustó automáticamente al paquete disponible más cercano: {cantidad} Diamantes.', 'info')
    else:
        minimos = {
            'Fragmentos': 25,
            'Cajas': 5,
            'Pases': 1
        }
        minimo_requerido = minimos.get(producto, 1)

        try:
            cantidad = int(request.form.get('cantidad', minimo_requerido))
        except ValueError:
            cantidad = minimo_requerido

        if cantidad < minimo_requerido:
            flash(f'La cantidad mínima para {producto} es de {minimo_requerido} unidades.', 'warning')
            return redirect(url_for('cliente_home', seccion='catalogo'))
    
    if 'carrito' not in session:
        session['carrito'] = []
        
    carrito = session['carrito']
    encontrado = False
    for item in carrito:
        if item['producto'] == producto:
            if producto == 'Diamantes':
                paq_suma = obtener_paquete_diamante_mas_cercano(item['cantidad'] + cantidad)
                item['cantidad'] = paq_suma.cantidad if paq_suma else cantidad
            else:
                item['cantidad'] += cantidad
            encontrado = True
            break
            
    if not encontrado:
        carrito.append({'producto': producto, 'cantidad': cantidad})
        
    session.modified = True
    flash(f'Se agregaron {cantidad} de {producto} al carrito.', 'success')
    return redirect(url_for('cliente_home', seccion='catalogo'))

@app.route('/cliente/aplicar_codigo', methods=['POST'])
def aplicar_codigo():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        return redirect(url_for('login'))
    
    codigo_ingresado = request.form.get('codigo_promo', '').strip().upper()
    cp = CodigoPromo.query.filter_by(codigo=codigo_ingresado).first()
    
    if not cp:
        flash('Código promocional inválido o inexistente.', 'danger')
        return redirect(url_for('cliente_home', seccion='catalogo'))
        
    usuario_id = session['usuario_id']
    
    if cp.es_premio_referido and cp.propietario_id != usuario_id:
        flash('Cupón inválido: este código de recompensa no te pertenece o aún no has completado la misión.', 'danger')
        return redirect(url_for('cliente_home', seccion='catalogo'))

    if cp.tipo_limite == 'solo_una_vez':
        if cp.usos_actuales >= 1:
            flash('Este cupón era de un solo uso y ya fue canjeado.', 'danger')
            return redirect(url_for('cliente_home', seccion='catalogo'))
    
    elif cp.tipo_limite == 'una_por_cuenta':
        ya_usado = UsoCodigoUsuario.query.filter_by(usuario_id=usuario_id, codigo_id=cp.id).first()
        if ya_usado:
            flash('Este código ya fue utilizado en tu cuenta. Solo se permite una vez por usuario.', 'danger')
            return redirect(url_for('cliente_home', seccion='catalogo'))
            
    elif cp.tipo_limite == 'primeras_cuentas':
        if cp.usos_actuales >= cp.max_usos_primeras:
            flash(f'Este código ya alcanzó su límite máximo de uso ({cp.max_usos_primeras} cuentas).', 'danger')
            return redirect(url_for('cliente_home', seccion='catalogo'))

    tipo_p = getattr(cp, 'tipo_premio', None) or 'descuento'
    cant_p = cp.cantidad_premio if (getattr(cp, 'cantidad_premio', 0) and cp.cantidad_premio > 0) else cp.descuento_porcentaje

    session['codigo_aplicado'] = cp.codigo
    session['tipo_premio'] = tipo_p
    session['cantidad_premio'] = cant_p

    if tipo_p == 'descuento':
        session['descuento_porcentaje'] = cant_p
        flash(f'¡Código promocional {cp.codigo} aplicado ({cant_p}% de descuento)!', 'success')
    else:
        session['descuento_porcentaje'] = 0.0
        cant_fmt = int(cant_p) if float(cant_p).is_integer() else cant_p
        flash(f'¡Código promocional {cp.codigo} aplicado (+{cant_fmt} {tipo_p} de regalo en tu pedido)!', 'success')
        
    session.modified = True
    return redirect(url_for('cliente_home', seccion='catalogo'))

@app.route('/cliente/preparar_pago', methods=['POST'])
def preparar_pago():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        return redirect(url_for('login'))
        
    if not session.get('carrito'):
        flash('Tu carrito está vacío.', 'warning')
        return redirect(url_for('login'))
        
    jugador_id = request.form.get('jugador_id', '').strip()
    if not jugador_id:
        flash('Debes ingresar el ID de cuenta del jugador.', 'danger')
        return redirect(url_for('cliente_home', seccion='catalogo'))
        
    session['jugador_id_temp'] = jugador_id
    session.modified = True
    
    return redirect(url_for('cliente_home', seccion='pago_yape'))

@app.route('/cliente/pagar_yape', methods=['POST'])
def pagar_yape():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        return redirect(url_for('login'))
        
    if not session.get('carrito') or not session.get('jugador_id_temp'):
        flash('Sesión de pago expirada o carrito vacío.', 'warning')
        return redirect(url_for('cliente_home', seccion='catalogo'))
        
    telefono_digitos = request.form.get('telefono_digitos', '').strip()
    codigo_operacion = request.form.get('codigo_operacion', '').strip()
    
    if not telefono_digitos or not codigo_operacion:
        flash('Debes ingresar los últimos 3 dígitos y el código de operación.', 'danger')
        return redirect(url_for('cliente_home', seccion='pago_yape'))
        
    jugador_id = session['jugador_id_temp']
    
    total_general = 0
    detalle_items = []
    for item in session['carrito']:
        sub, _ = calcular_subtotal_item(item['producto'], item['cantidad'])
        total_general += sub
        detalle_items.append(f"{item['producto']} (x{item['cantidad']})")
        
    descuento_porc = session.get('descuento_porcentaje', 0.0)
    descuento_monto = total_general * (descuento_porc / 100.0) if descuento_porc > 0 else 0.0
    total_final = max(0.0, total_general - descuento_monto)
        
    detalle_texto = ", ".join(detalle_items)
    h_lima = hora_lima()
    
    codigo_usado_str = session.get('codigo_aplicado')
    if codigo_usado_str:
        cp_obj = CodigoPromo.query.filter_by(codigo=codigo_usado_str).first()
        if cp_obj:
            if cp_obj.tipo_limite == 'solo_una_vez' and cp_obj.usos_actuales >= 1:
                session.pop('codigo_aplicado', None)
                session.pop('descuento_porcentaje', None)
                session.pop('tipo_premio', None)
                session.pop('cantidad_premio', None)
                session.modified = True
                flash('El cupón aplicado ya fue usado por otra cuenta. Intenta finalizar tu compra nuevamente.', 'warning')
                return redirect(url_for('cliente_home', seccion='catalogo'))

            tipo_p = getattr(cp_obj, 'tipo_premio', None) or 'descuento'
            cant_p = cp_obj.cantidad_premio if (getattr(cp_obj, 'cantidad_premio', 0) and cp_obj.cantidad_premio > 0) else cp_obj.descuento_porcentaje
            if tipo_p != 'descuento' and cant_p > 0:
                cant_fmt = int(cant_p) if float(cant_p).is_integer() else cant_p
                detalle_texto += f" + Premio Cupón ({codigo_usado_str}): {cant_fmt} {tipo_p}"

            cp_obj.usos_actuales += 1
            if cp_obj.tipo_limite == 'una_por_cuenta':
                nuevo_uso = UsoCodigoUsuario(usuario_id=session['usuario_id'], codigo_id=cp_obj.id)
                db.session.add(nuevo_uso)
            db.session.commit()

    nuevo_pedido = Pedido(
        usuario_id=session['usuario_id'],
        nombre_cliente=session['nombre'],
        jugador_id=jugador_id,
        detalle=detalle_texto,
        total=round(total_final, 2),
        telefono_digitos=telefono_digitos,
        codigo_operacion=codigo_operacion,
        codigo_promo=session.get('codigo_aplicado', ''),
        descuento_aplicado=round(descuento_monto, 2),
        estado='Validación de pago',
        solo_fecha=h_lima.strftime('%d/%m/%Y'),
        fecha=h_lima.strftime('%d/%m/%Y %H:%M')
    )
    
    db.session.add(nuevo_pedido)
    db.session.commit()
    
    session['carrito'] = []
    session.pop('jugador_id_temp', None)
    session.pop('codigo_aplicado', None)
    session.pop('descuento_porcentaje', None)
    session.pop('tipo_premio', None)
    session.pop('cantidad_premio', None)
    session.modified = True
    
    flash('¡Pago registrado! Su pedido se encuentra en "Validación de pago".', 'success')
    return redirect(url_for('cliente_home', seccion='historial'))

@app.route('/cliente/vaciar')
def vaciar_carrito():
    session['carrito'] = []
    session.pop('jugador_id_temp', None)
    session.pop('codigo_aplicado', None)
    session.pop('descuento_porcentaje', None)
    session.pop('tipo_premio', None)
    session.pop('cantidad_premio', None)
    session.modified = True
    flash('El carrito ha sido vaciado.', 'info')
    return redirect(url_for('cliente_home', seccion='catalogo'))

@app.route('/logout')
def logout():
    if 'usuario_id' in session:
        usuario = db.session.get(Usuario, session['usuario_id'])
        if usuario:
            usuario.ultima_actividad = None
            db.session.commit()
    session.clear()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)