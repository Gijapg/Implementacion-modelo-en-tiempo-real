from logica_bot.ORDENES import *
from logica_bot.safe_operations import *
from backend_14 import get_candle_data
from logica_bot.estrategias import *


def logica_bot(symbol, candles_data):

    #check_pending_orders_tp(symbol)
    #monitor_positions()

    df_candles = pd.DataFrame(candles_data)
    df_candles['Date'] = pd.to_datetime(df_candles.index)
    df_candles.set_index('Date', inplace=True)
    df_candles.index.name = 'Date'

    if (symbol == 'USDJPY'):
        candles_data2 = get_candle_data(symbol, mt5.TIMEFRAME_H1, 1010)

        # Convertir a DataFrame (asegurando que las columnas estén en el orden correcto)
        df_candles2 = pd.DataFrame(
            candles_data2,
            columns=['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
        )

        # Convertir la columna 'time' (timestamp UNIX) a datetime y establecerla como índice
        df_candles2['Date'] = pd.to_datetime(df_candles2['time'], unit='s')  # ¡Clave: unit='s'!
        df_candles2.set_index('Date', inplace=True)

        # Eliminar la columna 'time' original (opcional)
        df_candles2.drop('time', axis=1, inplace=True)
        #print(df_candles2.head())

        #Donchian_strategy(df_candles2, symbol)
        
        Wavelet_HMM_Strategy(df_candles2, symbol, MODEL_FILE = f'wavelet_hmm_model_USDJPY_20260130_2234.pkl', wavelet_window=12, wavelet_level=2, wavelet_type='db4', consolidation_required=1)
    
    elif (symbol == 'GBPJPY'):
        candles_data2 = get_candle_data(symbol, mt5.TIMEFRAME_H1, 180)

        # Convertir a DataFrame (asegurando que las columnas estén en el orden correcto)
        df_candles2 = pd.DataFrame(
            candles_data2,
            columns=['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
        )

        # Convertir la columna 'time' (timestamp UNIX) a datetime y establecerla como índice
        df_candles2['Date'] = pd.to_datetime(df_candles2['time'], unit='s')  # ¡Clave: unit='s'!
        df_candles2.set_index('Date', inplace=True)

        # Eliminar la columna 'time' original (opcional)
        df_candles2.drop('time', axis=1, inplace=True)

        #if get_spread(symbol):
            #Pivot_strategy(df_candles2, symbol)
            #Vwap_Strategy(df_candles2, symbol)


    elif (symbol == 'EURUSD'):
        candles_data2 = get_candle_data(symbol, mt5.TIMEFRAME_H1, 1010)

        # Convertir a DataFrame (asegurando que las columnas estén en el orden correcto)
        df_candles2 = pd.DataFrame(
            candles_data2,
            columns=['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
        )

        # Convertir la columna 'time' (timestamp UNIX) a datetime y establecerla como índice
        df_candles2['Date'] = pd.to_datetime(df_candles2['time'], unit='s')  # ¡Clave: unit='s'!
        df_candles2.set_index('Date', inplace=True)

        # Eliminar la columna 'time' original (opcional)
        df_candles2.drop('time', axis=1, inplace=True)


        #Donchian_strategy(df_candles2, symbol)

        #MonteCarlo_Strategy(df_candles2, symbol)
        Wavelet_HMM_Strategy(df_candles2, symbol, MODEL_FILE = f'wavelet_hmm_model_EURUSD_20251221_1417.pkl', wavelet_window=16, wavelet_level=3, wavelet_type='sym4', consolidation_required=3)
        #Regime_HMM_Strategy(df_candles2, symbol)

    elif (symbol == 'EURGBP'):

        # ✅ NUEVO: Estrategia PCA+ML para múltiples símbolos
        """symbols_pca_ml = ["EURGBP", "EURUSD", "EURJPY", "EURCHF", "EURAUD"]
        if symbol in symbols_pca_ml:
            # Obtener datos para TODOS los símbolos PCA+ML
            dfs_symbols = []
            
            for sym in symbols_pca_ml:
                candles_data = get_candle_data(sym, mt5.TIMEFRAME_H1, 1200)
                
                df_sym = pd.DataFrame(
                    candles_data,
                    columns=['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
                )
                
                df_sym['Date'] = pd.to_datetime(df_sym['time'], unit='s')
                df_sym.set_index('Date', inplace=True)
                df_sym.drop('time', axis=1, inplace=True)
                
                dfs_symbols.append(df_sym[['close']])
            
            # Combinar todos los símbolos
            df_multi = pd.concat(dfs_symbols, axis=1)
            df_multi.columns = symbols_pca_ml
            df_multi.dropna(inplace=True)
            
            #print(f"Datos PCA+ML: {df_multi.shape}")
            
            # Ejecutar estrategia PCA+ML
            if len(df_multi) >= 1100:
                PCA_ML_Strategy(df_multi, symbol)"""

        candles_data2 = get_candle_data(symbol, mt5.TIMEFRAME_H1, 1010)

        # Convertir a DataFrame (asegurando que las columnas estén en el orden correcto)
        df_candles2 = pd.DataFrame(
            candles_data2,
            columns=['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
        )

        # Convertir la columna 'time' (timestamp UNIX) a datetime y establecerla como índice
        df_candles2['Date'] = pd.to_datetime(df_candles2['time'], unit='s')  # ¡Clave: unit='s'!
        df_candles2.set_index('Date', inplace=True)

        # Eliminar la columna 'time' original (opcional)
        df_candles2.drop('time', axis=1, inplace=True)

        Wavelet_HMM_Strategy(df_candles2, symbol, MODEL_FILE = f'wavelet_hmm_model_EURGBP_20251105_2042.pkl')
            
            
    

