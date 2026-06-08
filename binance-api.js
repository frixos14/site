/**
 * Binance API Integration for TradingView
 * Este arquivo gerencia a conexão com a API Binance e fornece dados em tempo real
 */

class BinanceAPI {
  constructor() {
    this.baseURL = 'https://api.binance.com/api/v3';
    this.wsURL = 'wss://stream.binance.com:9443/ws';
    this.websocket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 3000;
  }

  /**
   * Obter informações do símbolo (par de trading)
   * @param {string} symbol - Símbolo do par (ex: BTCUSDT)
   * @returns {Promise<object>} Dados do símbolo
   */
  async getSymbolInfo(symbol) {
    try {
      const response = await fetch(`${this.baseURL}/exchangeInfo?symbol=${symbol}`);
      const data = await response.json();
      return data.symbols[0];
    } catch (error) {
      console.error('Erro ao obter informações do símbolo:', error);
      throw error;
    }
  }

  /**
   * Obter preço atual de um símbolo
   * @param {string} symbol - Símbolo do par
   * @returns {Promise<object>} Dados de preço
   */
  async getCurrentPrice(symbol) {
    try {
      const response = await fetch(`${this.baseURL}/ticker/price?symbol=${symbol}`);
      const data = await response.json();
      return {
        symbol: data.symbol,
        price: parseFloat(data.price),
        timestamp: Date.now()
      };
    } catch (error) {
      console.error('Erro ao obter preço atual:', error);
      throw error;
    }
  }

  /**
   * Obter dados de candlestick (OHLCV)
   * @param {string} symbol - Símbolo do par
   * @param {string} interval - Intervalo (1m, 5m, 15m, 1h, 4h, 1d, etc)
   * @param {number} limit - Número de candles a retornar (padrão: 100)
   * @returns {Promise<array>} Array de candlesticks
   */
  async getCandles(symbol, interval = '1h', limit = 100) {
    try {
      const response = await fetch(
        `${this.baseURL}/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`
      );
      const data = await response.json();
      
      return data.map(candle => ({
        time: Math.floor(candle[0] / 1000), // timestamp em segundos
        open: parseFloat(candle[1]),
        high: parseFloat(candle[2]),
        low: parseFloat(candle[3]),
        close: parseFloat(candle[4]),
        volume: parseFloat(candle[7]),
        quoteAssetVolume: parseFloat(candle[8]),
        trades: parseInt(candle[8])
      }));
    } catch (error) {
      console.error('Erro ao obter candles:', error);
      throw error;
    }
  }

  /**
   * Obter estatísticas 24h
   * @param {string} symbol - Símbolo do par
   * @returns {Promise<object>} Estatísticas 24h
   */
  async get24hStats(symbol) {
    try {
      const response = await fetch(`${this.baseURL}/ticker/24hr?symbol=${symbol}`);
      const data = await response.json();
      
      return {
        symbol: data.symbol,
        priceChange: parseFloat(data.priceChange),
        priceChangePercent: parseFloat(data.priceChangePercent),
        highPrice: parseFloat(data.highPrice),
        lowPrice: parseFloat(data.lowPrice),
        lastPrice: parseFloat(data.lastPrice),
        volume: parseFloat(data.volume),
        quoteVolume: parseFloat(data.quoteVolume),
        openTime: data.openTime,
        closeTime: data.closeTime
      };
    } catch (error) {
      console.error('Erro ao obter estatísticas 24h:', error);
      throw error;
    }
  }

  /**
   * Conectar ao WebSocket para stream de preços em tempo real
   * @param {string} symbol - Símbolo do par
   * @param {function} callback - Função de callback para processar dados
   */
  connectPriceStream(symbol, callback) {
    const streamName = `${symbol.toLowerCase()}@ticker`;
    const wsUrl = `${this.wsURL}/${streamName}`;

    try {
      this.websocket = new WebSocket(wsUrl);

      this.websocket.onopen = () => {
        console.log(`✓ Conectado ao stream: ${symbol}`);
        this.reconnectAttempts = 0;
      };

      this.websocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        callback({
          symbol: data.s,
          price: parseFloat(data.c),
          priceChange: parseFloat(data.p),
          priceChangePercent: parseFloat(data.P),
          highPrice: parseFloat(data.h),
          lowPrice: parseFloat(data.l),
          volume: parseFloat(data.v),
          timestamp: data.E
        });
      };

      this.websocket.onerror = (error) => {
        console.error('Erro no WebSocket:', error);
      };

      this.websocket.onclose = () => {
        console.log('Conexão WebSocket fechada');
        this.attemptReconnect(symbol, callback);
      };
    } catch (error) {
      console.error('Erro ao conectar ao WebSocket:', error);
      this.attemptReconnect(symbol, callback);
    }
  }

  /**
   * Stream de candles em tempo real (klines)
   * @param {string} symbol - Símbolo do par
   * @param {string} interval - Intervalo (1m, 5m, 15m, 1h, etc)
   * @param {function} callback - Função de callback
   */
  connectCandleStream(symbol, interval = '1m', callback) {
    const streamName = `${symbol.toLowerCase()}@kline_${interval}`;
    const wsUrl = `${this.wsURL}/${streamName}`;

    try {
      this.websocket = new WebSocket(wsUrl);

      this.websocket.onopen = () => {
        console.log(`✓ Conectado ao stream de candles: ${symbol} ${interval}`);
        this.reconnectAttempts = 0;
      };

      this.websocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const candle = data.k;
        
        callback({
          symbol: data.s,
          interval: interval,
          time: Math.floor(candle.t / 1000),
          open: parseFloat(candle.o),
          high: parseFloat(candle.h),
          low: parseFloat(candle.l),
          close: parseFloat(candle.c),
          volume: parseFloat(candle.v),
          quoteVolume: parseFloat(candle.q),
          isClosed: candle.x,
          timestamp: candle.T
        });
      };

      this.websocket.onerror = (error) => {
        console.error('Erro no WebSocket de candles:', error);
      };

      this.websocket.onclose = () => {
        console.log('Conexão WebSocket de candles fechada');
        this.attemptReconnect(symbol, callback, interval, true);
      };
    } catch (error) {
      console.error('Erro ao conectar ao WebSocket de candles:', error);
      this.attemptReconnect(symbol, callback, interval, true);
    }
  }

  /**
   * Tentar reconectar ao WebSocket
   * @private
   */
  attemptReconnect(symbol, callback, interval = null, isCandle = false) {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Tentando reconectar... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
      
      setTimeout(() => {
        if (isCandle) {
          this.connectCandleStream(symbol, interval, callback);
        } else {
          this.connectPriceStream(symbol, callback);
        }
      }, this.reconnectDelay);
    } else {
      console.error('Falha ao reconectar após múltiplas tentativas');
    }
  }

  /**
   * Desconectar do WebSocket
   */
  disconnect() {
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
      console.log('Desconectado do stream WebSocket');
    }
  }

  /**
   * Obter múltiplos símbolos (top pares)
   * @returns {Promise<array>} Lista de pares populares
   */
  async getTopPairs() {
    try {
      const response = await fetch(`${this.baseURL}/ticker/24hr?limit=20`);
      const data = await response.json();
      
      return data
        .filter(pair => pair.symbol.endsWith('USDT'))
        .map(pair => ({
          symbol: pair.symbol,
          price: parseFloat(pair.lastPrice),
          change24h: parseFloat(pair.priceChangePercent),
          volume: parseFloat(pair.quoteVolume)
        }));
    } catch (error) {
      console.error('Erro ao obter pares top:', error);
      throw error;
    }
  }
}

// Exportar para uso em outros arquivos
if (typeof module !== 'undefined' && module.exports) {
  module.exports = BinanceAPI;
}
