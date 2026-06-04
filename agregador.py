class AgregadorCandle:
    """Agregador de candles com base em intervalo de tempo configurável.
    
    Recebe trades em tempo real e os agrega em candles baseado no intervalo.
    
    Formato de candle:
        [idx, open, high, low, close, ...]
    
    Attributes:
        intervalo_ms: Intervalo de agregação em milissegundos
        candles: Lista de candles agregados
        ultimo_tempo: Timestamp do último trade processado (em segundos)
    """
    
    def __init__(self, intervalo_ms=1000):
        """Inicializa o agregador.
        
        Args:
            intervalo_ms: Intervalo de agregação em milissegundos (padrão: 1000ms = 1s)
        """
        self.intervalo_ms = intervalo_ms
        self.candles = []
        self.ultimo_tempo = None  # em SEGUNDOS (epoch unix)

    def set_historico(self, dados):
        """Define histórico inicial de candles.
        
        Args:
            dados: Lista de candles no formato [idx, open, high, low, close, ...]
        """
        self.candles = dados
        if dados:
            self.ultimo_tempo = dados[-1][0]  # assume que índice 0 é timestamp

    def processar_trade(self, preco, timestamp):
        """Processa um trade em tempo real.
        
        Args:
            preco: Preço do trade
            timestamp: Timestamp em SEGUNDOS (epoch unix)
        """
        if not self.candles:
            # Primeiro trade: inicializa o primeiro candle
            self.ultimo_tempo = timestamp
            self.candles.append([0, preco, preco, preco, preco])
            return

        ultimo = self.candles[-1]

        # Atualiza High, Low, Close do candle atual
        ultimo[2] = max(ultimo[2], preco)  # High
        ultimo[3] = min(ultimo[3], preco)  # Low
        ultimo[4] = preco                   # Close

        # ✅ CORRIGIDO: Conversão correta de timestamp
        # timestamp está em SEGUNDOS, intervalo_ms está em MILISSEGUNDOS
        tempo_decorrido_ms = (timestamp - self.ultimo_tempo) * 1000
        
        if tempo_decorrido_ms >= self.intervalo_ms:
            # Tempo suficiente para novo candle
            self.ultimo_tempo = timestamp
            idx = ultimo[0] + 1
            self.candles.append([idx, preco, preco, preco, preco])

    def get_candles(self):
        """Retorna lista de candles agregados.
        
        Returns:
            Lista de candles no formato [idx, open, high, low, close, ...]
        """
        return self.candles
