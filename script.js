
const btn = document.getElementById("btn");
const symbolInput = document.getElementById("symbol");
const status = document.getElementById("status");
const card = document.getElementById("resultado");
const par = document.getElementById("par");
const preco = document.getElementById("preco");

btn.addEventListener("click", consultar);

async function consultar() {
  const symbol = symbolInput.value.toUpperCase().trim();
  card.classList.add("hidden");
  status.textContent = "Consultando Binance...";

  try {
    const res = await fetch(
      `https://api.binance.com/api/v3/ticker/price?symbol=${symbol}`
    );

    if (!res.ok) {
      throw new Error("Par inválido ou indisponível");
    }

    const data = await res.json();

    par.textContent = data.symbol;
    preco.textContent = Number(data.price).toLocaleString("pt-BR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });

    status.textContent = "✔ Dados recebidos da Binance";
    card.classList.remove("hidden");

  } catch (err) {
    status.textContent = "❌ " + err.message;
  }
}
