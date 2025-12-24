async function postReceipt(form) {
  const statusBox = document.getElementById("status");
  statusBox.textContent = "Распознаём чек...";
  const formData = new FormData(form);
  const fileInput = form.querySelector('input[type="file"]');
  const selectedFile = fileInput?.files?.[0];
  if (selectedFile) {
    console.info("[upload] Отправляем файл чека", {
      name: selectedFile.name,
      size: `${selectedFile.size} bytes`,
      type: selectedFile.type,
    });
  } else {
    console.warn("[upload] Файл не выбран перед отправкой");
  }
  try {
    const response = await fetch("/api/receipts", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      let detail;
      try {
        detail = await response.json();
      } catch {
        detail = await response.text();
      }
      console.error("[upload] Сервер вернул ошибку", {
        status: response.status,
        statusText: response.statusText,
        detail,
      });
      statusBox.textContent = "Ошибка загрузки чека";
      return;
    }
    const data = await response.json();
    console.info("[upload] Чек успешно загружен", { receiptId: data.receipt_id });
    statusBox.textContent = "Готово! Перенаправляем на проверку...";
    window.location.href = `/review/${data.receipt_id}`;
  } catch (err) {
    console.error("[upload] Не удалось отправить чек", err);
    statusBox.textContent = "Не удалось отправить чек";
  }
}

async function loadItems(receiptId) {
  const response = await fetch(`/api/receipts/${receiptId}/items`);
  if (!response.ok) {
    throw new Error("Не удалось загрузить позиции");
  }
  return response.json();
}

function renderItems(items) {
  const tbody = document.getElementById("items-body");
  tbody.innerHTML = "";
  items.forEach((item) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input name="name" value="${item.name}" /></td>
      <td><input name="qty_total" type="number" step="1" min="1" value="${item.qty_total}" /></td>
      <td><input name="unit_price" type="number" step="0.01" min="0" value="${item.unit_price}" /></td>
      <td><input name="amount_total" type="number" step="0.01" min="0" value="${item.amount_total}" /></td>
      <td><button class="delete-row">Удалить</button></td>
    `;
    tbody.appendChild(row);
  });
}

function collectItems() {
  const rows = document.querySelectorAll("#items-body tr");
  return Array.from(rows).map((row) => {
    const [name, qty, unit, total] = row.querySelectorAll("input");
    return {
      name: name.value.trim() || "Без названия",
      qty_total: Number(qty.value),
      unit_price: Number(unit.value),
      amount_total: Number(total.value),
    };
  });
}

async function saveItems(receiptId) {
  const items = collectItems();
  const response = await fetch(`/api/receipts/${receiptId}/items`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  if (!response.ok) {
    throw new Error("Не удалось сохранить позиции");
  }
  return response.json();
}

async function finalizeReceipt(receiptId) {
  const response = await fetch(`/api/receipts/${receiptId}/finalize`, { method: "POST" });
  if (!response.ok) {
    throw new Error("Не удалось опубликовать чек");
  }
  return response.json();
}

async function initReviewPage() {
  const receiptId = document.body.dataset.receipt;
  const addButton = document.getElementById("add-row");
  const saveButton = document.getElementById("save-items");
  const publishButton = document.getElementById("publish-receipt");
  const message = document.getElementById("message");
  const tbody = document.getElementById("items-body");

  try {
    const items = await loadItems(receiptId);
    renderItems(items);
  } catch (err) {
    message.textContent = err.message;
  }

  addButton.addEventListener("click", () => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input name="name" value="Новая позиция" /></td>
      <td><input name="qty_total" type="number" step="1" min="1" value="1" /></td>
      <td><input name="unit_price" type="number" step="0.01" min="0" value="0" /></td>
      <td><input name="amount_total" type="number" step="0.01" min="0" value="0" /></td>
      <td><button class="delete-row">Удалить</button></td>
    `;
    tbody.appendChild(row);
  });

  tbody.addEventListener("click", (event) => {
    if (event.target.classList.contains("delete-row")) {
      event.target.closest("tr").remove();
    }
  });

  saveButton.addEventListener("click", async () => {
    try {
      await saveItems(receiptId);
      message.textContent = "Сохранено";
    } catch (err) {
      message.textContent = err.message;
    }
  });

  publishButton.addEventListener("click", async () => {
    try {
      await saveItems(receiptId);
      const data = await finalizeReceipt(receiptId);
      window.location.href = data.room_url;
    } catch (err) {
      message.textContent = err.message;
    }
  });
}

async function fetchRoom(token) {
  const response = await fetch(`/api/receipts/${token}`);
  if (!response.ok) throw new Error("Чек не найден");
  return response.json();
}

function renderRoom(data) {
  const container = document.getElementById("room");
  container.innerHTML = "";
  data.items.forEach((item) => {
    const section = document.createElement("section");
    const paidUnits = item.units.filter((u) => u.status === "paid").length;
    section.innerHTML = `
      <h3>${item.name}</h3>
      <p>${paidUnits}/${item.units.length} оплачено · ${item.unit_price} ₽ за шт.</p>
      <div class="units">${item.units
        .map(
          (unit) => `
          <button class="unit-btn" data-id="${unit.id}" data-item="${item.id}" data-status="${unit.status}">
            Юнит ${unit.unit_index + 1}: ${unit.amount_paid}/${unit.amount_total} ₽ (${unit.status})
          </button>
        `
        )
        .join("")}</div>
      <div class="actions">
        <button class="pay-one" data-item="${item.id}">Оплатить 1 шт</button>
      </div>
    `;
    container.appendChild(section);
  });

  const paymentsList = document.getElementById("payments");
  paymentsList.innerHTML = data.payments
    .map(
      (p) =>
        `<li>${new Date(p.created_at).toLocaleTimeString()} — ${p.payer_name}: ${p.amount} ₽ (юнит ${p.unit_id})</li>`
    )
    .join("");
}

async function sendPayment(token, payload) {
  const response = await fetch(`/api/receipts/${token}/pay`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json();
    throw new Error(detail.detail || "Ошибка оплаты");
  }
}

async function initRoomPage() {
  const token = document.body.dataset.token;
  const nameInput = document.getElementById("payer-name");
  const payButton = document.getElementById("pay-selected");
  let latestData = await fetchRoom(token);
  renderRoom(latestData);

  document.getElementById("room").addEventListener("click", async (event) => {
    if (event.target.classList.contains("pay-one")) {
      const payer = nameInput.value.trim() || "Гость";
      const itemId = event.target.dataset.item;
      await sendPayment(token, { payer_name: payer, lines: [{ item_id: itemId, mode: "unit_full" }] });
      latestData = await fetchRoom(token);
      renderRoom(latestData);
    }
    if (event.target.classList.contains("unit-btn")) {
      const payer = nameInput.value.trim() || "Гость";
      const unitId = event.target.dataset.id;
      const itemId = event.target.dataset.item;
      const amount = prompt("Сколько оплатить?");
      if (!amount) return;
      await sendPayment(token, {
        payer_name: payer,
        lines: [{ item_id: itemId, mode: "unit_partial", unit_id: unitId, amount: Number(amount) }],
      });
      latestData = await fetchRoom(token);
      renderRoom(latestData);
    }
  });

  try {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/rooms/${token}`);
    ws.onmessage = async () => {
      latestData = await fetchRoom(token);
      renderRoom(latestData);
    };
  } catch (err) {
    console.warn("WebSocket недоступен", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.body.classList.contains("page-index")) {
    const form = document.getElementById("upload-form");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      postReceipt(form);
    });
  }

  if (document.body.classList.contains("page-review")) {
    initReviewPage();
  }

  if (document.body.classList.contains("page-room")) {
    initRoomPage();
  }
});
