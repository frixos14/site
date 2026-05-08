
let socket;
let chart;

const priceEl = document.getElementById("price");
const statusEl = document.getElementById("status");
const symbolInput = document.getElementById("symbol");

document.getElementById("start").onclick = iniciar;

async function iniciar() {
  const symbol = symbolInput.value.toUpperCase();
  statusEl.textContent = "Inicializando terminal...";

  if (socket) socket.close();

  await carregarCandles(symbol);
  iniciarWebSocket(symbol);

  statusEl.textContent = "✔ Terminal ativo";
}

// =====================
// REST – Candles
// =====================
async function carregarCandles(symbol) {
  const res = await fetch(
    `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=1m&limit=50`
  );
  const data = await res.json();

  const labels = data.map(c => new Date(c[0]).toLocaleTimeString());
  const prices = data.map(c => parseFloat(c[4]));

  const ctx = document.getElementById("chart").getContext("2d");

  if (chart) chart.destroy();

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        data: prices,
        borderColor: "#f0b90b",
        borderWidth: 2,
        tension: 0.2
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { ticks: { color: "#777" } }
      }
    }
  });
}

// =====================
// WebSocket – Realtime
// =====================
function iniciarWebSocket(symbol) {
  socket = new WebSocket(
    `wss://stream.binance.com:9443/ws/${symbol.toLowerCase()}@trade`
  );

  socket.onmessage = e => {
    const data = JSON.parse(e.data);
    const price = parseFloat(data.p);

    priceEl.textContent = price.toLocaleString("pt-BR", {
      minimumFractionDigits: 2
    });

    atualizarGrafico(price);
  };
}

// =====================
// Atualiza gráfico em tempo real
// =====================
function atualizarGrafico(price) {
  if (!chart) return;

  chart.data.labels.push("");
  chart.data.datasets[0].data.push(price);

  if (chart.data.labels.length > 50) {
    chart.data.labels.shift();
    chart.data.datasets[0].data.shift();
  }

  chart.update();
}
