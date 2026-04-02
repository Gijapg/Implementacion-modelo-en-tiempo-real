# MT VPS Código Mínimo

Sistema de Trading Automatizado para Forex basado en Machine Learning con análisis técnico avanzado usando Wavelet y Hidden Markov Models.

## Descripción General

Este proyecto implementa un bot de trading completamente automatizado que opera en MetaTrader5, utilizando estrategias avanzadas de machine learning para tomar decisiones de trading en mercados Forex. El sistema está optimizado para ejecutarse en un VPS y proporciona una API web para monitoreo y control remoto.

## Características Principales

- Trading Automatizado: Opera 24/7 en el par USDJPY
- Machine Learning: Análisis Wavelet combinado con Hidden Markov Models (HMM) con comprobación en producción
- API Asincrónica: Backend con Quart para procesamiento concurrente
- Autenticación Segura: Integración con bcrypt y JWT
- Pagos Online: Integración con Stripe para usuarios premium
- Base de Datos: Almacenamiento de datos en MySQL
- Logging Completo: Sistema de registro detallado para debugging
- Arquitectura Escalable: Preparada para soportar múltiples estrategias en múltiples activos


## Flujo de Trabajo General

El sistema sigue un flujo de trabajo estructurado basado en análisis de datos de mercado y generación de señales de trading:

### 1. Captura de Datos de Mercado

El bot recolecta datos de velas (candles) de MetaTrader5 en timeframe H1 (1 hora) para USDJPY:

- Obtiene 1010 velas históricas
- Convierte timestamps UNIX a formato datetime de pandas
- Estructura los datos en DataFrame con columnas: time, open, high, low, close, tick_volume, spread, real_volume

### 2. Cálculo de Features Técnicos

Una vez recolectados los datos, se calculan features avanzados:

**Features Básicos:**
- Retornos logarítmicos (log_returns)
- Rango de precios (range)
- Volatilidad ATR (Average True Range)

**Features Wavelet:**
- Descomposición Wavelet tipo 'db4' (Daubechies 4)
- Ventana de análisis: 12 períodos
- Nivel de descomposición: 2
- Volatilidad extraída de coeficientes Wavelet (wavelet_vol) 

**Features de Tendencia:**
- Fuerza de tendencia (trend_strength)
- Autocorrelación lag-5 (autocorr_5)
- Indicadores técnicos mediante pandas_ta

### 3. Carga de Modelo Entrenado

El sistema carga el modelo de Hidden Markov Model pre-entrenado para USDJPY:

```
wavelet_hmm_model_USDJPY_20260130_2234.pkl
```

Cada modelo contiene:
- Componentes HMM entrenados con máquinas de estados
- StandardScaler para normalización de features
- Parámetros optimizados (número de estados, matriz de transición)

### 4. Generación de Señales

El modelo HMM cargado procesa los features recolectados y genera señales:

- Normaliza los features usando el scaler del modelo
- Predice estados de mercado (estados ocultos del HMM)
- Detecta transiciones de estado que indican cambios de tendencia
- Genera señal BUY (1) o SELL (-1) cuando se cumple el criterio de consolidación

**Consolidación:** El sistema requiere múltiples confirmaciones (consolidation_required = 1-3) antes de generar una señal para evitar falsos positivos.

### 5. Ejecución de Órdenes

Cuando se genera una señal válida:

**Cálculo de Riesgo (USDJPY):**
- Obtiene el balance de cuenta actual
- Calcula el riesgo permitido (risk_percent = 1% del balance)
- Determina Stop Loss: price - ATR * 3
- Determina Take Profit: price + ATR * 9

**Validación de Precios:**
- Verifica que el precio no sea 0 o negativo
- Contrasta contra bid/ask actual del mercado
- Calcula tamaño de lote dinámico basado en el riesgo

**Envío de Orden:**
- Crea orden de mercado o pendiente
- Incluye Stop Loss y Take Profit
- Registra con magic number único (5555555555)
- Guarda información en logs para auditoría

### 6. Monitoreo y Cierre

El sistema mantiene vigilancia continua:

- Verifica posiciones abiertas
- Monitorea Stop Loss y Take Profit
- Registra todas las operaciones en logs

## Componentes Principales

## API REST - Documentación Completa

El servidor API está construido con Quart (framework asincrónico para Python) y proporciona una interfaz completa para gestión de usuarios, autenticación, suscripciones, control de MetaTrader5 y monitoreo del bot.

### Configuración Base

- Host: 38.247.140.62
- Puerto: 80
- Framework: Quart (asincrónico)
- Autenticación: JWT (JSON Web Tokens)
- Base de Datos: MySQL (asincrónica con aiomysql)

### Estructura de Respuestas

Todas las respuestas devuelven JSON con el siguiente formato:

```json
{
  "status": "success|fail",
  "message": "Descripción de la operación",
  "data": {}
}
```

### Endpoints Disponibles

#### 1. Health Check

**GET /**

Verifica que el servidor está funcionando.

Respuesta exitosa:
```
HTTP/1.1 200 OK
Hello, World!
```

---

#### 2. Autenticación de Usuarios

**POST /register**

Registra un nuevo usuario en el sistema.

Request:
```json
{
  "username": "usuario",
  "password": "contraseña"
}
```

Respuesta exitosa (201):
```json
{
  "status": "success",
  "message": "Inicio de sesión exitoso",
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "username": "usuario"
}
```

Errores:
- 400: Faltan datos (username o password)
- 409: El usuario ya existe

---

**POST /login**

Inicia sesión con credenciales existentes.

Request:
```json
{
  "username": "usuario",
  "password": "contraseña"
}
```

Respuesta exitosa (200):
```json
{
  "status": "success",
  "message": "Inicio de sesión exitoso",
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
}
```

Errores:
- 400: Faltan datos
- 401: Credenciales inválidas

---

**GET /check_session**

Verifica si el token JWT actual es válido.

Headers requeridos:
```
Authorization: eyJ0eXAiOiJKV1QiLCJhbGc...
```

Respuesta exitosa (200):
```json
{
  "username": "usuario"
}
```

Errores:
- 401: Token expirado o inválido

---

**POST /logout**

Cierra la sesión actual del usuario.

Respuesta exitosa (200):
```json
{
  "message": "Sesión cerrada correctamente"
}
```

---

#### 3. Gestión de Cuenta MetaTrader5

**PUT /update_account**

Actualiza las credenciales de MetaTrader5 del usuario. Las contraseñas se almacenan hasheadas con bcrypt.

Request:
```json
{
  "username": "usuario",
  "account_id": 12345678,
  "account_password": "contraseña_mt5",
  "server": "ICMarkets-Demo"
}
```

Respuesta exitosa (200):
```json
{
  "status": "success",
  "message": "Detalles actualizados correctamente"
}
```

Errores:
- 400: Falta alguno de los campos requeridos
- 404: Usuario no encontrado
- 500: Error de base de datos

---

**POST /initialize-mt5**

Valida las credenciales e inicializa la conexión con MetaTrader5. Esta es una operación crítica que establece la conexión con la plataforma de trading.

Request:
```json
{
  "username": "usuario",
  "password": "contraseña_mt5"
}
```

Respuesta exitosa (200):
```json
{
  "message": "MetaTrader 5 initialized successfully!"
}
```

Errores:
- 400: Faltan username o password
- 401: Username o password inválidos
- 500: Error al inicializar MT5 (verificar credenciales del servidor)

---

#### 4. Gestión de Pagos (Stripe)

**POST /get_logged_in_user**

Maneja la autenticación de usuarios con Stripe para procesamiento de pagos. Crea o recupera un cliente Stripe vinculado al usuario y genera una sesión de checkout.

Request:
```json
{
  "username": "usuario"
}
```

Respuesta exitosa (200):
```json
{
  "status": "success",
  "username": "usuario",
  "customer_id": "cus_xxxxxxxxxxxxx",
  "payment_link_url": "https://checkout.stripe.com/pay/cs_..."
}
```

Errores:
- 400: Username no proporcionado
- 500: Error al procesar con Stripe

---

**POST /stripe/webhook**

Webhook para recibir eventos de Stripe. Maneja:
- `checkout.session.completed`: Pago completado
- `invoice.payment_succeeded`: Pago exitoso de suscripción
- `customer.subscription.deleted`: Suscripción cancelada

Headers requeridos:
```
Stripe-Signature: t=...,v1=...
```

Body: Payload firmado de Stripe (raw)

Respuesta exitosa (200):
```
Success
```

Errores:
- 400: Payload inválido
- 400: Firma no válida
- 500: Error procesando webhook

---

**POST /verify_subscription**

Verifica si un usuario tiene una suscripción activa y válida.

Request:
```json
{
  "username": "usuario"
}
```

Respuesta exitosa - Suscripción activa (200):
```json
{
  "access_granted": true
}
```

Respuesta exitosa - Suscripción inactiva o expirada (403):
```json
{
  "access_granted": false,
  "message": "Suscripción inactiva o expirada"
}
```

Errores:
- 400: Username no proporcionado
- 404: Usuario no encontrado
- 500: Error de base de datos

---

#### 5. Control del Bot de Trading

**POST /start_bot**

Inicia el bot de trading automatizado. Comienza a ejecutar la lógica de trading en segundo plano.

Parámetros: Ninguno

Respuesta exitosa (200):
```json
{
  "status": "success",
  "message": "Bot iniciado"
}
```

Errores:
- 400: El bot ya está en ejecución

Notas:
- El bot se ejecuta en un ciclo asincrónico y verifica posiciones cada 60 segundos
- Solo opera en el par USDJPY actualmente
- Utiliza MetaTrader5 debe estar inicializado previamente

---

**POST /stop_bot**

Detiene la ejecución del bot de trading.

Parámetros: Ninguno

Respuesta exitosa (200):
```json
{
  "status": "success",
  "message": "Bot detenido"
}
```

Errores:
- 400: El bot no está en ejecución

---

**GET /check_bot_status**

Obtiene el estado actual del bot.

Parámetros: Ninguno

Respuesta (200):
```json
{
  "active": true o false
}
```

---

#### 6. Monitoreo y Logging

**GET /get_operations**

Obtiene todos los mensajes de registro de las operaciones realizadas por el bot.

Parámetros: Ninguno

Respuesta (200):
```
El bot esta trabajando para USDJPY...
No se pueden obtener los precios, cierre y vuelva a iniciar sesion.
El bot esta trabajando para USDJPY...
```

Content-Type: text/plain

Notas:
- Devuelve mensajes concatenados separados por nueva línea
- Los mensajes se limpian automáticamente entre ciclos
- Útil para debugging y monitoreo en tiempo real

---

### Flujo de Uso Típico

1. **Registro/Login**
   ```
   POST /register → JWT token
   ```

2. **Actualizar Credenciales MT5**
   ```
   PUT /update_account → Guardar credenciales encriptadas
   ```

3. **Inicializar MetaTrader5**
   ```
   POST /initialize-mt5 → Conexión establecida
   ```

4. **Iniciar Bot**
   ```
   POST /start_bot → Bot activo
   GET /check_bot_status → Verificar estado
   GET /get_operations → Monitorear operaciones
   ```

5. **Pagos**
   ```
   POST /get_logged_in_user → Link de pago
   POST /stripe/webhook → Confirmación de pago
   POST /verify_subscription → Verificar acceso
   ```

### Seguridad

- Todas las contraseñas se hashean con bcrypt antes de almacenarse
- Los tokens JWT expiran después de 24 horas
- Las credenciales de MT5 se almacenan encriptadas
- Validación de entrada en todos los endpoints
- Logging detallado de todas las operaciones en archivo debug.log

### Manejo de Errores

Códigos HTTP utilizados:
- 200: Operación exitosa
- 201: Recurso creado exitosamente
- 400: Solicitud inválida (faltan datos)
- 401: No autorizado (token inválido, credenciales incorrectas)
- 403: Prohibido (suscripción requerida)
- 404: Recurso no encontrado
- 409: Conflicto (usuario ya existe)
- 500: Error del servidor

### backend_14.py - Servidor API

### MAIN_BOT.py - Orquestador de Estrategias

Punto de entrada para la lógica principal del trading:

```python
def logica_bot(symbol, candles_data):
```

**Flujo para USDJPY:**
- Ejecuta Wavelet_HMM_Strategy con parámetros optimizados
- wavelet_window=12, level=2, type='db4'
- consolidation_required=1 (requiere 1 confirmación)
- Obtiene datos de velas, estructura en DataFrame con índice temporal


### estrategias.py - Implementación de Wavelet_HMM_Strategy

Estrategia principal que combina análisis Wavelet con Hidden Markov Models:

1. **Validación de datos:** Verifica mínimo 1000 velas disponibles
2. **Cálculo de features básicos:** Log-returns, rango, ATR
3. **Aplicación de Wavelet:** Descomposición multiescala
4. **Extracción de features de tendencia:** Fuerza y autocorrelación
5. **Normalización:** Usa scaler del modelo cargado
6. **Predicción HMM:** Genera estados predichos
7. **Detección de transiciones:** Observa cambios de estado
8. **Generación de señales:** Con requisito de consolidación
9. **Cálculo de riesgos:** ATR-based SL y TP
10. **Ejecución:** Envía orden a MetaTrader5

### ORDENES.py - Gestión de Órdenes

Funciones críticas para validación y ejecución:

- `is_price_valid()`: Verifica precio contra bid/ask actual
- `calculate_lot_size()`: Calcula tamaño dinámico basado en riesgo
- Funciones de apertura/cierre de órdenes con manejo de errores

### auxiliar.py - Utilidades

Funciones de soporte:

- `get_last_trade_time_by_magic()`: Obtiene timestamp de última operación
- `get_candle_data()`: Recolecta datos de velas de MT5
- Cálculo de indicadores técnicos (ATR, MA, etc.)
- Análisis de órdenes pendientes y posiciones

### safe_operations.py - Operaciones Seguras

Abstracciones seguras para MetaTrader5:

- Validaciones antes de operaciones críticas
- Manejo de errores y reintentos
- Logging de operaciones fallidas


## Seguridad

- Contraseñas hasheadas con bcrypt
- Tokens JWT para autenticación
- Variables sensibles en archivo .env
- Validación de precios antes de órdenes
- Risk management automático
- Logging detallado para auditoría

## Dependencias

- metatrader5 - Conexión con plataforma de trading
- Quart - Framework web asincrónico
- pandas/numpy - Análisis de datos
- scikit-learn - Machine Learning
- hmmlearn - Hidden Markov Models
- PyWavelets - Análisis Wavelet
- pandas_ta - Indicadores técnicos
- aiomysql - Driver async para MySQL
- bcrypt - Hashing de contraseñas
- PyJWT - JWT tokens
- Stripe - Procesamiento de pagos
- python-dotenv - Gestión de variables de entorno

