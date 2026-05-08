
onst botao = document.getElementById("btnCarregar");
const lista = document.getElementById("lista");
const status = document.getElementById("status");

botao.addEventListener("click", carregarUsuarios);

async function carregarUsuarios() {
  lista.innerHTML = "";
  status.textContent = "Carregando dados da API...";

  try {
    const resposta = await fetch(
      "https://jsonplaceholder.typicode.com/users"
    );

    if (!resposta.ok) {
      throw new Error("Erro ao acessar a API");
    }

    const dados = await resposta.json();

    status.textContent = `✅ ${dados.length} usuários carregados`;

    dados.forEach(usuario => {
      const card = document.createElement("div");
      card.classList.add("card");

      card.innerHTML = `
        <h3>${usuario.name}</h3>
        <span>${usuario.email}</span><br />
        <span>${usuario.company.name}</span>
      `;

      lista.appendChild(card);
    });

  } catch (erro) {
    status.innerHTML = `<span style="color: var(--danger)">❌ ${erro.message}</span>`;
  }
}
