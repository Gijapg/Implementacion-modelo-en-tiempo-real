import pandas as pd
from logica_bot.safe_operations import *
from logica_bot.ORDENES import *
from logica_bot.auxiliar import*

import logging

logger = logging.getLogger(__name__)


def Wavelet_HMM_Strategy(df, symbol, MODEL_FILE, wavelet_window, wavelet_level, wavelet_type, consolidation_required):

    global last_signal_time

    magic = 5555555555
    trade_comment = 'Wavelet HMM Strategy'
    risk_percent = 1.0

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    df_closed = df.iloc[:-1].copy() 

    if len(df_closed) < 1000:
        logger.error(f"Datos insuficientes para features: {len(df_closed)} velas")
        return

    model_loaded = load_model(MODEL_FILE)

    df_basic = calculate_basic_features(df_closed)
    df_with_features = calculate_trend_and_wavelet_features(df_basic, wavelet_window, wavelet_level, wavelet_type)

    required_features = ['log_returns', 'wavelet_vol', 'autocorr_5', 'trend_strength', 'range']
    for feat in required_features:
        if feat not in df_with_features.columns:
            logger.error(f"Error: Falta columnas feature {feat}")
            return
 
    if not model_loaded:
        logger.error('ETRENAMIENTO NECESARIO, entrenar de forma independiente')
    
    signal, last_signal_time = generate_transition_signal_realtime(
        symbol,
        df_with_features,  
        model_loaded['state_info'],      
        model_loaded['model'],          
        model_loaded['scaler'],         
        consolidation_required,
        last_signal_time
    )

    if signal is not None:
        direction = "BUY" if signal['signal'] == 1 else "SELL"
        
        atr = calcular_atr(df, 14)
        price = df['close'].iloc[-1]

        if symbol == 'USDJPY':
            if direction == "BUY":
                sl = price - atr * 3
                tp = price + atr * 9
            else:
                sl = price + atr * 3
                tp = price - atr * 9
        
        elif symbol == 'EURUSD':
            if direction == "BUY":
                sl = price - atr * 2
                tp = price + atr * 8
            else:
                sl = price + atr * 2
                tp = price - atr * 8
        
        send_om(symbol, direction, sl, tp, magic, trade_comment, risk_percent)
        
        logger.info(f"SEÑAL EJECUTADA: {direction} | Precio: {price:.5f}")
        logger.info(f"Regimen: {signal['regime']} | SL: {sl:.5f}, TP: {tp:.5f}")


last_signal_time2 = None

def PCA_ML_Strategy(df, symbol):

    global last_signal_time2

    magic = 6666666666
    trade_comment = 'PCA ML Strategy'
    risk_percent = 1.0

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    df_closed = df.iloc[:-1].copy()  

    if len(df_closed) < MIN_DATA_NEEDED:
        print(f"Datos insuficientes para PCA+ML: {len(df_closed)} < {MIN_DATA_NEEDED} velas")
        return

    model_loaded = load_pca_ml_model()
    
    if not model_loaded:
        print('MODELO PCA+ML NO ENCONTRADO, entrenar de forma independiente')
        return

    signal, last_signal_time2 = generate_pca_ml_signal_realtime(
        df_closed,  
        model_loaded['pca_data'],      
        model_loaded['model'],           
        last_signal_time
    )
 
    if signal is not None:
        direction = "BUY" if signal['signal'] == 1 else "SELL"
        
        atr = calcular_atr(df, 14)
        price = signal['price']
        
        if direction == "BUY":
            sl = price - atr * 2
            tp = price + atr * 6
        else:
            sl = price + atr * 2
            tp = price - atr * 6
        
        send_om(symbol, direction, sl, tp, magic, trade_comment, risk_percent)
        
        print(f"SEÑAL PCA+ML EJECUTADA: {direction} | Precio: {price:.5f}")
        print(f"Z-score: {signal['z_score']:.2f} | Confianza ML: {signal['ml_confidence']:.3f} | SL: {sl:.5f}, TP: {tp:.5f}")