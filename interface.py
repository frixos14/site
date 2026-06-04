from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any

from PyQt5 import QtWidgets, QtCore

from grafico import GraficoWidget
from engine_hft import EngineHFT
from binance_ws import BinanceInfo


TIMEFRAMES = [
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
]

# Fase 1 - tipos simples Spot
TIPOS_ORDEM = [
    "LIMIT",
    "MARKET",
    "STOP_LOSS",
    "STOP_LOSS_LIMIT",
    "TAKE_PROFIT",
    "TAKE_PROFIT_LIMIT",
    "LIMIT_MAKER",
]
TIME_IN_FORCE = ["GTC", "IOC", "FOK"]

# Paleta visual
BG = "#0d0f14"
PANEL = "#12151c"
PANEL_2 = "#161b24"
BORDER = "#262b36"
TEXT = "#e8eaf0"
DIM = "#7f8694"
GREEN = "#00e676"
GREEN_HOVER = "#14f18a"
RED = "#ff3d5a"
RED_HOVER = "#ff5a73"
BLUE = "#4da3ff"
BTN = "#1c2230"
BTN_HOVER = "#283042"
BTN_PRESSED = "#33405a"


def _d(txt: str, default: str = '0') -> Decimal:
    try:
        return Decimal(str(txt).replace(',', '.').strip())
    except Exception:
        return Decimal(default)


def _qstep(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


class WorkerSimbolos(QtCore.QObject):
    pronto = QtCore.pyqtSignal(list)
    erro = QtCore.pyqtSignal(str)

    def __init__(self, quote: str = "USDT"):
        super().__init__()
        self.quote = quote

    @QtCore.pyqtSlot()
    def executar(self):
        try:
            simbolos = BinanceInfo.listar_simbolos(quote=self.quote, somente_ativos=True, somente_spot=True)
            self.pronto.emit(simbolos)
        except Exception as e:
            self.erro.emit(str(e))


class WorkerRegrasSimbolo(QtCore.QObject):
    pronto = QtCore.pyqtSignal(dict)
    erro = QtCore.pyqtSignal(str)

    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol

    @QtCore.pyqtSlot()
    def executar(self):
        try:
            regras = BinanceInfo.obter_regras_simbolo(self.symbol)
            self.pronto.emit(regras)
        except Exception as e:
            self.erro.emit(str(e))


class DockHandle(QtWidgets.QSplitterHandle):
    def __init__(self, orientation, parent_splitter):
        super().__init__(orientation, parent_splitter)
        self._splitter = parent_splitter
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        self.btn = QtWidgets.QToolButton(self)
        self.btn.setObjectName("btnPainelLateral")
        self.btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn.setCheckable(True)
        self.btn.setChecked(True)
        self.btn.setArrowType(QtCore.Qt.RightArrow)
        self.btn.clicked.connect(self._splitter.toggle_right_panel)
        self.btn.setToolTip("Esconder/mostrar painel de ordens")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        bw, bh = 18, 54
        x = max(0, (self.width() - bw) // 2)
        y = max(0, (self.height() - bh) // 2)
        self.btn.setGeometry(x, y, bw, bh)


class DockableSplitter(QtWidgets.QSplitter):
    painelAlterado = QtCore.pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(QtCore.Qt.Horizontal, parent)
        self._right_visible = True
        self._last_right_width = 360
        self.setHandleWidth(18)
        self.setOpaqueResize(True)
        self.setChildrenCollapsible(True)
        self.setCollapsible(0, False)
        self.setCollapsible(1, True)

    def createHandle(self):
        return DockHandle(self.orientation(), self)

    def toggle_right_panel(self):
        if self.count() < 2:
            return
        sizes = self.sizes()
        if len(sizes) < 2:
            return
        total = max(sum(sizes), 1)
        right = sizes[1]
        if right > 0:
            self._last_right_width = max(right, 280)
            self.setSizes([total, 0])
            self._right_visible = False
        else:
            right = min(max(self._last_right_width, 340), 460)
            left = max(total - right, 220)
            self.setSizes([left, right])
            self._right_visible = True
        self._sync_handle_arrow()
        self.painelAlterado.emit(self._right_visible)

    def _sync_handle_arrow(self):
        handle = self.handle(1)
        if isinstance(handle, DockHandle):
            handle.btn.setChecked(self._right_visible)
            handle.btn.setArrowType(QtCore.Qt.RightArrow if self._right_visible else QtCore.Qt.LeftArrow)
            handle.btn.setToolTip("Esconder painel de ordens" if self._right_visible else "Mostrar painel de ordens")

    def setSizes(self, sizes):
        super().setSizes(sizes)
        current = super().sizes()
        if len(current) >= 2:
            self._right_visible = current[1] > 0
            if self._right_visible:
                self._last_right_width = max(current[1], 280)
            self._sync_handle_arrow()


class JanelaPrincipal(QtWidgets.QMainWindow):
    """Opção A — adaptação da interface atual para Fase 1 (demo segura).

    - Mantém painel lateral dockável
    - Adiciona os tipos Spot da Fase 1
    - Mostra/oculta campos dinamicamente
    - Faz validação local do payload (sem enviar ordem)
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Terminal Binance Testnet • Fase 1 (demo local)")
        self.resize(1540, 940)

        self.engine = None
        self.regras_simbolo: Dict[str, Any] = None
        self._thread_regras = None
        self._worker_regras = None
        self._thread_simbolos = None
        self._worker_simbolos = None

        self._montar_ui()
        self._aplicar_estilos()
        self._iniciar_worker_simbolos()
        self._iniciar_timer_render()

    # ─────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────
    def _montar_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        raiz = QtWidgets.QVBoxLayout(central)
        raiz.setContentsMargins(10, 10, 10, 10)
        raiz.setSpacing(10)

        # topo
        topo = QtWidgets.QFrame()
        topo.setObjectName("barraSuperior")
        topo_layout = QtWidgets.QHBoxLayout(topo)
        topo_layout.setContentsMargins(12, 10, 12, 10)
        topo_layout.setSpacing(10)
        raiz.addWidget(topo)

        topo_layout.addWidget(self._label_topo("Símbolo"))
        self.combo_simbolos = QtWidgets.QComboBox()
        self.combo_simbolos.setEnabled(False)
        self.combo_simbolos.addItem("Carregando símbolos...")
        self.combo_simbolos.currentIndexChanged.connect(self._on_symbol_change)
        topo_layout.addWidget(self.combo_simbolos)

        topo_layout.addWidget(self._label_topo("Timeframe"))
        self.combo_timeframe = QtWidgets.QComboBox()
        self.combo_timeframe.addItems(TIMEFRAMES)
        self.combo_timeframe.setCurrentText("1m")
        self.combo_timeframe.currentTextChanged.connect(self._on_timeframe_change)
        topo_layout.addWidget(self.combo_timeframe)

        self.btn_follow = QtWidgets.QPushButton("FOLLOW")
        self.btn_follow.setObjectName("btnFollow")
        self.btn_follow.setCheckable(True)
        self.btn_follow.setChecked(True)
        self.btn_follow.toggled.connect(self._on_follow_toggled)
        topo_layout.addWidget(self.btn_follow)
        topo_layout.addStretch(1)

        # splitter dockável
        self.splitter = DockableSplitter()
        self.splitter.painelAlterado.connect(self._on_painel_alterado)
        raiz.addWidget(self.splitter, 1)

        self.bloco_grafico = QtWidgets.QFrame()
        self.bloco_grafico.setObjectName("blocoGrafico")
        g_layout = QtWidgets.QVBoxLayout(self.bloco_grafico)
        g_layout.setContentsMargins(0, 0, 0, 0)
        g_layout.setSpacing(0)
        self.grafico = GraficoWidget()
        g_layout.addWidget(self.grafico)
        self.splitter.addWidget(self.bloco_grafico)

        self.painel_ordens = QtWidgets.QFrame()
        self.painel_ordens.setObjectName("painelOrdens")
        self.painel_ordens.setMinimumWidth(0)
        self.painel_ordens.setMaximumWidth(460)
        painel_layout = QtWidgets.QVBoxLayout(self.painel_ordens)
        painel_layout.setContentsMargins(14, 14, 14, 14)
        painel_layout.setSpacing(12)
        self.splitter.addWidget(self.painel_ordens)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([1160, 360])

        cab = QtWidgets.QFrame()
        cab.setObjectName("cabecalhoOrdens")
        cab_layout = QtWidgets.QVBoxLayout(cab)
        cab_layout.setContentsMargins(10, 8, 10, 8)
        cab_layout.setSpacing(2)
        self.lbl_titulo_ordens = QtWidgets.QLabel("Painel de Ordens • Fase 1")
        self.lbl_titulo_ordens.setObjectName("tituloOrdens")
        self.lbl_subtitulo_ordens = QtWidgets.QLabel("Spot • Demo local (sem envio)")
        self.lbl_subtitulo_ordens.setObjectName("subtituloOrdens")
        cab_layout.addWidget(self.lbl_titulo_ordens)
        cab_layout.addWidget(self.lbl_subtitulo_ordens)
        painel_layout.addWidget(cab)

        # Card 1 — parâmetros principais
        card1 = QtWidgets.QFrame()
        card1.setObjectName("cardOrdens")
        f1 = QtWidgets.QGridLayout(card1)
        f1.setContentsMargins(12, 12, 12, 12)
        f1.setHorizontalSpacing(10)
        f1.setVerticalSpacing(10)

        f1.addWidget(self._lbl("Tipo"), 0, 0)
        self.combo_tipo_ordem = QtWidgets.QComboBox()
        self.combo_tipo_ordem.addItems(TIPOS_ORDEM)
        self.combo_tipo_ordem.currentTextChanged.connect(self._on_tipo_ordem_change)
        f1.addWidget(self.combo_tipo_ordem, 0, 1)

        f1.addWidget(self._lbl("Quantidade"), 1, 0)
        self.edit_quantidade = QtWidgets.QLineEdit("0.001")
        self.edit_quantidade.setPlaceholderText("Ex.: 0.001")
        self.edit_quantidade.editingFinished.connect(self._normalizar_campos_ativos)
        f1.addWidget(self.edit_quantidade, 1, 1)

        f1.addWidget(self._lbl("Quote Order Qty"), 2, 0)
        self.edit_quote_qty = QtWidgets.QLineEdit("")
        self.edit_quote_qty.setPlaceholderText("Ex.: 100 USDT")
        f1.addWidget(self.edit_quote_qty, 2, 1)

        f1.addWidget(self._lbl("Preço"), 3, 0)
        self.edit_preco = QtWidgets.QLineEdit("10000")
        self.edit_preco.setPlaceholderText("Ex.: 10000")
        self.edit_preco.editingFinished.connect(self._normalizar_campos_ativos)
        f1.addWidget(self.edit_preco, 3, 1)

        f1.addWidget(self._lbl("Stop Price"), 4, 0)
        self.edit_stop = QtWidgets.QLineEdit("")
        self.edit_stop.setPlaceholderText("Ex.: 9500")
        self.edit_stop.editingFinished.connect(self._normalizar_campos_ativos)
        f1.addWidget(self.edit_stop, 4, 1)

        f1.addWidget(self._lbl("Trailing Delta"), 5, 0)
        self.edit_trailing = QtWidgets.QLineEdit("")
        self.edit_trailing.setPlaceholderText("Ex.: 100")
        f1.addWidget(self.edit_trailing, 5, 1)

        f1.addWidget(self._lbl("TimeInForce"), 6, 0)
        self.combo_tif = QtWidgets.QComboBox()
        self.combo_tif.addItems(TIME_IN_FORCE)
        self.combo_tif.setCurrentText("GTC")
        f1.addWidget(self.combo_tif, 6, 1)

        self.lbl_regras = QtWidgets.QLabel("Regras do símbolo serão carregadas ao selecionar um ativo.")
        self.lbl_regras.setObjectName("statusOrdens")
        self.lbl_regras.setWordWrap(True)
        f1.addWidget(self.lbl_regras, 7, 0, 1, 2)

        painel_layout.addWidget(card1)

        # Card 2 — validação demo
        card2 = QtWidgets.QFrame()
        card2.setObjectName("cardOrdens")
        f2 = QtWidgets.QVBoxLayout(card2)
        f2.setContentsMargins(12, 12, 12, 12)
        f2.setSpacing(10)

        self.lbl_modo = QtWidgets.QLabel("Botões abaixo validam e montam o payload local. Não enviam ordens.")
        self.lbl_modo.setObjectName("statusOrdens")
        self.lbl_modo.setWordWrap(True)
        f2.addWidget(self.lbl_modo)

        grid_btn = QtWidgets.QGridLayout()
        self.btn_comprar = QtWidgets.QPushButton("VALIDAR BUY")
        self.btn_comprar.setObjectName("btnComprar")
        self.btn_vender = QtWidgets.QPushButton("VALIDAR SELL")
        self.btn_vender.setObjectName("btnVender")
        self.btn_comprar.clicked.connect(lambda: self._validar_demo("BUY"))
        self.btn_vender.clicked.connect(lambda: self._validar_demo("SELL"))
        grid_btn.addWidget(self.btn_comprar, 0, 0)
        grid_btn.addWidget(self.btn_vender, 0, 1)
        f2.addLayout(grid_btn)

        self.lbl_ordem_status = QtWidgets.QLabel("Pronto para validar payload Spot Fase 1.")
        self.lbl_ordem_status.setObjectName("statusOrdens")
        self.lbl_ordem_status.setWordWrap(True)
        f2.addWidget(self.lbl_ordem_status)

        painel_layout.addWidget(card2)
        painel_layout.addStretch(1)

        self.statusBar().showMessage("Inicializando...")
        self._on_tipo_ordem_change(self.combo_tipo_ordem.currentText())

    def _label_topo(self, txt: str):
        w = QtWidgets.QLabel(txt)
        w.setObjectName("labelTopo")
        return w

    def _lbl(self, txt: str):
        w = QtWidgets.QLabel(txt)
        w.setObjectName("labelCampo")
        return w

    def _aplicar_estilos(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {BG}; color: {TEXT}; }}
            QWidget {{ color: {TEXT}; font-size: 12px; }}
            #barraSuperior {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
            #labelTopo {{ color: {DIM}; font-weight: 600; }}
            QComboBox, QLineEdit {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 8px; min-height: 18px; color: {TEXT}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{ background: {PANEL_2}; border: 1px solid {BORDER}; selection-background-color: {BTN_HOVER}; color: {TEXT}; }}
            #btnFollow {{ background: {BTN}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 14px; font-weight: 700; }}
            #btnFollow:hover {{ background: {BTN_HOVER}; }}
            #btnFollow:pressed {{ background: {BTN_PRESSED}; }}
            #btnFollow:checked {{ background: {BLUE}; color: white; border-color: {BLUE}; }}
            QSplitter::handle {{ background: {PANEL}; border-left: 1px solid {BORDER}; border-right: 1px solid {BORDER}; }}
            QSplitter::handle:horizontal {{ width: 18px; }}
            QToolButton#btnPainelLateral {{ background: {BTN}; border: 1px solid {BORDER}; border-radius: 9px; color: {TEXT}; }}
            QToolButton#btnPainelLateral:hover {{ background: {BTN_HOVER}; }}
            QToolButton#btnPainelLateral:pressed {{ background: {BTN_PRESSED}; }}
            QToolButton#btnPainelLateral:checked {{ background: {PANEL_2}; }}
            #blocoGrafico {{ background: {BG}; border: 1px solid {BORDER}; border-top-left-radius: 14px; border-bottom-left-radius: 14px; }}
            #painelOrdens {{ background: {PANEL}; border: 1px solid {BORDER}; border-top-right-radius: 14px; border-bottom-right-radius: 14px; }}
            #cabecalhoOrdens {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 12px; }}
            #tituloOrdens {{ font-size: 16px; font-weight: 800; color: {TEXT}; }}
            #subtituloOrdens {{ font-size: 11px; color: {DIM}; }}
            #cardOrdens {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 12px; }}
            #labelCampo {{ color: {DIM}; font-weight: 600; }}
            #btnComprar, #btnVender {{ min-height: 40px; border-radius: 12px; font-size: 13px; font-weight: 800; border: none; color: white; }}
            #btnComprar {{ background: {GREEN}; }}
            #btnComprar:hover {{ background: {GREEN_HOVER}; }}
            #btnComprar:pressed {{ background: #00c867; }}
            #btnVender {{ background: {RED}; }}
            #btnVender:hover {{ background: {RED_HOVER}; }}
            #btnVender:pressed {{ background: #e93351; }}
            #statusOrdens {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px; color: {DIM}; }}
            QStatusBar {{ background: {PANEL}; color: {TEXT}; }}
        """)

    # ─────────────────────────────────────────────────────
    # Painel / regras / UI dinâmica
    # ─────────────────────────────────────────────────────
    def _on_painel_alterado(self, visivel: bool):
        symbol = self.combo_simbolos.currentText().strip().upper() if self.combo_simbolos.currentText() else '---'
        tf = self.combo_timeframe.currentText()
        self.lbl_subtitulo_ordens.setText(f"{symbol} • {tf} • Spot • Demo local" if visivel else "Painel recolhido")

    def _on_tipo_ordem_change(self, tipo: str):
        tipo = tipo.upper()
        usa_price = tipo in {"LIMIT", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT", "LIMIT_MAKER"}
        usa_tif = tipo in {"LIMIT", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"}
        usa_stop = tipo in {"STOP_LOSS", "STOP_LOSS_LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_LIMIT"}
        usa_quote_qty = tipo == "MARKET"
        usa_trailing = tipo in {"STOP_LOSS", "STOP_LOSS_LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_LIMIT"}

        self.edit_preco.setEnabled(usa_price)
        self.combo_tif.setEnabled(usa_tif)
        self.edit_stop.setEnabled(usa_stop)
        self.edit_quote_qty.setEnabled(usa_quote_qty)
        self.edit_trailing.setEnabled(usa_trailing)

        self._atualizar_ui_regras()

    def _iniciar_worker_regras(self, symbol: str):
        """✅ CORRIGIDO: Sempre inicializa thread e worker antes de usar."""
        try:
            if self._thread_regras and self._thread_regras.isRunning():
                self._thread_regras.quit()
                self._thread_regras.wait(1000)
        except Exception:
            pass
        
        # ✅ INICIALIZAR SEMPRE ANTES DE USAR
        self._thread_regras = QtCore.QThread(self)
        self._worker_regras = WorkerRegrasSimbolo(symbol)
        self._worker_regras.moveToThread(self._thread_regras)
        
        self._thread_regras.started.connect(self._worker_regras.executar)
        self._worker_regras.pronto.connect(self._on_regras_prontas)
        self._worker_regras.erro.connect(self._on_regras_erro)
        self._worker_regras.pronto.connect(lambda _: self._thread_regras.quit())
        self._worker_regras.erro.connect(lambda _: self._thread_regras.quit())
        
        self._thread_regras.start()
        
    def _on_regras_prontas(self, regras: dict):
        self.regras_simbolo = regras
        self._atualizar_ui_regras()

    def _on_regras_erro(self, msg: str):
        self.regras_simbolo = None
        self.lbl_regras.setText(f"Erro ao carregar regras do símbolo: {msg}")
        self.statusBar().showMessage(f"Erro ao carregar regras do símbolo: {msg}")

    def _filtro_qtd_ativo(self):
        if not self.regras_simbolo:
            return None
        tipo = self.combo_tipo_ordem.currentText().strip().upper()
        if tipo == 'MARKET':
            f = self.regras_simbolo.get('market_lot_size', {})
            if f.get('stepSize', Decimal('0')) > 0 or f.get('minQty', Decimal('0')) > 0:
                return f
        return self.regras_simbolo.get('lot_size', {})

    def _fmt_decimal(self, v: Decimal) -> str:
        s = format(v.normalize(), 'f')
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
        return s if s else '0'

    def _atualizar_ui_regras(self):
        symbol = self.combo_simbolos.currentText().strip().upper() if self.combo_simbolos.currentText() else '---'
        tf = self.combo_timeframe.currentText()
        self.lbl_subtitulo_ordens.setText(f"{symbol} • {tf} • Spot • Demo local")

        if not self.regras_simbolo:
            self.lbl_regras.setText("Regras do símbolo serão carregadas ao selecionar um ativo.")
            return

        qtd_filter = self._filtro_qtd_ativo() or {}
        price_filter = self.regras_simbolo.get('price_filter', {})
        quote = self.regras_simbolo.get('quoteAsset', '') or ''
        base = self.regras_simbolo.get('baseAsset', '') or ''

        min_qty = qtd_filter.get('minQty', Decimal('0'))
        step_qty = qtd_filter.get('stepSize', Decimal('0'))
        max_qty = qtd_filter.get('maxQty', Decimal('0'))
        tick = price_filter.get('tickSize', Decimal('0'))
        min_notional = self.regras_simbolo.get('notional', {}).get('minNotional', Decimal('0'))
        if min_notional <= 0:
            min_notional = self.regras_simbolo.get('min_notional', {}).get('minNotional', Decimal('0'))

        self.edit_quantidade.setPlaceholderText(f"min {min_qty} • step {step_qty} • max {max_qty}")
        self.edit_preco.setPlaceholderText(f"tick {tick} {quote}" if tick > 0 else f"Preço em {quote}")

        self.lbl_regras.setText(
            f"{symbol}: qty {min_qty}–{max_qty} ({base}) • step {step_qty} • tick {tick} {quote} • minNotional {min_notional} {quote}"
        )

    def _normalizar_campos_ativos(self):
        if not self.regras_simbolo:
            return
        qtd_filter = self._filtro_qtd_ativo() or {}
        step_qty = qtd_filter.get('stepSize', Decimal('0'))
        min_qty = qtd_filter.get('minQty', Decimal('0'))
        max_qty = qtd_filter.get('maxQty', Decimal('0'))
        q = _d(self.edit_quantidade.text(), str(min_qty or '0'))
        if step_qty > 0:
            q = _qstep(q, step_qty)
        if min_qty > 0:
            q = max(q, min_qty)
        if max_qty > 0:
            q = min(q, max_qty)
        self.edit_quantidade.setText(self._fmt_decimal(q))

        if self.edit_preco.isEnabled():
            tick = self.regras_simbolo.get('price_filter', {}).get('tickSize', Decimal('0'))
            p = _d(self.edit_preco.text(), '0')
            if p > 0 and tick > 0:
                self.edit_preco.setText(self._fmt_decimal(_qstep(p, tick)))

        if self.edit_stop.isEnabled():
            tick = self.regras_simbolo.get('price_filter', {}).get('tickSize', Decimal('0'))
            p = _d(self.edit_stop.text(), '0')
            if p > 0 and tick > 0:
                self.edit_stop.setText(self._fmt_decimal(_qstep(p, tick)))

    # ─────────────────────────────────────────────────────
    # Validação local Fase 1 (sem envio)
    # ─────────────────────────────────────────────────────
    def _montar_payload_local(self, side: str) -> dict:
        symbol = self.combo_simbolos.currentText().strip().upper()
        if not symbol or symbol.startswith("Carregando") or symbol.startswith("Erro"):
            raise ValueError("Símbolo inválido.")
        if not self.regras_simbolo or self.regras_simbolo.get('symbol') != symbol:
            raise ValueError("Regras do símbolo ainda não carregadas.")

        self._normalizar_campos_ativos()

        tipo = self.combo_tipo_ordem.currentText().strip().upper()
        qty = _d(self.edit_quantidade.text(), '0')
        quote_qty = _d(self.edit_quote_qty.text(), '0')
        price = _d(self.edit_preco.text(), '0')
        stop_price = _d(self.edit_stop.text(), '0')
        trailing = self.edit_trailing.text().strip()
        tif = self.combo_tif.currentText().strip().upper()

        qtd_filter = self._filtro_qtd_ativo() or {}
        min_qty = qtd_filter.get('minQty', Decimal('0'))
        max_qty = qtd_filter.get('maxQty', Decimal('0'))
        step_qty = qtd_filter.get('stepSize', Decimal('0'))

        def validar_qty(q: Decimal):
            if min_qty > 0 and q < min_qty:
                raise ValueError(f"Quantidade menor que minQty ({min_qty}).")
            if max_qty > 0 and q > max_qty:
                raise ValueError(f"Quantidade maior que maxQty ({max_qty}).")
            if step_qty > 0 and _qstep(q, step_qty) != q:
                raise ValueError(f"Quantidade fora do stepSize ({step_qty}).")

        def validar_price(p: Decimal, campo='price'):
            pf = self.regras_simbolo.get('price_filter', {})
            tick = pf.get('tickSize', Decimal('0'))
            min_price = pf.get('minPrice', Decimal('0'))
            max_price = pf.get('maxPrice', Decimal('0'))
            if p <= 0:
                raise ValueError(f"{campo} inválido.")
            if tick > 0 and _qstep(p, tick) != p:
                raise ValueError(f"{campo} fora do tickSize ({tick}).")
            if min_price > 0 and p < min_price:
                raise ValueError(f"{campo} menor que minPrice ({min_price}).")
            if max_price > 0 and p > max_price:
                raise ValueError(f"{campo} maior que maxPrice ({max_price}).")

        payload = {'symbol': symbol, 'side': side.upper(), 'type': tipo}

        if tipo == 'LIMIT':
            if qty <= 0:
                raise ValueError('LIMIT exige quantity.')
            if price <= 0:
                raise ValueError('LIMIT exige price.')
            validar_qty(qty)
            validar_price(price, 'price')
            payload.update({'quantity': self._fmt_decimal(qty), 'price': self._fmt_decimal(price), 'timeInForce': tif})

        elif tipo == 'MARKET':
            if qty <= 0 and quote_qty <= 0:
                raise ValueError('MARKET exige quantity ou quoteOrderQty.')
            if qty > 0:
                validar_qty(qty)
                payload['quantity'] = self._fmt_decimal(qty)
            else:
                payload['quoteOrderQty'] = self._fmt_decimal(quote_qty)

        elif tipo == 'STOP_LOSS':
            if qty <= 0:
                raise ValueError('STOP_LOSS exige quantity.')
            if stop_price <= 0 and not trailing:
                raise ValueError('STOP_LOSS exige stopPrice ou trailingDelta.')
            validar_qty(qty)
            payload['quantity'] = self._fmt_decimal(qty)
            if stop_price > 0:
                validar_price(stop_price, 'stopPrice')
                payload['stopPrice'] = self._fmt_decimal(stop_price)
            if trailing:
                payload['trailingDelta'] = trailing

        elif tipo == 'STOP_LOSS_LIMIT':
            if qty <= 0:
                raise ValueError('STOP_LOSS_LIMIT exige quantity.')
            if price <= 0:
                raise ValueError('STOP_LOSS_LIMIT exige price.')
            if stop_price <= 0 and not trailing:
                raise ValueError('STOP_LOSS_LIMIT exige stopPrice ou trailingDelta.')
            validar_qty(qty)
            validar_price(price, 'price')
            payload.update({'quantity': self._fmt_decimal(qty), 'price': self._fmt_decimal(price), 'timeInForce': tif})
            if stop_price > 0:
                validar_price(stop_price, 'stopPrice')
                payload['stopPrice'] = self._fmt_decimal(stop_price)
            if trailing:
                payload['trailingDelta'] = trailing

        elif tipo == 'TAKE_PROFIT':
            if qty <= 0:
                raise ValueError('TAKE_PROFIT exige quantity.')
            if stop_price <= 0 and not trailing:
                raise ValueError('TAKE_PROFIT exige stopPrice ou trailingDelta.')
            validar_qty(qty)
            payload['quantity'] = self._fmt_decimal(qty)
            if stop_price > 0:
                validar_price(stop_price, 'stopPrice')
                payload['stopPrice'] = self._fmt_decimal(stop_price)
            if trailing:
                payload['trailingDelta'] = trailing

        elif tipo == 'TAKE_PROFIT_LIMIT':
            if qty <= 0:
                raise ValueError('TAKE_PROFIT_LIMIT exige quantity.')
            if price <= 0:
                raise ValueError('TAKE_PROFIT_LIMIT exige price.')
            if stop_price <= 0 and not trailing:
                raise ValueError('TAKE_PROFIT_LIMIT exige stopPrice ou trailingDelta.')
            validar_qty(qty)
            validar_price(price, 'price')
            payload.update({'quantity': self._fmt_decimal(qty), 'price': self._fmt_decimal(price), 'timeInForce': tif})
            if stop_price > 0:
                validar_price(stop_price, 'stopPrice')
                payload['stopPrice'] = self._fmt_decimal(stop_price)
            if trailing:
                payload['trailingDelta'] = trailing

        elif tipo == 'LIMIT_MAKER':
            if qty <= 0:
                raise ValueError('LIMIT_MAKER exige quantity.')
            if price <= 0:
                raise ValueError('LIMIT_MAKER exige price.')
            validar_qty(qty)
            validar_price(price, 'price')
            payload.update({'quantity': self._fmt_decimal(qty), 'price': self._fmt_decimal(price)})

        else:
            raise ValueError(f"Tipo de ordem não suportado na Fase 1: {tipo}")

        # Notional mínimo somente quando houver price*qty disponível
        if 'price' in payload and 'quantity' in payload:
            notional = _d(payload['price']) * _d(payload['quantity'])
            min_notional = self.regras_simbolo.get('notional', {}).get('minNotional', Decimal('0'))
            if min_notional <= 0:
                min_notional = self.regras_simbolo.get('min_notional', {}).get('minNotional', Decimal('0'))
            if min_notional > 0 and notional < min_notional:
                raise ValueError(f"Valor da ordem menor que minNotional ({min_notional}).")

        return payload

    def _validar_demo(self, side: str):
        try:
            payload = self._montar_payload_local(side)
            self.lbl_ordem_status.setText(f"Payload local válido: {payload}")
            self.statusBar().showMessage("Validação local da Fase 1 OK.")
        except Exception as e:
            self.lbl_ordem_status.setText(f"Erro de validação: {e}")
            self.statusBar().showMessage(f"Erro de validação: {e}")

    # ─────────────────────────────────────────────────────
    # Símbolos / regras / engine
    # ─────────────────────────────────────────────────────
    def _iniciar_worker_simbolos(self):
        self._thread_simbolos = QtCore.QThread(self)
        self._worker_simbolos = WorkerSimbolos(quote="USDT")
        self._worker_simbolos.moveToThread(self._thread_simbolos)
        self._thread_simbolos.started.connect(self._worker_simbolos.executar)
        self._worker_simbolos.pronto.connect(self._on_simbolos_prontos)
        self._worker_simbolos.erro.connect(self._on_simbolos_erro)
        self._worker_simbolos.pronto.connect(lambda _: self._thread_simbolos.quit())
        self._worker_simbolos.erro.connect(lambda _: self._thread_simbolos.quit())
        self._thread_simbolos.start()

    def _on_simbolos_prontos(self, simbolos: list):
        self.combo_simbolos.blockSignals(True)
        self.combo_simbolos.clear()
        for s in simbolos:
            self.combo_simbolos.addItem(s, s.lower())
        self.combo_simbolos.setEnabled(True)
        self.combo_simbolos.blockSignals(False)
        self.statusBar().showMessage(f"Símbolos carregados: {len(simbolos)}")
        if simbolos:
            symbol_ws = self.combo_simbolos.itemData(0)
            self._iniciar_engine(symbol_ws, self.combo_timeframe.currentText())
            self._iniciar_worker_regras(self.combo_simbolos.currentText().strip().upper())

    def _on_simbolos_erro(self, msg: str):
        self.combo_simbolos.blockSignals(True)
        self.combo_simbolos.clear()
        self.combo_simbolos.addItem("Erro ao carregar símbolos")
        self.combo_simbolos.setEnabled(False)
        self.combo_simbolos.blockSignals(False)
        self.statusBar().showMessage(f"Erro ao buscar símbolos: {msg}")

    def _iniciar_engine(self, symbol_ws: str, timeframe: str):
        try:
            if self.engine:
                self.engine.stop()
        except Exception:
            pass
        self.engine = EngineHFT(symbol_ws, timeframe=timeframe)
        self.statusBar().showMessage(f"Engine: {symbol_ws} | TF: {timeframe}")

    def _on_symbol_change(self, idx: int):
        if idx < 0:
            return
        symbol_ws = self.combo_simbolos.itemData(idx)
        symbol_ui = self.combo_simbolos.currentText().strip().upper()
        if not symbol_ws or not symbol_ui:
            return
        self._iniciar_engine(symbol_ws, self.combo_timeframe.currentText())
        self._iniciar_worker_regras(symbol_ui)
        self._on_painel_alterado(self.splitter._right_visible)

    def _on_timeframe_change(self, tf: str):
        if self.engine:
            try:
                self.engine.set_timeframe(tf)
                self.statusBar().showMessage(f"Timeframe alterado para: {tf}")
            except Exception as e:
                self.statusBar().showMessage(f"Erro ao trocar timeframe: {e}")
        self._on_painel_alterado(self.splitter._right_visible)

    def _on_follow_toggled(self, checked: bool):
        if hasattr(self.grafico, 'set_follow'):
            self.grafico.set_follow(checked)
        self.btn_follow.setText("FOLLOW" if checked else "FREE")

    # ─────────────────────────────────────────────────────
    # Render / encerramento
    # ─────────────────────────────────────────────────────
    def _iniciar_timer_render(self):
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.render)
        self.timer.start(16)

    def render(self):
        if not self.engine:
            return
        candles = self.engine.get_snapshot(300)
        self.grafico.atualizar(candles)

    def closeEvent(self, event):
        try:
            if self.engine:
                self.engine.stop()
        except Exception:
            pass
        try:
            if self._thread_simbolos and self._thread_simbolos.isRunning():
                self._thread_simbolos.quit()
                self._thread_simbolos.wait(1000)
        except Exception:
            pass
        try:
            if self._thread_regras and self._thread_regras.isRunning():
                self._thread_regras.quit()
                self._thread_regras.wait(1000)
        except Exception:
            pass
        super().closeEvent(event)
