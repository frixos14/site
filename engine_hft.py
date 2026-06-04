import logging
import threading
import queue
import time
from typing import Dict, List, Optional

from binance_ws import BinanceWS
from historico_binance import carregar_historico


logger = logging.getLogger(__name__)


INTERVALOS_MS: Dict[str, int] = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "6h": 6 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "3d": 3 * 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
    "1M": 30 * 24 * 60 * 60_000,  # aproximação para bucket visual; REST usa calendário.
}


class EngineHFT:
    """Engine HFT (viewer) com timeframe configurável.

    - Carrega histórico via /api/v3/klines com interval = timeframe.
    - Atualiza candle em tempo real via trades (@trade) agregando no bucket do timeframe.

    Formato candle interno:
        [idx, open, high, low, close, volume, open_time_ms]
    """

    def __init__(self, symbol: str, timeframe: str = "1m", historico_limite: int = 500):
        # configura atributos essenciais primeiro
        self.symbol = symbol
        self.timeframe = timeframe
        self.intervalo_ms = self._intervalo_ms(timeframe)
        self.historico_limite = int(historico_limite)

        # sincronização / filas
        self._lock = threading.Lock()
        self.queue: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()

        # estado de candles
        self.candles: List[list] = []
        self.last_bucket: Optional[int] = None

        # carrega histórico inicial
        try:
            self._carregar_historico()
        except Exception:
            # não falhar na construção; log e seguir com lista vazia
            logger.exception("Falha ao carregar histórico inicial")
            self.candles = []
            self.last_bucket = None

        # websocket público de trades
        # BinanceWS espera symbol em lower() e callback (price, qty, ts_s)
        self.ws = BinanceWS(self.symbol.lower(), self.on_trade)
        self.ws.start()

        # thread principal de processamento
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    # ────────────────────────────────────────────────────────────────
    def _intervalo_ms(self, tf: str) -> int:
        if tf not in INTERVALOS_MS:
            raise ValueError(f"Timeframe inválido: {tf}")
        return int(INTERVALOS_MS[tf])

    def _carregar_historico(self):
        """Carrega klines via historico_binance.carregar_historico.

        Atualiza self.candles e self.last_bucket de forma thread-safe.
        """
        # chamada blocking para REST
        candles = carregar_historico(self.symbol.upper(), intervalo=self.timeframe, limit=self.historico_limite)
        with self._lock:
            self.candles = candles or []
            if self.candles:
                # open_time_ms está no índice 6 (ver historico_binance.py)
                self.last_bucket = int(self.candles[-1][6] // self.intervalo_ms) if self.intervalo_ms else None
            else:
                self.last_bucket = None

    # ────────────────────────────────────────────────────────────────
    def set_timeframe(self, timeframe: str):
        """Troca timeframe e recarrega histórico.

        Mantém tudo coerente com a API: histórico e agregação em tempo real usam o mesmo timeframe.
        """
        # valida e aplica
        self.timeframe = timeframe
        self.intervalo_ms = self._intervalo_ms(timeframe)

        # recarrega histórico (bloqueante)
        try:
            self._carregar_historico()
        except Exception:
            logger.exception("Erro ao recarregar histórico para novo timeframe")

    def stop(self):
        """Encerra o engine e o websocket."""
        self._stop.set()
        try:
            if self.ws:
                self.ws.stop()
        except Exception:
            logger.exception("Erro ao parar websocket")

        try:
            if self._thread.is_alive():
                # se a thread estiver em blocking get, liberamos colocando None
                try:
                    self.queue.put_nowait((None, None, None))
                except Exception:
                    pass
                self._thread.join(timeout=1.0)
        except Exception:
            logger.exception("Erro ao aguardar thread do engine")

    # ────────────────────────────────────────────────────────────────
    def on_trade(self, price: float, qty: float, ts_s: float):
        """Callback do BinanceWS: recebe timestamp em segundos.

        Converte para ms e enfileira para processamento na thread do engine.
        """
        try:
            ts_ms = int(ts_s * 1000)
        except Exception:
            # proteção caso ts_s seja inválido
            ts_ms = int(time.time() * 1000)
        self.queue.put((float(price), float(qty), int(ts_ms)))

    def run(self):
        """Loop principal que consome a fila de trades e agrega candles."""
        while not self._stop.is_set():
            try:
                price, qty, ts_ms = self.queue.get(timeout=0.5)
                # protocolo de parada (enqueued by stop)
                if price is None and qty is None and ts_ms is None:
                    break
                self.process(price, qty, ts_ms)
            except queue.Empty:
                continue
            except Exception:
                logger.exception("Erro no loop principal do EngineHFT")

    def process(self, price: float, qty: float, ts_ms: int):
        """Agrega trade em candles de acordo com self.intervalo_ms."""
        if self.intervalo_ms <= 0:
            return

        bucket = int(ts_ms // self.intervalo_ms)

        with self._lock:
            # se não houver candles ou bucket mudou: cria novo candle
            if not self.candles or self.last_bucket != bucket:
                idx = self.candles[-1][0] + 1 if self.candles else 0
                open_time_ms = bucket * self.intervalo_ms
                # candle: [idx, open, high, low, close, volume, open_time_ms]
                self.candles.append([idx, price, price, price, price, float(qty), open_time_ms])
                self.last_bucket = bucket

                # mantém limite do histórico em memória
                if len(self.candles) > self.historico_limite:
                    # remove do início
                    excess = len(self.candles) - self.historico_limite
                    del self.candles[0:excess]
                return

            # atualiza candle atual
            c = self.candles[-1]
            c[2] = max(c[2], price)  # high
            c[3] = min(c[3], price)  # low
            c[4] = price             # close
            c[5] = float(c[5]) + float(qty)  # volume

    def get_snapshot(self, n: int = 300) -> List[list]:
        """Retorna uma cópia dos últimos n candles (thread-safe)."""
        with self._lock:
            if not self.candles:
                return []
            n = max(1, int(n))
            return [row.copy() for row in self.candles[-n:]]
