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
    
    return render_template(
        'admin.html', 
        pendientes=usuarios_pendientes, 
        confirmados=usuarios_confirmados,
        pedidos_validacion=pedidos_validacion,
        pedidos_recargando=pedidos_recargando,
        historial_envios=historial_envios,
        pedidos_hoy=pedidos_hoy,
        historicos_agrupados=historicos_agrupados,
        seccion=seccion_admin
    )

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
    pedido.solo_fecha = datetime.now().strftime('%d/%m/%Y')
    pedido.fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
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
        
    hoy_str = datetime.now().strftime('%d/%m/%Y')
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
        
    db.session.delete(usuario)
    db.session.commit()
    flash(f'El usuario {usuario.nombre} ha sido eliminado.', 'info')
    return redirect(url_for('admin_panel', seccion='gestion_usuarios'))

# Rutas del Cliente
@app.route('/cliente/home')
def cliente_home():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        flash('Por favor inicia sesión con una cuenta de cliente.', 'warning')
        return redirect(url_for('login'))
    
    if 'carrito' not in session:
        session['carrito'] = []
        
    seccion = request.args.get('seccion', 'catalogo')
    
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
        
    return render_template(
        'cliente_home.html', 
        nombre=session.get('nombre'), 
        carrito=carrito_calculado, 
        total_general=round(total_general, 2),
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
    return redirect(url_for('cliente_home'))

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
        return redirect(url_for('cliente_home'))
        
    session['jugador_id_temp'] = jugador_id
    session.modified = True
    
    return redirect(url_for('cliente_home', seccion='pago_yape'))

@app.route('/cliente/pagar_yape', methods=['POST'])
def pagar_yape():
    if 'usuario_id' not in session or session.get('rol') != 'cliente':
        return redirect(url_for('login'))
        
    if not session.get('carrito') or not session.get('jugador_id_temp'):
        flash('Sesión de pago expirada o carrito vacío.', 'warning')
        return redirect(url_for('cliente_home'))
        
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
        
    detalle_texto = ", ".join(detalle_items)
    
    nuevo_pedido = Pedido(
        usuario_id=session['usuario_id'],
        nombre_cliente=session['nombre'],
        jugador_id=jugador_id,
        detalle=detalle_texto,
        total=round(total_general, 2),
        telefono_digitos=telefono_digitos,
        codigo_operacion=codigo_operacion,
        estado='Validación de pago',
        solo_fecha=datetime.now().strftime('%d/%m/%Y')
    )
    
    db.session.add(nuevo_pedido)
    db.session.commit()
    
    session['carrito'] = []
    session.pop('jugador_id_temp', None)
    session.modified = True
    
    flash('¡Pago registrado! Su pedido se encuentra en "Validación de pago".', 'success')
    return redirect(url_for('cliente_home', seccion='seguimiento', buscar_id=jugador_id))

@app.route('/cliente/vaciar')
def vaciar_carrito():
    session['carrito'] = []
    session.pop('jugador_id_temp', None)
    session.modified = True
    flash('El carrito ha sido vaciado.', 'info')
    return redirect(url_for('cliente_home'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)