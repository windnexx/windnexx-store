import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'clave_secreta_windnexx_desarrollo'

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
        if m_frag:
            total_fragmentos += int(m_frag.group(1))

        m_cajas = re.search(r'Cajas \(x(\d+)\)', p.detalle)
        if m_cajas:
            total_cajas += int(m_cajas.group(1))

        m_pases = re.search(r'Pases \(x(\d+)\)', p.detalle)
        if m_pases:
            total_pases += int(m_pases.group(1))

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
            if not patrocinador:
                flash('El código de referido ingresado no es válido.', 'warning')

        hashed_password = generate_password_hash(password)
        nuevo_usuario = Usuario(
            nombre=nombre,
            correo=correo,
            telefono=telefono,
            password=hashed_password,
            rol='cliente',
            confirmado=False,
            categoria='Cliente',
            rango='Bronce',
            referido_por_id=patrocinador.id if patrocinador else None
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
    solicitudes_reset = Usuario.query.filter_by(solicitud_reset=True).all()
    codigos_promo = CodigoPromo.query.all()
    registros_referidos = RegistroReferido.query.all()
    
    limite_online = datetime.now(TIMEZONE_LIMA).replace(tzinfo=None) - timedelta(minutes=3)
    for u in usuarios_confirmados:
        u.en_linea = bool(u.ultima_actividad and u.ultima_actividad >= limite_online)
    
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
        pedidos_validacion=pedidos_validacion,
        pedidos_recargando=pedidos_recargando,
        historial_envios=historial_envios,
        pedidos_hoy=pedidos_hoy,
        historicos_agrupados=historicos_agrupados,
        seccion=seccion_admin,
        Usuario=Usuario
    )

@app.route('/admin/crear_codigo', methods=['POST'])
def crear_codigo():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    
    codigo = request.form.get('codigo', '').strip().upper()
    try:
        descuento = float(request.form.get('descuento', 0))
    except ValueError:
        descuento = 0
        
    tipo_limite = request.form.get('tipo_limite', 'ilimitado')
    try:
        max_usos_primeras = int(request.form.get('max_usos_primeras', 0))
    except ValueError:
        max_usos_primeras = 0

    es_premio = True if request.form.get('es_premio_referido') == 'on' else False
    
    if codigo and descuento > 0:
        if not CodigoPromo.query.filter_by(codigo=codigo).first():
            nuevo_cp = CodigoPromo(
                codigo=codigo, 
                descuento_porcentaje=descuento,
                tipo_limite=tipo_limite,
                max_usos_primeras=max_usos_primeras,
                usos_actuales=0,
                es_premio_referido=es_premio
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
    db.session.delete(cp)
    db.session.commit()
    flash('Código promocional eliminado.', 'info')
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

    cliente_pedido = Usuario.query.get(pedido.usuario_id)
    if cliente_pedido and cliente_pedido.referido_por_id:
        _, _, _, frag_equiv_total = calcular_estadisticas_usuario(cliente_pedido.id)
        if frag_equiv_total >= 1456:
            reg_ref = RegistroReferido.query.filter_by(patrocinador_id=cliente_pedido.referido_por_id, referido_id=cliente_pedido.id).first()
            if reg_ref and not reg_ref.meta_cumplida:
                reg_ref.meta_cumplida = True
                db.session.commit()

                # Crear cupón exclusivo y personal para el patrocinador que ganó la recompensa
                patrocinador = Usuario.query.get(cliente_pedido.referido_por_id)
                if patrocinador:
                    codigo_personal = f"PREMIO-{patrocinador.id}-{os.urandom(2).hex().upper()}"
                    existe_cupon = CodigoPromo.query.filter_by(propietario_id=patrocinador.id, es_premio_referido=True).first()
                    if not existe_cupon:
                        nuevo_cupon_ref = CodigoPromo(
                            codigo=codigo_personal,
                            descuento_porcentaje=10.0,
                            tipo_limite='una_por_cuenta',
                            es_premio_referido=True,
                            propietario_id=patrocinador.id
                        )
                        db.session.add(nuevo_cupon_ref)
                        db.session.commit()

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
        p.solo_fecha = "Archivado (" + hoy_str + ")"
        
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

# Rutas del Cliente
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
        
    seccion = request.args.get('seccion', 'catalogo')
    
    codigo_pat = request.args.get('codigo_patrocinador', '').strip().upper()
    usuario_actual = db.session.get(Usuario, session['usuario_id'])
    
    if codigo_pat and not usuario_actual.referido_por_id:
        patrocinador = Usuario.query.filter_by(codigo_referido=codigo_pat).first()
        if patrocinador and patrocinador.id != usuario_actual.id:
            usuario_actual.referido_por_id = patrocinador.id
            nuevo_reg = RegistroReferido(patrocinador_id=patrocinador.id, referido_id=usuario_actual.id)
            db.session.add(nuevo_reg)
            db.session.commit()
            
            _, _, _, frag_equiv_actual = calcular_estadisticas_usuario(usuario_actual.id)
            if frag_equiv_actual >= 1456:
                nuevo_reg.meta_cumplida = True
                db.session.commit()
                
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

    mis_referidos = RegistroReferido.query.filter_by(patrocinador_id=usuario_actual.id).all()
    
    for ref in mis_referidos:
        if not ref.meta_cumplida:
            _, _, _, f_eq = calcular_estadisticas_usuario(ref.referido_id)
            if f_eq >= 1456:
                ref.meta_cumplida = True
                patrocinador = Usuario.query.get(ref.patrocinador_id)
                if patrocinador:
                    existe_cupon = CodigoPromo.query.filter_by(propietario_id=patrocinador.id, es_premio_referido=True).first()
                    if not existe_cupon:
                        nuevo_cupon_ref = CodigoPromo(
                            codigo=f"PREMIO-{patrocinador.id}-{os.urandom(2).hex().upper()}",
                            descuento_porcentaje=10.0,
                            tipo_limite='una_por_cuenta',
                            es_premio_referido=True,
                            propietario_id=patrocinador.id
                        )
                        db.session.add(nuevo_cupon_ref)
    db.session.commit()

    buscar_id = request.args.get('buscar_id', '').strip()
    resultados_seguimiento = []
    if buscar_id:
        resultados_seguimiento = Pedido.query.filter_by(jugador_id=buscar_id).all()

    historial_compras = Pedido.query.filter_by(usuario_id=session['usuario_id']).order_by(Pedido.id.desc()).all()
        
    total_general = 0
    carrito_calculado = []
    for item in session['carrito']:
        prod = item['producto']
        cant = item['cantidad']
        precio_unitario = PRECIOS.get(prod, 0)
        subtotal = cant * precio_unitario
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
        total_pases=total_pases,
        total_fragmentos=total_fragmentos,
        total_cajas=total_cajas,
        progreso_porcentaje=progreso_porcentaje,
        puntos_fragmentos=puntos_fragmentos,
        meta_rango=meta_rango,
        mis_referidos=mis_referidos,
        Usuario=Usuario,
        CodigoPromo=CodigoPromo,
        carrito=carrito_calculado, 
        total_general=round(total_general, 2),
        descuento_monto=round(descuento_monto, 2),
        total_final=round(total_final, 2),
        codigo_aplicado=session.get('codigo_aplicado'),
        seccion=seccion,
        historial=historial_compras,
        resultados_seguimiento=resultados_seguimiento,
        buscar_id=buscar_id
    )

@app.route('/cliente/agregar', methods=['POST'])
def agregar_carrito():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        return redirect(url_for('login'))
        
    producto = request.form.get('producto')
    try:
        cantidad = int(request.form.get('cantidad', 1))
        if cantidad < 1:
            cantidad = 1
    except ValueError:
        cantidad = 1
    
    if 'carrito' not in session:
        session['carrito'] = []
        
    carrito = session['carrito']
    encontrado = False
    for item in carrito:
        if item['producto'] == producto:
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
    
    # Validar exclusividad del cupón de referido
    if cp.es_premio_referido and cp.propietario_id != usuario_id:
        flash('Cupón inválido: este código de recompensa no te pertenece o aún no has completado la misión.', 'danger')
        return redirect(url_for('cliente_home', seccion='catalogo'))
    
    if cp.tipo_limite == 'una_por_cuenta':
        ya_usado = UsoCodigoUsuario.query.filter_by(usuario_id=usuario_id, codigo_id=cp.id).first()
        if ya_usado:
            flash('Este código ya fue utilizado en tu cuenta. Solo se permite una vez por usuario.', 'danger')
            return redirect(url_for('cliente_home', seccion='catalogo'))
            
    elif cp.tipo_limite == 'primeras_cuentas':
        if cp.usos_actuales >= cp.max_usos_primeras:
            flash(f'Este código ya alcanzó su límite máximo de uso ({cp.max_usos_primeras} cuentas).', 'danger')
            return redirect(url_for('cliente_home', seccion='catalogo'))

    session['codigo_aplicado'] = cp.codigo
    session['descuento_porcentaje'] = cp.descuento_porcentaje
    flash(f'¡Código promocional {cp.codigo} aplicado ({cp.descuento_porcentaje}% de descuento)!', 'success')
        
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
        sub = item['cantidad'] * PRECIOS.get(item['producto'], 0)
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
    session.modified = True
    
    flash('¡Pago registrado! Su pedido se encuentra en "Validación de pago".', 'success')
    return redirect(url_for('cliente_home', seccion='seguimiento', buscar_id=jugador_id))

@app.route('/cliente/vaciar')
def vaciar_carrito():
    session['carrito'] = []
    session.pop('jugador_id_temp', None)
    session.pop('codigo_aplicado', None)
    session.pop('descuento_porcentaje', None)
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