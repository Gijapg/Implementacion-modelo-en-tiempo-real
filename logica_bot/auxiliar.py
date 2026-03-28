import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
import MetaTrader5 as mt5
import pandas_ta as ta
import pywt
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler, RobustScaler
from scipy import stats
import random
import joblib
import os
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pywt")

import logging

logger = logging.getLogger(__name__)


np.random.seed(42)  # Semilla para numpy
random.seed(42)     # Semilla para Python


def get_last_trade_time_by_magic(symbol, magic):
    from_date = datetime.now() - timedelta(days=30)
    to_date = datetime.now()

    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        return None

    # Filtrar por magic
    magic_deals = [d for d in deals if d.magic == magic]
    if not magic_deals:
        return None

    # Si se especifica un símbolo, filtrar también por símbolo
    if symbol is not None:
        magic_deals = [d for d in magic_deals if d.symbol == symbol]
        if not magic_deals:
            return None

    open_deals = [d for d in magic_deals if d.entry == 0]
    
    if not open_deals:
        open_deals = magic_deals
    
    last_deal = max(open_deals, key=lambda d: d.time)

    # Conversión base
    dt = datetime.utcfromtimestamp(last_deal.time)

    # OFFSET EXACTO para que coincida con MT5
    offset = timedelta(hours=3, minutes=40, seconds=44)

    return dt 



def calcular_atr(df, periodo):
    """
    Retorna el último valor del ATR (igual que la original).
    """
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    
    atr = df.ta.atr(length=periodo, mamode='RMA', append=False)
    return atr.iloc[-1]


def calculate_monte_carlo_percentiles(symbol, timeframe, lookback_months=6, 
                                     num_simulations=10000, forecast_bars=24,
                                     upper_percentile=0.9, lower_percentile=0.1):
    # Obtener hora actual del servidor
    ultima_vela = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 1)[0]
    ultima_vela_hora = pd.to_datetime(ultima_vela['time'], unit='s')
    print(f"\nÚltima vela H1 completa: {ultima_vela_hora}")
    
    # Forzar end_date a las 00:00 del día de la última vela completa
    end_date = datetime.combine(ultima_vela_hora.date(), time.min)
    print(f'en date: {end_date}')
    # Calcular fecha de inicio (lookback_months antes de end_date)
    start_date = end_date - timedelta(days=30*lookback_months)
    
    # Obtener datos históricos (hasta 00:00 del día actual)
    rates = mt5.copy_rates_range(symbol, timeframe, start_date, end_date)
    if rates is None or len(rates) < 2:
        print("Error al obtener datos históricos")
        return None, None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)

    df = df[df.index <= end_date]  # <= para incluir exactamente las 00:00
    
    # Calcular retornos logarítmicos
    df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
    returns = df['log_returns'].dropna().values
    
    if len(returns) < 10:
        print("Datos insuficientes para cálculo")
        return None, None
    
    # Calcular media y desviación estándar de retornos
    mean_return = np.mean(returns)
    std_return = np.std(returns)
    
    # Obtener último precio disponible (antes de 00:00)
    last_price = df['close'].iloc[-1]
    
    # Simulación Monte Carlo
    simulated_prices = []
    
    for _ in range(num_simulations):
        price = last_price
        for __ in range(forecast_bars):
            # Movimiento browniano geométrico
            price *= np.exp(mean_return + std_return * np.random.normal())
        simulated_prices.append(price)
    
    # Calcular percentiles
    upper_level = np.percentile(simulated_prices, upper_percentile * 100)
    lower_level = np.percentile(simulated_prices, lower_percentile * 100)
    
    print(f"Cálculo completado. Último precio usado: {last_price:.5f}")
    print(f"Niveles calculados - Lower: {lower_level:.5f}, Upper: {upper_level:.5f}")
    
    return lower_level, upper_level



#CONSOLIDATION_REQUIRED = 1
VOL_INCREASE_MULT = 0.6
MIN_PRICE_MOVE = 0.0
COOLDOWN_HOURS = 24
#WAVELET = 'db4'
#WAVELET_LEVEL = 2
#WAVELET_WINDOW = 12

# Variables globales para el estado de la estrategia
last_trained_model = None
last_trained_scaler = None
last_state_info = None
last_training_time = None
last_signal_time = None

# -----------------------
# Funciones auxiliares para la estrategia
# -----------------------
def _wavelet_vol_from_array(arr, wavelet_type, wavelet_level):
    """Calcula volatilidad wavelet y noise_level desde un array."""
    try:
        if len(arr) < 4:
            return np.nan, np.nan
        coeffs = pywt.wavedec(arr, wavelet_type, level=wavelet_level)
        detail_coeffs = coeffs[1:]
        detail_stds = [np.std(c) for c in detail_coeffs if len(c) > 0]
        wavelet_vol = float(np.mean(detail_stds)) if len(detail_stds) > 0 else 0.0
        noise = float(np.std(detail_coeffs[0])) if len(detail_coeffs) > 0 and len(detail_coeffs[0]) > 0 else 0.0
        return wavelet_vol, noise
    except Exception:
        return np.nan, np.nan

def calculate_wavelet_features_series(close_series, wavelet_window, wavelet_level, wavelet_type):
    """Calcula características wavelet de forma causal."""
    wavelet_vol = close_series.rolling(window=wavelet_window, min_periods=wavelet_window).apply(
        lambda arr: _wavelet_vol_from_array(arr, wavelet_type, wavelet_level)[0], raw=True
    )
    noise_level = close_series.rolling(window=wavelet_window, min_periods=wavelet_window).apply(
        lambda arr: _wavelet_vol_from_array(arr, wavelet_type, wavelet_level)[1], raw=True
    )
    return wavelet_vol, noise_level

def calculate_basic_features(df):
    """Calcula características básicas del dataframe."""
    df = df.copy()
    df['returns'] = df['close'].pct_change()
    df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
    df['std_vol_20'] = df['log_returns'].rolling(20, min_periods=5).std()
    df['range'] = (df['high'] - df['low']) / df['close']
    
    def window_autocorr(x):
        if len(x) < 3:
            return np.nan
        s = pd.Series(x)
        return s.autocorr(lag=1)
    
    df['autocorr_5'] = df['returns'].rolling(5, min_periods=3).apply(window_autocorr, raw=True)
    df['momentum'] = df['close'] / df['close'].shift(5) - 1
    return df

def calculate_trend_and_wavelet_features(df_subset, wavelet_window, wavelet_level, wavelet_type):
    """Calcula características de tendencia y wavelet."""
    df = df_subset.copy()
    df['ma_fast'] = df['close'].rolling(8, min_periods=1).mean()
    df['ma_slow'] = df['close'].rolling(21, min_periods=1).mean()
    df['trend_strength'] = (df['ma_fast'] - df['ma_slow']) / df['ma_slow']
    df['volume_ratio'] = df['tick_volume'] / df['tick_volume'].rolling(20, min_periods=5).mean()
    
    wv, noise = calculate_wavelet_features_series(df['close'], wavelet_window, wavelet_level, wavelet_type)
    df['wavelet_vol'] = wv
    df['noise_level'] = noise
    
    return df


def predict_states_with_viterbi(model, scaler, df, features):
    """Predice estados usando el algoritmo de Viterbi."""
    states_aligned = np.full(len(df), -1, dtype=int)
    if model is None or scaler is None:
        return states_aligned

    X_df = df[features]
    mask = ~X_df.isnull().any(axis=1)
    if mask.sum() == 0:
        return states_aligned

    X_valid = X_df.loc[mask].values
    try:
        X_scaled = scaler.transform(X_valid)
        X_scaled = np.nan_to_num(X_scaled)
        preds = model.predict(X_scaled)
    except Exception:
        return states_aligned

    valid_positions = np.flatnonzero(mask.values)
    states_aligned[valid_positions] = preds
    return states_aligned

def generate_transition_signal_realtime(symbol, df, state_info, model, scaler, consolidation_required, last_signal_time=None):
    """
    Versión para tiempo real 
    - Usa TODO el histórico (igual que backtest)
    - Evalúa SOLO la última vela cerrada
    - El dataset ya excluye la vela en formación
    """
    features = ['log_returns', 'wavelet_vol', 'autocorr_5', 'trend_strength', 'range']

    # Necesitamos suficientes velas para contexto
    if len(df) < 5:
        return None, last_signal_time

    # USAMOS TODO EL DATASET (igual que backtest)
    full_data = df.copy()

    # Predecir estados para TODAS las velas
    states = predict_states_with_viterbi(model, scaler, full_data, features)
    if len(states) == 0:
        logger.error(f'ERROOOOORR hay 0 estados HMM {len(states)}, {len(full_data)}')
        return None, last_signal_time
    #if -1 in states:
        #print(f"ATENCION: -1 detectado en estados. Total: {int((states == -1).sum())}")


    state_labels = [state_info.get(s, {}).get('label', f'UNKNOWN_{s}') for s in states]

    # Índice de la última vela cerrada
    i = -1  

    try:
        state_i = states[i]
        idx = full_data.index[i] + timedelta(hours=1)

        # Cooldown check
        last_trade_time = get_last_trade_time_by_magic(symbol, 5555555555)

        if last_trade_time is not None:
            #logger.debug(f'last_trade_time: {last_trade_time}')
            #logger.debug(f'idx: {idx}')
            #diff = (idx - last_trade_time)
            #print(f'Diff desde última trade: {diff}')
            if (idx - last_trade_time) < timedelta(hours=COOLDOWN_HOURS):
                return None, last_signal_time

        current_label = state_labels[i]
        prev_labels = state_labels[i-3:i]  # 3 velas anteriores reales

        # Confirmar consolidación previa
        consolidation_count = sum(
            1 for lab in prev_labels 
            if ('CONSOLIDACION' in lab)
        )
        if consolidation_count < consolidation_required:
            return None, last_signal_time


        # Dirección
        if 'TENDENCIA_ALCISTA' in current_label:
            signal_direction = 1
            strategy = 'BREAKOUT_BULL'
        elif 'TENDENCIA_BAJISTA' in current_label:
            signal_direction = -1
            strategy = 'BREAKOUT_BEAR'
        else:
            return None, last_signal_time

        # Datos de velas reales
        curr = full_data.iloc[i]
        prev = full_data.iloc[i-1]
        prev2 = full_data.iloc[i-2]

        # Volatilidad
        current_vol = float(curr.get('wavelet_vol', 0.0) or 0.0)
        prev_vol   = float(prev.get('wavelet_vol', 0.0) or 0.0)
        prev2_vol  = float(prev2.get('wavelet_vol', 0.0) or 0.0)

        avg_prev_vol = (prev_vol + prev2_vol) / 2.0 if (prev_vol + prev2_vol) > 0 else prev_vol

        if avg_prev_vol > 0 and current_vol <= avg_prev_vol * VOL_INCREASE_MULT:
            return None, last_signal_time

        # Movimiento de precio
        price_change = float(curr['close'] - prev['close'])
        two_period_change = float(curr['close'] - prev2['close'])

        if signal_direction == 1:
            ok_price = (price_change > MIN_PRICE_MOVE) or (two_period_change > MIN_PRICE_MOVE)
        else:
            ok_price = (price_change < -MIN_PRICE_MOVE) or (two_period_change < -MIN_PRICE_MOVE)

        if not ok_price:
            return None, last_signal_time

        # Señal válida
        signal_info = {
            'timestamp': full_data.index[i].strftime('%Y.%m.%d %H:%M'),
            'price': round(curr['close'], 5),
            'regime': current_label,
            'regime_state': int(state_i),
            'strategy_used': strategy,
            'signal': int(signal_direction),
            'volatility': round(current_vol, 6),
            'noise_level': round(float(curr.get('noise_level', np.nan) or 0.0), 6),
            'trend_deviation': round(float(curr.get('trend_strength', np.nan) or 0.0), 6),
            'prev_regime': prev_labels[-1] if prev_labels else None
        }

        logger.info(f"SEÑAL GENERADA -> {signal_info['timestamp']} | {signal_info['prev_regime']} -> {signal_info['regime']} | {signal_info['strategy_used']}")
        return signal_info, full_data.index[i]

    except Exception as e:
        logger.error(f"Error generando señal: {e}")
        return None, last_signal_time



model_data = {
    'model': None,
    'scaler': None, 
    'state_info': None,
    'features': ['log_returns', 'wavelet_vol', 'autocorr_5', 'trend_strength', 'range'],
    'last_training_time': None,
    'training_samples': 0
}

def load_model(MODEL_FILE):
    """Carga el modelo desde archivo si existe"""
    global model_data
    
    if not os.path.exists(MODEL_FILE):
        logger.error("No se encontró archivo de modelo")
        return False
    
    try:
        loaded_data = joblib.load(MODEL_FILE)
        
        model_data['model'] = loaded_data['model']
        model_data['scaler'] = loaded_data['scaler']
        model_data['state_info'] = loaded_data['state_info']
        model_data['features'] = loaded_data['features']
        model_data['last_training_time'] = loaded_data['last_training_time']
        model_data['training_samples'] = loaded_data['training_samples']
        
        #print(f"Modelo cargado. Entrenado el {model_data['last_training_time']} con {model_data['training_samples']} muestras")
        return model_data
    except Exception as e:
        print(f"Error cargando modelo: {e}")
        return False


# ----------------------- Configuración CORREGIDA -----------------------
SYMBOLS = ["EURGBP", "EURUSD", "EURJPY", "EURCHF", "EURAUD"]
Z_SCORE_THRESHOLD = 1.8
COOLDOWN_HOURS = 10
ROLLING_WINDOW = 1000  # Para z-score
FEATURE_WINDOW = 500   # Para features ML
ML_CONFIDENCE_THRESHOLD = 0.55

# ✅ CORREGIDO: Mínimo de datos para tiempo real
MIN_DATA_NEEDED = max(ROLLING_WINDOW, FEATURE_WINDOW) + 100  # ~1100 velas

# Variables globales para el estado (EXACTAMENTE como tu ejemplo)
last_trained_model2 = None
last_trained_scaler2 = None  
last_pca_data2 = None
last_signal_time2 = None
last_training_time2 = None

MODEL_FILE_PCA = 'pca_model_EURGBP_20251019_1432.pkl'

# ----------------------- Funciones auxiliares -----------------------
def _calculate_hurst_exponent(ts):
    """Calcula el exponente de Hurst de forma robusta"""
    if len(ts) < 100:
        return np.nan
    try:
        lags = range(2, min(50, len(ts)//4))
        tau = [np.std(np.subtract(ts[lag:], ts[:-lag])) for lag in lags]
        if len(tau) < 2:
            return np.nan
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        return poly[0]
    except:
        return np.nan

def _calculate_eigenvalue_ratio(corr_matrix):
    """Calcula ratio de eigenvalues de forma segura"""
    if corr_matrix.isna().any().any() or len(corr_matrix) < 2:
        return np.nan
    try:
        eigenvalues = np.linalg.eigvals(corr_matrix)
        eigenvalues = np.sort(eigenvalues)[::-1]
        if len(eigenvalues) > 1 and eigenvalues[1] != 0:
            return eigenvalues[0] / eigenvalues[1]
    except:
        pass
    return np.nan

def extract_advanced_features_safe(df_prices, current_idx, feature_window=500):
    """Extrae features SIN look-ahead bias"""
    if current_idx <= feature_window:
        return {}
    
    start_idx = current_idx - feature_window
    end_idx = current_idx
    
    window_data = df_prices.iloc[start_idx:end_idx]
    
    if len(window_data) < 100:
        return {}
    
    features = {}
    
    try:
        returns = window_data.pct_change().dropna()
        
        if len(returns) < 50:
            return {}
        
        portfolio_returns = returns.mean(axis=1)
        
        features['hurst_exponent'] = _calculate_hurst_exponent(portfolio_returns.values)
        
        corr_matrix = returns.corr()
        features['eigenvalue_ratio'] = _calculate_eigenvalue_ratio(corr_matrix)
        
        features['volatility_regime'] = returns.std().mean()
        features['correlation_regime'] = corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean()
        
        if len(returns) > 100:
            var_short = returns.tail(50).var().mean()
            var_long = returns.var().mean()
            features['variance_ratio'] = var_short / var_long if var_long != 0 else np.nan
        else:
            features['variance_ratio'] = np.nan
            
    except Exception as e:
        for feature in ['hurst_exponent', 'eigenvalue_ratio', 'volatility_regime', 
                       'correlation_regime', 'variance_ratio']:
            features[feature] = np.nan
    
    return features

def prepare_ml_features(pca_signal, advanced_features, timestamp):
    """Prepara features para el modelo ML (igual que tu estructura)"""
    features = {
        'z_score_abs': abs(pca_signal['z_score']),
        'z_score_raw': pca_signal['z_score'],
        'training_window_size': pca_signal['training_window_size'],
        'trend_deviation': pca_signal['trend_deviation'],
        'volatility': pca_signal['volatility'],
        'hurst_exponent': advanced_features.get('hurst_exponent', 0),
        'eigenvalue_ratio': advanced_features.get('eigenvalue_ratio', 0),
        'volatility_regime': advanced_features.get('volatility_regime', 0),
        'correlation_regime': advanced_features.get('correlation_regime', 0),
        'variance_ratio': advanced_features.get('variance_ratio', 0),
    }
    return features

def predict_ml_confidence(pca_signal, advanced_features, timestamp, ml_model):
    """Predice confianza de señal usando modelo ML"""
    if ml_model is None:
        return 0.5
    
    try:
        features = prepare_ml_features(pca_signal, advanced_features, timestamp)
        features_array = np.array([list(features.values())])
        confidence = ml_model.predict_proba(features_array)[0][1]
        return confidence
    except Exception as e:
        return 0.5

def load_pca_ml_model():
    """Carga el modelo PCA+ML con la estructura correcta"""
    global last_trained_model2, last_pca_data2, last_training_time2
    
    if not os.path.exists(MODEL_FILE_PCA):
        print("No se encontró archivo de modelo PCA+ML")
        return False
    
    try:
        loaded_data = joblib.load(MODEL_FILE_PCA)
        
        # Cargar con la estructura REAL del archivo
        last_trained_model2 = loaded_data['ml_model']
        last_pca_data2 = {
            'pca': loaded_data['pca'],           # ← Se llama 'pca' en el archivo
            'scaler': loaded_data['scaler']      # ← También necesitas el scaler
        }
        last_training_time2 = loaded_data['last_training_time']
        
        return {
            'model': last_trained_model2,
            'pca_data': last_pca_data2,  # ← Ahora contiene tanto 'pca' como 'scaler'
            'last_training_time': last_training_time2
        }
    except Exception as e:
        print(f"Error cargando modelo PCA+ML: {e}")
        return False

def generate_pca_ml_signal_realtime(df_prices, pca_data, ml_model, last_signal_time=None):
    """
    Versión para tiempo real CORREGIDA - sin requisito de 5000 velas
    Devuelve UNA sola señal (o None) - EXACTAMENTE como tu función
    """
    
    if pca_data is None or ml_model is None:
        return None, last_signal_time2
    
    scaler, pca = pca_data['scaler'], pca_data['pca']
    
    # ✅ CORREGIDO: Solo necesitamos ~1100 velas, no 5000
    if len(df_prices) < MIN_DATA_NEEDED:
        print(f"Datos insuficientes: {len(df_prices)} < {MIN_DATA_NEEDED}")
        return None, last_signal_time2
    
    # Solo analizamos la vela más reciente
    i = len(df_prices) - 1
    timestamp = df_prices.index[i]
    
    # Cooldown check (igual que tu implementación)
    if last_signal_time2 is not None and (timestamp - last_signal_time2) < timedelta(hours=COOLDOWN_HOURS):
        return None, last_signal_time2
    
    try:
        # ✅ CORREGIDO: Ventana más pequeña solo para z-score (1000 velas, no 5000)
        window_start = max(0, i - ROLLING_WINDOW)
        apply_window = df_prices.iloc[window_start:i+1]
        
        # Aplicar PCA pre-entrenado
        scaled_apply = scaler.transform(apply_window)
        factor = scaled_apply @ pca.components_.T
        residuals = scaled_apply - factor * pca.components_
        current_residual = residuals[-1, 0]
        
        # Calcular z-score (excluyendo punto actual)
        residual_series = pd.Series(residuals[:-1, 0])
        if len(residual_series) > ROLLING_WINDOW:
            rolling_data = residual_series.tail(ROLLING_WINDOW)
            spread_mean, spread_std = rolling_data.mean(), rolling_data.std()
        else:
            spread_mean, spread_std = residual_series.mean(), residual_series.std()
        
        if spread_std == 0 or np.isnan(spread_std):
            return None, last_signal_time2
            
        z_score = (current_residual - spread_mean) / spread_std
        
        # Generar señal base
        if z_score > Z_SCORE_THRESHOLD:
            signal = -1
            strategy = 'PCA_RESIDUAL_BEAR'
        elif z_score < -Z_SCORE_THRESHOLD:
            signal = 1  
            strategy = 'PCA_RESIDUAL_BULL'
        else:
            return None, last_signal_time2
        
        # Features avanzadas para ML
        advanced_features = extract_advanced_features_safe(df_prices, i, FEATURE_WINDOW)
        
        # Filtrar con ML
        ml_confidence = predict_ml_confidence(
            {
                'z_score': z_score,
                'training_window_size': len(apply_window),
                'trend_deviation': current_residual,
                'volatility': float(df_prices.iloc[i].pct_change().std() if i > 1 else 0.0)
            },
            advanced_features,
            timestamp,
            ml_model
        )
        
        if ml_confidence < ML_CONFIDENCE_THRESHOLD:
            return None, last_signal_time2
        
        # Señal válida
        signal_info = {
            'timestamp': timestamp.strftime('%Y.%m.%d %H:%M'),
            'price': round(df_prices.iloc[i, 0], 5),
            'regime': 'RESIDUAL_EXTREME',
            'regime_state': 0,
            'strategy_used': strategy,
            'signal': signal,
            'volatility': round(float(df_prices.iloc[i].pct_change().std() if i > 1 else 0.0), 6),
            'noise_level': 0.0,
            'trend_deviation': round(float(current_residual), 6),
            'z_score': round(z_score, 3),
            'ml_confidence': round(ml_confidence, 3),
            'training_window_size': len(apply_window),
            'hurst_exponent': round(advanced_features.get('hurst_exponent', 0), 4),
            'eigenvalue_ratio': round(advanced_features.get('eigenvalue_ratio', 0), 4),
            'volatility_regime': round(advanced_features.get('volatility_regime', 0), 4),
            'correlation_regime': round(advanced_features.get('correlation_regime', 0), 4),
            'variance_ratio': round(advanced_features.get('variance_ratio', 0), 4)
        }
        
        print(f"SEÑAL PCA+ML GENERADA -> {signal_info['timestamp']} | {signal_info['strategy_used']} | Z: {signal_info['z_score']:.2f} | ML: {ml_confidence:.3f}")
        return signal_info, timestamp
        
    except Exception as e:
        print(f"Error generando señal PCA+ML: {e}")
        return None, last_signal_time2